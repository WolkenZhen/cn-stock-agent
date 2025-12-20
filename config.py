# config.py
# 策略迭代核心参数（极简配置，避免参数冲突）
STRATEGY_CONFIG = {
    "MA_SHORT": 5,          # 短期均线周期（可迭代）
    "MA_LONG": 20,          # 长期均线周期（可迭代）
    "SUPPORT_RESIST_DAYS": 5,  # 支撑/阻力计算天数（可迭代）
    "LIMIT_UP_DOWN": 0.1,   # 涨跌停比例
    "BUY_MARGIN": 0.01,     # 买入区间margin（可迭代）
    "SELL_MARGIN": 0.01,    # 卖出区间margin（可迭代）
    "AUTO_ADJUST": True     # 前复权
}

# 必选：美的集团（000333），确保接口兼容
TARGET_SYMBOL = "000333"
TARGET_STOCK_NAME = "美的集团（深市，家电龙头）"

# 市场信息（固定，无需推导）
MARKET_TYPE = "中国A股"
CURRENCY = "人民币（CNY）"
TRADING_HOURS = "北京时间 9:30-11:30 | 13:00-15:00"

# 策略参数快捷引用
MA_SHORT = STRATEGY_CONFIG["MA_SHORT"]
MA_LONG = STRATEGY_CONFIG["MA_LONG"]
SUPPORT_RESIST_DAYS = STRATEGY_CONFIG["SUPPORT_RESIST_DAYS"]
LIMIT_UP_DOWN = STRATEGY_CONFIG["LIMIT_UP_DOWN"]
BUY_MARGIN = STRATEGY_CONFIG["BUY_MARGIN"]
SELL_MARGIN = STRATEGY_CONFIG["SELL_MARGIN"]
AUTO_ADJUST = STRATEGY_CONFIG["AUTO_ADJUST"]