# explainer.py
from config import MARKET_TYPE, CURRENCY

def explain(signal, market_info):
    """
    简化版策略分析报告：聚焦策略逻辑+区间依据，支持迭代说明
    """
    # 提取核心数据
    stock_code = market_info["stock_code"]
    stock_name = market_info["stock_name"]
    latest_close = market_info["latest_close"]
    short_ma = market_info["short_ma"]
    long_ma = market_info["long_ma"]
    buy_range = market_info["short_buy_range"]
    sell_range = market_info["short_sell_range"]
    strategy_params = market_info["strategy_params"]
    data_source = market_info["data_source"]

    # 策略逻辑说明（可迭代修改）
    strategy_logic = (
        f"📋 当前迭代策略逻辑（第1版）\n"
        f"   1. 均线交叉策略：{strategy_params['MA_SHORT']}日均线上穿{strategy_params['MA_LONG']}日均线 → 买入信号\n"
        f"   2. 短线买入区间：近{strategy_params['SUPPORT_RESIST_DAYS']}日低点±{strategy_params['BUY_MARGIN']*100}%（限制在涨跌停内）\n"
        f"   3. 短线卖出区间：近{strategy_params['SUPPORT_RESIST_DAYS']}日高点±{strategy_params['SELL_MARGIN']*100}%（限制在涨跌停内）\n"
        f"   4. 迭代优化方向：调整MA_SHORT/MA_LONG周期、SUPPORT_RESIST_DAYS天数、BUY/SELL_MARGIN比例\n"
    )

    # 信号逻辑说明
    signal_logic = ""
    if signal == "BUY":
        signal_logic = (
            f"🔍 买入信号触发逻辑\n"
            f"   - 当前{strategy_params['MA_SHORT']}日均线（{short_ma} {CURRENCY}）> {strategy_params['MA_LONG']}日均线（{long_ma} {CURRENCY}），形成金叉\n"
            f"   - 当前价格{latest_close} {CURRENCY}未触及涨跌停，具备买入条件\n"
        )
    else:
        signal_logic = (
            f"🔍 观望信号触发逻辑\n"
            f"   - 当前{strategy_params['MA_SHORT']}日均线（{short_ma} {CURRENCY}）≤ {strategy_params['MA_LONG']}日均线（{long_ma} {CURRENCY}），未形成金叉\n"
            f"   - 趋势不明确，建议等待信号触发\n"
        )

    # 区间依据说明
    range_logic = (
        f"📊 区间计算依据（数据来源：{data_source}）\n"
        f"   - 短线买入区间：{buy_range[0]} - {buy_range[1]} {CURRENCY}（近{strategy_params['SUPPORT_RESIST_DAYS']}日低点±{strategy_params['BUY_MARGIN']*100}%）\n"
        f"   - 短线卖出区间：{sell_range[0]} - {sell_range[1]} {CURRENCY}（近{strategy_params['SUPPORT_RESIST_DAYS']}日高点±{strategy_params['SELL_MARGIN']*100}%）\n"
        f"   - 风险控制：区间已强制限制在当日涨跌停范围内\n"
    )

    # 迭代提示
    iteration_tip = (
        f"💡 一个月迭代建议\n"
        f"   1. 每日运行程序，记录信号准确性和区间有效性\n"
        f"   2. 每3-5天调整一次策略参数（如MA_SHORT改为6、BUY_MARGIN改为0.008）\n"
        f"   3. 迭代目标：提高买入信号准确率，优化卖出区间盈利空间\n"
        f"   4. 数据回溯：修改config.py中DATA_PERIOD为'30d'，回溯历史数据测试不同参数组合\n"
    )

    # 整合报告
    return (
        f"🤖 A股短线策略分析报告\n"
        f"   标的：{stock_code}（{stock_name}）| 市场：{MARKET_TYPE} | 货币：{CURRENCY}\n"
        f"\n{strategy_logic}\n{signal_logic}\n{range_logic}\n{iteration_tip}"
    )