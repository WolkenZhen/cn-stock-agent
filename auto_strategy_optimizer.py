import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta
import os
from tqdm import tqdm  # 进度条，需安装：pip install tqdm
import warnings
warnings.filterwarnings('ignore')

# ====================== 全局配置（可微调，无需每天改）======================
# 选股配置
STOCK_FILTER_CONFIG = {
    "min_market_cap": 500,  # 最小市值（亿）
    "min_avg_volume": 1,    # 最小日均成交额（亿）
    "exclude_st": True,     # 排除ST股
    "exclude_delisted": True,  # 排除退市股
    "stock_pool": "沪深A股"  # 选股池：沪深A股/创业板/科创板
}

# 参数优化配置（搜索范围）
PARAM_SEARCH_CONFIG = {
    "MA_SHORT": [3, 4, 5, 6, 7, 8, 9, 10],  # 短期均线（天）
    "MA_LONG": [15, 18, 20, 22, 25, 28, 30],  # 长期均线（天）
    "SUPPORT_RESIST_DAYS": [3, 4, 5, 6, 7],  # 支撑/阻力计算天数（天）
    "BUY_MARGIN": [0.005, 0.01, 0.015, 0.02],  # 买入区间margin
    "SELL_MARGIN": [0.005, 0.01, 0.015, 0.02]  # 卖出区间margin
}

# 回测配置
BACKTEST_CONFIG = {
    "history_days": 365,  # 回测历史天数（1年）
    "transaction_cost": 0.0015,  # 交易成本（印花税+佣金，0.15%）
    "score_weights": {  # 参数优化评分权重
        "annual_return": 0.6,    # 年化收益率权重
        "win_rate": 0.3,         # 胜率权重
        "max_drawdown": -0.1     # 最大回撤权重（负向）
    }
}

# 保存路径（自动创建）
LOG_DIR = "strategy_log"
os.makedirs(LOG_DIR, exist_ok=True)
PARAM_LOG_PATH = os.path.join(LOG_DIR, "param_optimization_log.csv")
STOCK_LOG_PATH = os.path.join(LOG_DIR, "stock_selection_log.csv")

# ====================== 工具函数 ======================
def get_tradable_stocks():
    """获取符合条件的可交易股票池（流动性+风险过滤）"""
    print("📊 正在筛选可交易股票池...")
    # 用AKShare获取沪深A股列表（包含市值、成交额等）
    stock_info = ak.stock_info_a_code_name()  # 股票代码+名称
    stock_quote = ak.stock_zh_a_spot_em()     # 实时行情（含成交额）
    
    # 合并股票信息和行情
    stock_df = pd.merge(
        stock_info,
        stock_quote[["代码", "最新价", "成交额", "总市值"]],
        left_on="code", right_on="代码", how="inner"
    ).drop("代码", axis=1)
    
    # 单位转换（成交额：万→亿，总市值：万→亿）
    stock_df["成交额_亿"] = stock_df["成交额"] / 10000
    stock_df["总市值_亿"] = stock_df["总市值"] / 10000
    
    # 筛选条件
    filter_mask = (
        (stock_df["总市值_亿"] >= STOCK_FILTER_CONFIG["min_market_cap"]) &
        (stock_df["成交额_亿"] >= STOCK_FILTER_CONFIG["min_avg_volume"])
    )
    
    # 排除ST股
    if STOCK_FILTER_CONFIG["exclude_st"]:
        filter_mask &= ~(
            stock_df["name"].str.contains("ST", na=False) |
            stock_df["name"].str.contains("退市", na=False)
        )
    
    # 筛选结果
    tradable_stocks = stock_df[filter_mask][["code", "name", "总市值_亿", "成交额_亿"]].reset_index(drop=True)
    print(f"✅ 筛选完成！可交易股票池共{len(tradable_stocks)}只")
    return tradable_stocks

def calculate_short_term_score(stock_code):
    """计算单只股票的短线评分（因子加权）"""
    try:
        # 获取近60天日线数据（计算短线因子）
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            adjust="qfq"
        ).tail(60).reset_index(drop=True)
        
        if len(df) < 30:  # 数据不足30天，跳过
            return 0
        
        # 因子1：近5日涨幅（强势度）→ 标准化到0-20分
        recent_5d_return = (df.iloc[-1]["收盘"] - df.iloc[-6]["收盘"]) / df.iloc[-6]["收盘"]
        return_score = min(max(recent_5d_return * 100, 0), 20)
        
        # 因子2：成交量放大率（近5日/近20日）→ 0-20分
        recent_5d_volume = df.iloc[-5:]["成交量"].mean()
        recent_20d_volume = df.iloc[-20:]["成交量"].mean()
        volume_ratio = recent_5d_volume / recent_20d_volume if recent_20d_volume != 0 else 0
        volume_score = min(max(volume_ratio * 10, 0), 20)
        
        # 因子3：均线多头排列（5/10/20日均线）→ 0-20分
        df["ma5"] = df["收盘"].rolling(5).mean()
        df["ma10"] = df["收盘"].rolling(10).mean()
        df["ma20"] = df["收盘"].rolling(20).mean()
        ma排列 = (
            df.iloc[-1]["ma5"] > df.iloc[-1]["ma10"] > df.iloc[-1]["ma20"]
        )
        ma_score = 20 if ma排列 else 0
        
        # 因子4：RSI（6日）→ 0-20分（50-70分最佳，对应10-20分）
        delta = df["收盘"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(6).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
        rs = gain / loss if loss != 0 else 0
        rsi6 = 100 - (100 / (1 + rs))
        rsi_score = min(max((rsi6 - 40) * 2, 0), 20)
        
        # 因子5：换手率（近5日平均）→ 0-20分（2%-8%最佳）
        turnover = df.iloc[-5:]["换手率"].mean() if "换手率" in df.columns else 0
        turnover_score = min(max((turnover - 1) * 4, 0), 20)
        
        # 总评分（加权求和）
        total_score = (
            return_score * 0.3 +
            volume_score * 0.2 +
            ma_score * 0.2 +
            rsi_score * 0.15 +
            turnover_score * 0.15
        )
        return round(total_score, 2)
    except Exception as e:
        return 0

def select_top10_stocks():
    """自动选出10只短线高潜力股票"""
    print("\n🎯 正在评选短线潜力股（前10名）...")
    tradable_stocks = get_tradable_stocks()
    
    # 计算每只股票的短线评分（带进度条）
    scores = []
    for idx, row in tqdm(tradable_stocks.iterrows(), total=len(tradable_stocks)):
        score = calculate_short_term_score(row["code"])
        scores.append(score)
    
    tradable_stocks["短线评分"] = scores
    top10_stocks = tradable_stocks.nlargest(10, "短线评分").reset_index(drop=True)
    
    # 保存选股日志
    top10_stocks["选股日期"] = datetime.now().strftime("%Y-%m-%d")
    top10_stocks.to_csv(STOCK_LOG_PATH, mode="a", header=not os.path.exists(STOCK_LOG_PATH), index=False)
    
    print(f"\n🏆 短线潜力股TOP10：")
    for idx, row in top10_stocks.iterrows():
        print(f"{idx+1:2d}. {row['code']} {row['name']} | 市值：{row['总市值_亿']:.1f}亿 | 评分：{row['短线评分']:.1f}")
    return top10_stocks

def backtest_strategy(stock_code, params):
    """回测单只股票的策略表现（给定参数）"""
    try:
        # 获取回测数据（近1年）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=BACKTEST_CONFIG["history_days"])
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            adjust="qfq"
        ).reset_index(drop=True)
        
        if len(df) < params["MA_LONG"] * 2:  # 数据不足，跳过
            return None
        
        # 计算均线和交易信号
        df["ma_short"] = df["收盘"].rolling(params["MA_SHORT"]).mean()
        df["ma_long"] = df["收盘"].rolling(params["MA_LONG"]).mean()
        df["support"] = df["最低"].rolling(params["SUPPORT_RESIST_DAYS"]).min()
        df["resistance"] = df["最高"].rolling(params["SUPPORT_RESIST_DAYS"]).max()
        
        # 交易信号：金叉（ma_short上穿ma_long）且价格在支撑位附近→买入；死叉→卖出
        df["buy_signal"] = (
            df["ma_short"].shift(1) < df["ma_long"].shift(1) &
            df["ma_short"] > df["ma_long"] &
            df["收盘"] <= df["support"] * (1 + params["BUY_MARGIN"])
        )
        df["sell_signal"] = (
            df["ma_short"].shift(1) > df["ma_long"].shift(1) &
            df["ma_short"] < df["ma_long"]
        )
        
        # 模拟交易
        position = 0  # 持仓状态：0=空仓，1=持仓
        trades = []
        for idx, row in df.iterrows():
            if row["buy_signal"] and position == 0:
                # 买入
                buy_price = row["收盘"] * (1 + params["BUY_MARGIN"])
                position = 1
                buy_date = row["日期"]
            elif row["sell_signal"] and position == 1:
                # 卖出
                sell_price = row["收盘"] * (1 - params["SELL_MARGIN"])
                # 扣除交易成本
                net_sell_price = sell_price * (1 - BACKTEST_CONFIG["transaction_cost"])
                net_buy_price = buy_price * (1 + BACKTEST_CONFIG["transaction_cost"])
                return_rate = (net_sell_price - net_buy_price) / net_buy_price
                trades.append({
                    "buy_date": buy_date,
                    "sell_date": row["日期"],
                    "return_rate": return_rate
                })
                position = 0
        
        # 计算回测指标
        if not trades:
            return {"annual_return": 0, "win_rate": 0, "max_drawdown": 0}
        
        trade_df = pd.DataFrame(trades)
        total_return = (1 + trade_df["return_rate"]).prod() - 1
        annual_return = (1 + total_return) ** (365 / BACKTEST_CONFIG["history_days"]) - 1
        win_rate = (trade_df["return_rate"] > 0).mean()
        
        # 计算最大回撤（累计收益的最大跌幅）
        trade_df["cum_return"] = (1 + trade_df["return_rate"]).cumprod()
        trade_df["cum_max"] = trade_df["cum_return"].cummax()
        trade_df["drawdown"] = (trade_df["cum_return"] - trade_df["cum_max"]) / trade_df["cum_max"]
        max_drawdown = trade_df["drawdown"].min()
        
        return {
            "annual_return": annual_return,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown
        }
    except Exception as e:
        return None

def optimize_strategy_params(top10_stocks):
    """自动优化策略参数（遍历组合，回测TOP10股票）"""
    print("\n⚙️  正在优化策略参数...")
    from itertools import product
    
    # 生成所有参数组合
    param_names = list(PARAM_SEARCH_CONFIG.keys())
    param_combinations = product(*PARAM_SEARCH_CONFIG.values())
    total_combinations = len(list(product(*PARAM_SEARCH_CONFIG.values())))
    print(f"参数组合总数：{total_combinations}，正在回测...")
    
    best_score = -float("inf")
    best_params = None
    all_results = []
    
    # 遍历参数组合（带进度条）
    for combo in tqdm(param_combinations, total=total_combinations):
        params = dict(zip(param_names, combo))
        
        # 回测TOP10股票的平均表现
        stock_metrics = []
        for _, row in top10_stocks.iterrows():
            metrics = backtest_strategy(row["code"], params)
            if metrics:
                stock_metrics.append(metrics)
        
        if not stock_metrics:
            continue
        
        # 计算平均指标
        avg_metrics = {
            "annual_return": np.mean([m["annual_return"] for m in stock_metrics]),
            "win_rate": np.mean([m["win_rate"] for m in stock_metrics]),
            "max_drawdown": np.mean([m["max_drawdown"] for m in stock_metrics])
        }
        
        # 计算综合评分
        score = (
            avg_metrics["annual_return"] * BACKTEST_CONFIG["score_weights"]["annual_return"] +
            avg_metrics["win_rate"] * BACKTEST_CONFIG["score_weights"]["win_rate"] +
            avg_metrics["max_drawdown"] * BACKTEST_CONFIG["score_weights"]["max_drawdown"]
        )
        
        all_results.append({**params, **avg_metrics, "综合评分": score})
        
        # 更新最优参数
        if score > best_score:
            best_score = score
            best_params = params.copy()
    
    # 保存参数优化日志
    result_df = pd.DataFrame(all_results)
    result_df["优化日期"] = datetime.now().strftime("%Y-%m-%d")
    result_df.to_csv(PARAM_LOG_PATH, mode="a", header=not os.path.exists(PARAM_LOG_PATH), index=False)
    
    print(f"\n✨ 最优参数组合：")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    print(f"  平均年化收益率：{avg_metrics['annual_return']:.2%}")
    print(f"  平均胜率：{avg_metrics['win_rate']:.2%}")
    print(f"  平均最大回撤：{avg_metrics['max_drawdown']:.2%}")
    return best_params

def generate_trading_signals(top10_stocks, best_params):
    """生成TOP10股票的当日交易信号"""
    print("\n📈 当日交易信号：")
    trading_signals = []
    
    for _, row in top10_stocks.iterrows():
        try:
            # 获取最新10天数据
            df = ak.stock_zh_a_hist(
                symbol=row["code"],
                period="daily",
                adjust="qfq"
            ).tail(10).reset_index(drop=True)
            
            df["ma_short"] = df["收盘"].rolling(best_params["MA_SHORT"]).mean()
            df["ma_long"] = df["收盘"].rolling(best_params["MA_LONG"]).mean()
            df["support"] = df["最低"].rolling(best_params["SUPPORT_RESIST_DAYS"]).min()
            
            # 最新数据
            latest = df.iloc[-1]
            prev_latest = df.iloc[-2]
            
            # 买入信号判断
            buy_signal = (
                prev_latest["ma_short"] < prev_latest["ma_long"] &
                latest["ma_short"] > latest["ma_long"] &
                latest["收盘"] <= latest["support"] * (1 + best_params["BUY_MARGIN"])
            )
            
            # 卖出信号判断（假设持仓）
            sell_signal = (
                prev_latest["ma_short"] > prev_latest["ma_long"] &
                latest["ma_short"] < latest["ma_long"]
            )
            
            # 生成信号
            signal = "买入" if buy_signal else "卖出" if sell_signal else "观望"
            trading_signals.append({
                "股票代码": row["code"],
                "股票名称": row["name"],
                "最新价": latest["收盘"],
                "5日均线": latest["ma_short"],
                "20日均线": latest["ma_long"],
                "交易信号": signal
            })
            
            print(f"{row['code']} {row['name']} | 最新价：{latest['收盘']:.2f} | 信号：{signal}")
        except Exception as e:
            continue
    
    # 保存交易信号
    signal_df = pd.DataFrame(trading_signals)
    signal_df["日期"] = datetime.now().strftime("%Y-%m-%d")
    signal_df.to_csv(os.path.join(LOG_DIR, "trading_signals.csv"), mode="a", header=not os.path.exists(os.path.join(LOG_DIR, "trading_signals.csv")), index=False)

# ====================== 主流程 ======================
if __name__ == "__main__":
    print("="*60)
    print(f"📅 策略自动优化程序（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
    print("="*60)
    
    # 1. 自动选10只短线潜力股
    top10_stocks = select_top10_stocks()
    
    # 2. 自动优化策略参数
    best_params = optimize_strategy_params(top10_stocks)
    
    # 3. 生成当日交易信号
    generate_trading_signals(top10_stocks, best_params)
    
    # 4. 输出月度优化提示
    log_df = pd.read_csv(PARAM_LOG_PATH)
    total_days = log_df["优化日期"].nunique()
    print(f"\n📊 月度优化进度：{total_days}/30 天")
    if total_days >= 30:
        print("🎉 月度优化完成！最佳策略已保存至日志，可查看 param_optimization_log.csv 分析")
    else:
        print(f"⏳ 剩余 {30 - total_days} 天完成月度优化，建议每天运行一次")
    
    print("="*60)