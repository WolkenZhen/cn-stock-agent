# executor.py
from config import CURRENCY  # 仅依赖必要变量

def generate_core_suggestion(signal, market_info):
    """
    仅输出核心建议：股票名称+代码、短线买入区间、短线卖出区间
    """
    stock_code = market_info["stock_code"]
    stock_name = market_info["stock_name"]
    buy_range = market_info["short_buy_range"]
    sell_range = market_info["short_sell_range"]

    # 核心建议文本（简洁明了）
    core_suggestion = (
        f"🏆 核心交易建议（仅作分析，不涉及实际操作）\n"
        f"   =======================================\n"
        f"   建议状态：{'✅ 建议买入' if signal == 'BUY' else '⚠️  建议观望'}\n"
        f"   股票名称：{stock_name}\n"
        f"   股票代码：{stock_code}\n"
        f"   短线买入区间：{buy_range[0]} - {buy_range[1]} {CURRENCY}\n"
        f"   短线卖出区间：{sell_range[0]} - {sell_range[1]} {CURRENCY}\n"
        f"   =======================================\n"
        f"   📌 策略迭代提示：\n"
        f"      - 若建议观望，可调整config.py中STRATEGY_CONFIG参数（如MA_SHORT=6）\n"
        f"      - 若买入后盈利不佳，可缩小BUY_MARGIN（如0.005）或调整支撑阻力计算天数\n"
        f"      - 每月末统计信号准确率，优化参数组合\n"
    )

    return core_suggestion