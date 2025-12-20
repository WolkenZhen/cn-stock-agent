# trading_signal.py
import pandas as pd
import akshare as ak  # 核心数据源
from config import (
    TARGET_SYMBOL, TARGET_STOCK_NAME,
    MA_SHORT, MA_LONG, SUPPORT_RESIST_DAYS,
    LIMIT_UP_DOWN, AUTO_ADJUST, BUY_MARGIN, SELL_MARGIN
)

def generate_signal():
    """
    极简逻辑：用AKShare默认返回最近100条日线数据，去掉手动日期，避免格式错误
    """
    # ====================== 获取A股数据（终极简化，必成功）======================
    print(f"   📡 正在获取A股{TARGET_SYMBOL}（{TARGET_STOCK_NAME}）日线数据...")
    print(f"   📅 自动获取最近100条日线数据（前复权）")
    
    try:
        # 调用AKShare接口（去掉日期参数，用默认值，避免格式错误）
        # 接口：stock_zh_a_hist（东方财富），默认返回最近100条日线
        df = ak.stock_zh_a_hist(
            symbol=TARGET_SYMBOL,
            period="daily",          # 日线参数（固定'daily'）
            adjust="qfq" if AUTO_ADJUST else "none"  # 前复权
        )

        # 数据验证（确保接口返回有效数据）
        if df.empty:
            raise ValueError("接口返回空数据，尝试更换接口...")
        
        # 强制提取核心列（兼容不同AKShare版本的列名差异）
        required_cols = ["日期", "收盘", "最高", "最低"]
        if not all(col in df.columns for col in required_cols):
            # 若列名是英文（部分版本可能返回英文列名），直接用英文
            df = df[["Date", "Close", "High", "Low"]].copy()
            df.columns = ["日期", "收盘", "最高", "最低"]
        
        # 数据处理（极简逻辑）
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期").reset_index(drop=True)
        
        # 确保数据量足够（≥MA_LONG=20条）
        if len(df) < MA_LONG:
            raise ValueError(f"有效数据{len(df)}条 < 20条，接口异常")
        
        # 提取关键数据
        latest_data = df.iloc[-1]
        latest_close = round(float(latest_data["收盘"]), 2)
        latest_date = latest_data["日期"].strftime("%Y-%m-%d")
        
        print(f"   ✅ 数据获取成功！")
        print(f"   📊 最新交易日：{latest_date}，最新收盘价：{latest_close}元")
        print(f"   📈 共获取{len(df)}条有效日线数据（前复权）")

    except Exception as e:
        # 若第一个接口失败，直接换用备用接口（akshare.stock_zh_a_hist_min_em）
        print(f"   ⚠️  第一个接口失败，尝试备用接口...")
        try:
            # 备用接口：分钟级数据转日线（东方财富，稳定性更高）
            df = ak.stock_zh_a_hist_min_em(
                symbol=TARGET_SYMBOL,
                period="1d",  # 1d=日线
                adjust="qfq"
            )
            if df.empty:
                raise ValueError("备用接口也返回空数据")
            
            # 处理备用接口数据
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.sort_values("日期").reset_index(drop=True)
            latest_data = df.iloc[-1]
            latest_close = round(float(latest_data["收盘"]), 2)
            latest_date = latest_data["日期"].strftime("%Y-%m-%d")
            
            print(f"   ✅ 备用接口数据获取成功！")
            print(f"   📊 最新交易日：{latest_date}，最新收盘价：{latest_close}元")
            print(f"   📈 共获取{len(df)}条有效日线数据（前复权）")
        except Exception as e2:
            # 终极错误提示，直接给出可执行方案
            raise RuntimeError(
                f"所有接口均失败！详细原因：\n"
                f"主接口错误：{str(e)}\n"
                f"备用接口错误：{str(e2)}\n"
                f"终极解决方案（直接复制执行）：\n"
                f"1. 卸载所有相关包：\n"
                f"   pip uninstall -y akshare pandas yfinance urllib3\n"
                f"2. 重新安装指定版本（确保兼容性）：\n"
                f"   pip install akshare==1.17.50 pandas==2.1.4 urllib3==1.26.16 -i https://pypi.tuna.tsinghua.edu.cn/simple\n"
                f"3. 运行程序时关闭代理，确保网络是纯国内IP\n"
                f"4. 若仍失败，直接使用以下测试代码验证AKShare是否可用：\n"
                f"   import akshare as ak\n"
                f"   df = ak.stock_zh_a_hist(symbol='000333', period='daily', adjust='qfq')\n"
                f"   print(df.head())"
            )

    # ====================== 核心指标计算（极简逻辑）======================
    # 计算均线
    df["ma_short"] = df["收盘"].rolling(window=MA_SHORT, min_periods=1).mean()
    df["ma_long"] = df["收盘"].rolling(window=MA_LONG, min_periods=1).mean()
    
    # 提取关键指标
    short_ma = round(float(df.iloc[-1]["ma_short"]), 2)
    long_ma = round(float(df.iloc[-1]["ma_long"]), 2)
    prev_close = round(float(df.iloc[-2]["收盘"]), 2) if len(df) >= 2 else latest_close
    limit_up = round(prev_close * (1 + LIMIT_UP_DOWN), 2)
    limit_down = round(prev_close * (1 - LIMIT_UP_DOWN), 2)
    
    # 近N日高低点
    recent_df = df.tail(SUPPORT_RESIST_DAYS)
    recent_low = round(float(recent_df["最低"].min()), 2)
    recent_high = round(float(recent_df["最高"].max()), 2)
    
    # 买入/卖出区间
    buy_low = max(round(recent_low * (1 - BUY_MARGIN), 2), limit_down)
    buy_high = min(round(recent_low * (1 + BUY_MARGIN), 2), limit_up)
    sell_low = max(round(recent_high * (1 - SELL_MARGIN), 2), limit_down)
    sell_high = min(round(recent_high * (1 + SELL_MARGIN), 2), limit_up)

    # ====================== 生成信号======================
    signal = "BUY" if short_ma > long_ma else "HOLD"

    # ====================== 返回结果======================
    return signal, {
        "stock_code": TARGET_SYMBOL,
        "stock_name": TARGET_STOCK_NAME,
        "latest_close": latest_close,
        "short_ma": short_ma,
        "long_ma": long_ma,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "short_buy_range": (buy_low, buy_high),
        "short_sell_range": (sell_low, sell_high),
        "strategy_params": {
            "MA_SHORT": MA_SHORT,
            "MA_LONG": MA_LONG,
            "SUPPORT_RESIST_DAYS": SUPPORT_RESIST_DAYS,
            "BUY_MARGIN": BUY_MARGIN,
            "SELL_MARGIN": SELL_MARGIN
        },
        "data_source": "AKShare（东方财富·前复权）",
        "last_updated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    }