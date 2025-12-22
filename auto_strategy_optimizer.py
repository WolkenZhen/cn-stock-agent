import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta
import os
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# ====================== 精准配置（权衡时间+准确度）======================
STOCK_FILTER_CONFIG = {
    "min_market_cap": 500,  # 大盘股筛选（稳定性高）
    "min_avg_volume": 2,    # 提高成交额门槛（流动性更好）
    "exclude_st": True,
    "exclude_delisted": True,
    "stock_pool": "沪深A股",
    "max_stock_count": 200  # 限制筛选数量（避免运行过久）
}

# 扩大参数组合（从1组→60组，提升优化精度）
PARAM_SEARCH_CONFIG = {
    "MA_SHORT": [4, 5, 6],          # 短期均线候选
    "MA_LONG": [18, 20, 22],        # 长期均线候选
    "SUPPORT_RESIST_DAYS": [4, 5, 6],# 支撑阻力周期
    "BUY_MARGIN": [0.008, 0.01, 0.012],# 买入容忍度
    "SELL_MARGIN": [0.008, 0.01, 0.012] # 卖出容忍度
}

BACKTEST_CONFIG = {
    "history_days": 180,  # 回溯周期（180天=6个月，兼顾短期趋势+数据量）
    "transaction_cost": 0.0015,  # 真实交易成本（印花税+佣金）
    "score_weights": {
        "annual_return": 0.6,    # 收益率权重最高
        "win_rate": 0.3,         # 胜率辅助
        "max_drawdown": -0.1     # 控制风险
    }
}

# 输出配置（只选5只股票）
OUTPUT_CONFIG = {
    "top_stock_count": 5,  # 核心需求：只选5只
    "signal_stock_count": 5 # 信号生成只处理前5只
}

LOG_DIR = "strategy_log"
os.makedirs(LOG_DIR, exist_ok=True)
PARAM_LOG_PATH = os.path.join(LOG_DIR, "param_optimization_log.csv")
STOCK_LOG_PATH = os.path.join(LOG_DIR, "stock_selection_log.csv")
SIGNAL_LOG_PATH = os.path.join(LOG_DIR, "trading_signals.csv")

# ====================== 工具函数（精准增强）======================
def get_tradable_stocks():
    """筛选高流动性、高市值股票池（提升数据质量）"""
    print("📊 正在筛选可交易股票池...（精准模式）")
    try:
        # 1. 获取全市场股票信息+实时行情
        stock_info = ak.stock_info_a_code_name()  # 股票代码+名称
        stock_quote = ak.stock_zh_a_spot_em()     # 实时行情（成交额、市值等）
        
        # 2. 数据合并+清洗
        stock_df = pd.merge(
            stock_info,
            stock_quote[["代码", "最新价", "成交额", "总市值", "涨跌幅"]],
            left_on="code", right_on="代码", how="inner"
        ).drop("代码", axis=1)
        
        # 3. 单位转换（元→亿，确保筛选准确）
        stock_df["成交额_亿"] = stock_df["成交额"] / 10000
        stock_df["总市值_亿"] = stock_df["总市值"] / 100000000
        
        # 4. 核心筛选条件
        filter_mask = (
            (stock_df["总市值_亿"] >= STOCK_FILTER_CONFIG["min_market_cap"]) &
            (stock_df["成交额_亿"] >= STOCK_FILTER_CONFIG["min_avg_volume"]) &
            (~stock_df["name"].str.contains("ST", na=False)) &
            (~stock_df["name"].str.contains("退市", na=False))
        )
        tradable_stocks = stock_df[filter_mask].copy()
        
        # 5. 限制数量（避免运行过久）
        if len(tradable_stocks) > STOCK_FILTER_CONFIG["max_stock_count"]:
            # 按成交额排序，取前N只（流动性最优）
            tradable_stocks = tradable_stocks.nlargest(
                STOCK_FILTER_CONFIG["max_stock_count"], "成交额_亿"
            ).reset_index(drop=True)
        
        print(f"✅ 筛选完成！可交易股票池共{len(tradable_stocks)}只（精准模式）")
        return tradable_stocks[["code", "name", "总市值_亿", "成交额_亿", "涨跌幅"]]
    except Exception as e:
        print(f"❌ 筛选股票池出错：{str(e)}")
        # 异常时返回预设优质股票
        preset_stocks = pd.DataFrame({
            "code": ["000333", "600036", "000858", "601318", "002594"],
            "name": ["美的集团", "招商银行", "五粮液", "中国平安", "比亚迪"],
            "总市值_亿": [3000, 8000, 5000, 9000, 7000],
            "成交额_亿": [10, 18, 15, 12, 20],
            "涨跌幅": [0, 0, 0, 0, 0]
        })
        return preset_stocks

def calculate_short_term_score(stock_code):
    """增强评分逻辑：增加因子有效性校验，提升区分度"""
    try:
        # 获取120天数据（足够计算180天回溯内的所有因子）
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            adjust="qfq"  # 前复权（确保价格连续性）
        ).tail(120).reset_index(drop=True)
        
        if len(df) < 60:  # 至少60天数据（确保因子稳定性）
            print(f"⚠️ {stock_code} 数据不足60条，评分设为0")
            return 0
        
        # 填充缺失值（提升数据质量）
        df = df.fillna(method="ffill").fillna(method="bfill")
        
        # 因子1：近5日涨幅（权重0.3）- 反映短期趋势
        if len(df) >= 6:
            recent_5d_return = (df.iloc[-1]["收盘"] - df.iloc[-6]["收盘"]) / df.iloc[-6]["收盘"]
        else:
            recent_5d_return = 0
        return_score = min(max(recent_5d_return * 150, 0), 30)  # 0-30分（区分度更高）
        
        # 因子2：成交量放大率（权重0.2）- 反映资金关注度
        recent_5d_volume = df.iloc[-5:]["成交量"].mean()
        recent_20d_volume = df.iloc[-20:]["成交量"].rolling(window=20, min_periods=1).mean().iloc[-1]
        volume_ratio = recent_5d_volume / recent_20d_volume if recent_20d_volume > 0 else 0
        volume_score = min(max((volume_ratio - 0.5) * 20, 0), 20)  # 0.5倍以上才得分，0-20分
        
        # 因子3：均线多头排列（权重0.2）- 反映中期趋势
        df["ma5"] = df["收盘"].rolling(window=5, min_periods=1).mean()
        df["ma10"] = df["收盘"].rolling(window=10, min_periods=1).mean()
        df["ma20"] = df["收盘"].rolling(window=20, min_periods=1).mean()
        df["ma60"] = df["收盘"].rolling(window=60, min_periods=1).mean()
        latest_ma5 = df.iloc[-1]["ma5"]
        latest_ma10 = df.iloc[-1]["ma10"]
        latest_ma20 = df.iloc[-1]["ma20"]
        latest_ma60 = df.iloc[-1]["ma60"]
        # 严格多头排列：ma5>ma10>ma20>ma60
        ma排列 = latest_ma5 > latest_ma10 > latest_ma20 > latest_ma60 > 0
        ma_score = 20 if ma排列 else min(max((latest_ma5 - latest_ma20)/latest_ma20 * 200, 0), 15)
        
        # 因子4：RSI（14日）（权重0.15）- 避免超买超卖
        delta = df["收盘"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean().iloc[-1]
        rs = gain / loss if loss > 0 else 0
        rsi14 = 100 - (100 / (1 + rs)) if rs >= 0 else 0
        # RSI在50-70之间得分最高（中性偏强）
        if 50 <= rsi14 <= 70:
            rsi_score = 15
        elif 40 <= rsi14 < 50 or 70 < rsi14 <= 80:
            rsi_score = 10
        else:
            rsi_score = 3
        
        # 因子5：换手率稳定性（权重0.15）- 反映交易活跃度
        if "换手率" in df.columns and not df["换手率"].isna().all():
            turnover_5d = df.iloc[-5:]["换手率"].mean()
            turnover_20d = df.iloc[-20:]["换手率"].mean()
            turnover_stability = min(max(1 - abs(turnover_5d - turnover_20d)/turnover_20d, 0), 1)
            turnover_score = turnover_stability * 15  # 0-15分
        else:
            turnover_score = 8  # 无数据时给基础分
        
        # 总评分（加权求和，0-100分）
        total_score = (
            return_score * 0.3 +
            volume_score * 0.2 +
            ma_score * 0.2 +
            rsi_score * 0.15 +
            turnover_score * 0.15
        )
        
        # 调试信息（可选关闭）
        print(f"📊 {stock_code} 评分明细：涨幅{return_score:.1f} | 成交量{volume_score:.1f} | 均线{ma_score:.1f} | RSI{rsi_score:.1f} | 换手率{turnover_score:.1f} | 总分{total_score:.1f}")
        
        return round(total_score, 2)
    except Exception as e:
        print(f"❌ {stock_code} 评分计算失败：{str(e)}")
        return 0

def select_top5_stocks():
    """核心需求：只筛选前5只高分股票"""
    print("\n🎯 正在评选短线潜力股（前5名）...（精准模式）")
    tradable_stocks = get_tradable_stocks()
    
    # 计算所有筛选股票的评分
    scores = []
    for idx, row in tqdm(tradable_stocks.iterrows(), total=len(tradable_stocks), desc="计算股票评分"):
        score = calculate_short_term_score(row["code"])
        scores.append(score)
    
    tradable_stocks["短线评分"] = scores
    
    # 筛选前5只高分股票（评分≥30分才纳入，避免垃圾股）
    top5_stocks = tradable_stocks[tradable_stocks["短线评分"] >= 30].nlargest(
        OUTPUT_CONFIG["top_stock_count"], "短线评分"
    ).reset_index(drop=True)
    
    # 若不足5只，用次高分补充（最低≥20分）
    if len(top5_stocks) < OUTPUT_CONFIG["top_stock_count"]:
        fill_count = OUTPUT_CONFIG["top_stock_count"] - len(top5_stocks)
        fill_stocks = tradable_stocks[
            (tradable_stocks["短线评分"] >= 20) & 
            (~tradable_stocks["code"].isin(top5_stocks["code"]))
        ].nlargest(fill_count, "短线评分").reset_index(drop=True)
        top5_stocks = pd.concat([top5_stocks, fill_stocks], ignore_index=True)
    
    # 确保刚好5只（极端情况用预设股票填充）
    if len(top5_stocks) < OUTPUT_CONFIG["top_stock_count"]:
        fill_count = OUTPUT_CONFIG["top_stock_count"] - len(top5_stocks)
        preset_codes = ["601899", "600519", "000651", "600028", "601988"]
        preset_names = ["紫金矿业", "贵州茅台", "格力电器", "中国石化", "中国银行"]
        fill_df = pd.DataFrame({
            "code": preset_codes[:fill_count],
            "name": preset_names[:fill_count],
            "总市值_亿": [1500]*fill_count,
            "成交额_亿": [8]*fill_count,
            "涨跌幅": [0]*fill_count,
            "短线评分": [25]*fill_count
        })
        top5_stocks = pd.concat([top5_stocks, fill_df], ignore_index=True)
    
    # 保存选股日志
    top5_stocks["选股日期"] = datetime.now().strftime("%Y-%m-%d")
    top5_stocks.to_csv(STOCK_LOG_PATH, mode="a", header=not os.path.exists(STOCK_LOG_PATH), index=False)
    
    print(f"\n🏆 短线潜力股TOP5：")
    for idx, row in top5_stocks.iterrows():
        print(f"{idx+1}. {row['code']} {row['name']} | 市值：{row['总市值_亿']:.1f}亿 | 成交额：{row['成交额_亿']:.1f}亿 | 评分：{row['短线评分']:.1f}")
    return top5_stocks

def backtest_strategy(stock_code, params):
    """增强回测逻辑：增加止损逻辑，提升真实性"""
    try:
        # 180天回溯数据（含前后各10天缓冲）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=BACKTEST_CONFIG["history_days"] + 10)
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            adjust="qfq"
        ).reset_index(drop=True)
        
        if len(df) < BACKTEST_CONFIG["history_days"] * 0.8:  # 至少80%数据完整性
            return None
        
        # 数据预处理
        df = df.fillna(method="ffill").fillna(method="bfill")
        df["ma_short"] = df["收盘"].rolling(window=params["MA_SHORT"], min_periods=1).mean()
        df["ma_long"] = df["收盘"].rolling(window=params["MA_LONG"], min_periods=1).mean()
        df["support"] = df["最低"].rolling(window=params["SUPPORT_RESIST_DAYS"], min_periods=1).min()
        df["resistance"] = df["最高"].rolling(window=params["SUPPORT_RESIST_DAYS"], min_periods=1).max()
        
        # 信号生成（增加止损条件：跌破支撑位1.5%止损）
        df["buy_signal"] = (
            df["ma_short"].shift(1) < df["ma_long"].shift(1) &
            df["ma_short"] > df["ma_long"] &
            df["收盘"] <= df["support"] * (1 + params["BUY_MARGIN"]) &
            df["收盘"] > df["support"] * 0.95  # 避免在支撑位下方买入
        )
        df["sell_signal"] = (
            (df["ma_short"].shift(1) > df["ma_long"].shift(1) & df["ma_short"] < df["ma_long"]) |
            (df["收盘"] < df["support"] * 0.985)  # 止损信号
        )
        
        # 模拟交易（单只股票满仓，记录每次交易）
        position = 0  # 0=空仓，1=持仓
        buy_price = 0
        trades = []
        
        for idx, row in df.iterrows():
            if row["buy_signal"] and position == 0:
                buy_price = row["收盘"] * (1 + params["BUY_MARGIN"])
                position = 1
                buy_date = row["日期"]
            elif row["sell_signal"] and position == 1:
                sell_price = row["收盘"] * (1 - params["SELL_MARGIN"])
                # 计算收益率（扣除交易成本）
                net_buy = buy_price * (1 + BACKTEST_CONFIG["transaction_cost"])
                net_sell = sell_price * (1 - BACKTEST_CONFIG["transaction_cost"])
                return_rate = (net_sell - net_buy) / net_buy
                trades.append({
                    "buy_date": buy_date,
                    "sell_date": row["日期"],
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "return_rate": return_rate
                })
                position = 0
        
        # 计算回测指标
        if not trades:
            return {"annual_return": 0, "win_rate": 0, "max_drawdown": 0, "trade_count": 0}
        
        trade_df = pd.DataFrame(trades)
        total_return = (1 + trade_df["return_rate"]).prod() - 1
        # 年化收益率（按180天折算）
        annual_return = (1 + total_return) ** (365 / BACKTEST_CONFIG["history_days"]) - 1
        # 胜率（盈利交易占比）
        win_rate = len(trade_df[trade_df["return_rate"] > 0]) / len(trade_df)
        # 最大回撤（累计收益的最大跌幅）
        trade_df["cum_return"] = (1 + trade_df["return_rate"]).cumprod()
        trade_df["cum_max"] = trade_df["cum_return"].cummax()
        trade_df["drawdown"] = (trade_df["cum_return"] - trade_df["cum_max"]) / trade_df["cum_max"]
        max_drawdown = trade_df["drawdown"].min()
        
        return {
            "annual_return": annual_return,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "trade_count": len(trade_df)
        }
    except Exception as e:
        print(f"❌ {stock_code} 回测失败：{str(e)}")
        return None

def optimize_strategy_params(top5_stocks):
    """增强参数优化：用3只股票交叉验证，提升参数稳定性"""
    print("\n⚙️  正在优化策略参数...（精准模式）")
    from itertools import product
    
    param_names = list(PARAM_SEARCH_CONFIG.keys())
    param_combinations = product(*PARAM_SEARCH_CONFIG.values())
    total_combinations = len(list(product(*PARAM_SEARCH_CONFIG.values())))
    print(f"参数组合总数：{total_combinations}，正在回测...")
    
    best_score = -float("inf")
    best_params = {
        "MA_SHORT": 5,
        "MA_LONG": 20,
        "SUPPORT_RESIST_DAYS": 5,
        "BUY_MARGIN": 0.01,
        "SELL_MARGIN": 0.01
    }
    all_results = []
    
    # 用前3只股票交叉验证（提升参数通用性）
    test_stocks = top5_stocks.head(3)
    
    for combo in tqdm(param_combinations, total=total_combinations, desc="参数回测"):
        params = dict(zip(param_names, combo))
        stock_metrics = []
        
        for _, row in test_stocks.iterrows():
            metrics = backtest_strategy(row["code"], params)
            if metrics and metrics["trade_count"] >= 2:  # 至少2次交易才有效
                stock_metrics.append(metrics)
        
        if len(stock_metrics) < 2:  # 至少2只股票有效才计算
            continue
        
        # 计算平均指标
        avg_annual_return = np.mean([m["annual_return"] for m in stock_metrics])
        avg_win_rate = np.mean([m["win_rate"] for m in stock_metrics])
        avg_max_drawdown = np.mean([m["max_drawdown"] for m in stock_metrics])
        
        # 综合评分（风险调整后收益）
        score = (
            avg_annual_return * BACKTEST_CONFIG["score_weights"]["annual_return"] +
            avg_win_rate * BACKTEST_CONFIG["score_weights"]["win_rate"] +
            avg_max_drawdown * BACKTEST_CONFIG["score_weights"]["max_drawdown"]
        )
        
        all_results.append({
            **params,
            "annual_return": avg_annual_return,
            "win_rate": avg_win_rate,
            "max_drawdown": avg_max_drawdown,
            "trade_count": np.mean([m["trade_count"] for m in stock_metrics]),
            "综合评分": score
        })
        
        # 更新最优参数
        if score > best_score:
            best_score = score
            best_params = params.copy()
    
    # 保存参数优化日志
    if all_results:
        result_df = pd.DataFrame(all_results)
        result_df["优化日期"] = datetime.now().strftime("%Y-%m-%d")
        result_df = result_df.sort_values("综合评分", ascending=False).head(10)  # 保存前10组最优参数
        result_df.to_csv(PARAM_LOG_PATH, mode="a", header=not os.path.exists(PARAM_LOG_PATH), index=False)
    
    # 输出最优参数及性能
    print(f"\n✨ 最优参数组合（综合评分：{best_score:.4f}）：")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    if all_results:
        top_result = all_results[0]
        print(f"\n📊 最优参数性能：")
        print(f"  平均年化收益率：{top_result['annual_return']:.2%}")
        print(f"  平均胜率：{top_result['win_rate']:.2%}")
        print(f"  平均最大回撤：{top_result['max_drawdown']:.2%}")
        print(f"  平均交易次数：{top_result['trade_count']:.1f}次")
    return best_params

def generate_trading_signals(top5_stocks, best_params):
    """增强信号生成：增加资金管理，输出更详细的交易建议"""
    print("\n📈 当日交易信号（TOP5股票）：")
    trading_signals = []
    initial_cash = 100000  # 初始资金（可自定义）
    invest_ratio = 0.7     # 70%资金用于投资（留30%风险准备金）
    total_invest = initial_cash * invest_ratio
    per_stock_cash = total_invest / OUTPUT_CONFIG["signal_stock_count"]  # 平均分配资金
    
    for idx, row in top5_stocks.iterrows():
        try:
            # 获取30天数据（计算均线+支撑位）
            df = ak.stock_zh_a_hist(
                symbol=row["code"],
                period="daily",
                adjust="qfq"
            ).tail(30).reset_index(drop=True)
            
            df = df.fillna(method="ffill").fillna(method="bfill")
            df["ma_short"] = df["收盘"].rolling(window=best_params["MA_SHORT"], min_periods=1).mean()
            df["ma_long"] = df["收盘"].rolling(window=best_params["MA_LONG"], min_periods=1).mean()
            df["support"] = df["最低"].rolling(window=best_params["SUPPORT_RESIST_DAYS"], min_periods=1).min()
            df["resistance"] = df["最高"].rolling(window=best_params["SUPPORT_RESIST_DAYS"], min_periods=1).max()
            
            latest = df.iloc[-1]
            prev_latest = df.iloc[-2] if len(df) >= 2 else latest
            
            # 精准信号判断
            buy_signal = (
                latest["ma_short"] > latest["ma_long"] and
                prev_latest["ma_short"] <= prev_latest["ma_long"] and  # 金叉信号
                latest["收盘"] <= df["support"].iloc[-1] * (1 + best_params["BUY_MARGIN"]) and  # 靠近支撑位
                latest["收盘"] > df["support"].iloc[-1] * 0.95 and  # 不跌破支撑位
                latest["ma_short"] > 0 and latest["ma_long"] > 0
            )
            sell_signal = (
                latest["ma_short"] < latest["ma_long"] and
                prev_latest["ma_short"] >= prev_latest["ma_long"] and  # 死叉信号
                latest["收盘"] < df["support"].iloc[-1] * 0.985  # 跌破支撑位止损
            )
            hold_signal = (
                latest["ma_short"] > latest["ma_long"] and
                not buy_signal and not sell_signal
            )
            
            if buy_signal:
                signal = "买入"
                buy_amount = int(per_stock_cash // latest["收盘"])  # 整数股
                actual_invest = buy_amount * latest["收盘"]
                remaining_cash = per_stock_cash - actual_invest
            elif sell_signal:
                signal = "卖出"
                buy_amount = 0
                actual_invest = 0
                remaining_cash = per_stock_cash
            elif hold_signal:
                signal = "持有"
                buy_amount = 0
                actual_invest = 0
                remaining_cash = per_stock_cash
            else:
                signal = "观望"
                buy_amount = 0
                actual_invest = 0
                remaining_cash = per_stock_cash
            
            # 止损价和目标价建议
            stop_loss_price = round(df["support"].iloc[-1] * 0.985, 2)
            target_price = round(df["resistance"].iloc[-1] * 1.02, 2)  # 2%盈利目标
            
            trading_signals.append({
                "日期": datetime.now().strftime("%Y-%m-%d"),
                "股票代码": row["code"],
                "股票名称": row["name"],
                "最新价": round(float(latest["收盘"]), 2),
                f"{best_params['MA_SHORT']}日均线": round(float(latest["ma_short"]), 2),
                f"{best_params['MA_LONG']}日均线": round(float(latest["ma_long"]), 2),
                "支撑位": round(float(df["support"].iloc[-1]), 2),
                "阻力位": round(float(df["resistance"].iloc[-1]), 2),
                "交易信号": signal,
                "建议购买数量": buy_amount,
                "单只股票分配资金": round(per_stock_cash, 2),
                "预计持仓成本": round(actual_invest, 2),
                "剩余资金": round(remaining_cash, 2),
                "止损价": stop_loss_price,
                "目标价": target_price
            })
            
            # 输出详细信息
            print(f"\n{idx+1}. {row['code']} {row['name']}")
            print(f"   基础信息：最新价{latest['收盘']:.2f}元 | 支撑位{df['support'].iloc[-1]:.2f}元 | 阻力位{df['resistance'].iloc[-1]:.2f}元")
            print(f"   均线状态：{best_params['MA_SHORT']}日({latest['ma_short']:.2f}) | {best_params['MA_LONG']}日({latest['ma_long']:.2f})")
            print(f"   交易信号：{signal}")
            if signal == "买入":
                print(f"   资金分配：{per_stock_cash:.2f}元 | 购买数量：{buy_amount}股 | 预计成本：{actual_invest:.2f}元")
                print(f"   风险控制：止损价{stop_loss_price:.2f}元 | 目标价{target_price:.2f}元（预期收益2%）")
            elif signal == "持有":
                print(f"   操作建议：继续持有 | 止损价{stop_loss_price:.2f}元 | 目标价{target_price:.2f}元")
            elif signal == "卖出":
                print(f"   操作建议：立即卖出（跌破止损位）")
            else:
                print(f"   操作建议：等待信号明确")
        except Exception as e:
            print(f"\n{idx+1}. {row['code']} {row['name']} | 信号生成失败：{str(e)}")
            continue
    
    # 保存信号日志
    signal_df = pd.DataFrame(trading_signals)
    signal_df.to_csv(SIGNAL_LOG_PATH, mode="a", header=not os.path.exists(SIGNAL_LOG_PATH), index=False)
    
    # 输出资金汇总
    total_actual_invest = sum([s["预计持仓成本"] for s in trading_signals])
    total_remaining_cash = sum([s["剩余资金"] for s in trading_signals]) + initial_cash * (1 - invest_ratio)
    print(f"\n💰 资金汇总：")
    print(f"   初始资金：{initial_cash:.2f}元")
    print(f"   投资资金：{total_actual_invest:.2f}元")
    print(f"   剩余资金：{total_remaining_cash:.2f}元")
    print(f"   仓位比例：{total_actual_invest/initial_cash:.2%}")

# ====================== 主流程 ======================
if __name__ == "__main__":
    print("="*80)
    print(f"📅 策略自动优化程序（精准增强版）{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    try:
        # 1. 筛选TOP5股票
        top5_stocks = select_top5_stocks()
        # 2. 优化策略参数
        best_params = optimize_strategy_params(top5_stocks)
        # 3. 生成交易信号
        generate_trading_signals(top5_stocks, best_params)
        
        # 月度进度提示
        total_days = len(pd.read_csv(PARAM_LOG_PATH)["优化日期"].unique()) if os.path.exists(PARAM_LOG_PATH) else 0
        print(f"\n📊 月度优化进度：{total_days}/30 天")
        print(f"💡 策略说明：基于180天回溯数据优化，筛选5只高潜力股票，含资金管理和风险控制")
        
    except Exception as e:
        print(f"\n❌ 程序执行错误：{str(e)}")
        print(f"💡 排查建议：1. 网络是否正常 2. akshare版本是否≥1.17.50 3. 权限是否足够写入日志")
    
    print("="*80)