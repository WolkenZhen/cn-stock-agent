# main.py
import sys
from datetime import datetime
from config import (
    TARGET_SYMBOL, TARGET_STOCK_NAME, MARKET_TYPE,
    CURRENCY, TRADING_HOURS, STRATEGY_CONFIG
)
from trading_signal import generate_signal
from explainer import explain
from executor import generate_core_suggestion

def print_separator():
    """打印分隔线，优化输出格式"""
    print("\n" + "="*80 + "\n")

def main():
    # 启动信息
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 A股短线策略分析工具（支持一个月迭代优化）")
    print(f"🌍 基础配置：")
    print(f"   - 分析标的：{TARGET_SYMBOL}（{TARGET_STOCK_NAME}）")
    print(f"   - 市场类型：{MARKET_TYPE} | 交易时间：{TRADING_HOURS}")
    print(f"   - 策略参数（可迭代修改）：")
    for key, value in STRATEGY_CONFIG.items():
        print(f"     · {key}：{value}")
    print_separator()

    try:
        # 步骤1：生成策略信号和市场信息
        print(f"📊 [步骤1/3] 执行A股策略分析（数据+指标计算）...")
        signal, market_info = generate_signal()
        print(f"   ✅ 策略分析完成！当前信号：【{signal}】")
        print(f"   核心数据预览：")
        print(f"      - 当前价格：{market_info['latest_close']} {CURRENCY}")
        print(f"      - {STRATEGY_CONFIG['MA_SHORT']}/{STRATEGY_CONFIG['MA_LONG']}日均线：{market_info['short_ma']}/{market_info['long_ma']} {CURRENCY}")
        print(f"      - 涨跌停范围：{market_info['limit_down']} - {market_info['limit_up']} {CURRENCY}")
        print_separator()

        # 步骤2：生成策略分析报告（支持迭代说明）
        print(f"📋 [步骤2/3] 生成策略迭代分析报告...")
        analysis_report = explain(signal, market_info)
        print(analysis_report)
        print_separator()

        # 步骤3：输出核心交易建议
        print(f"💡 [步骤3/3] 输出核心交易建议...")
        core_suggestion = generate_core_suggestion(signal, market_info)
        print(core_suggestion)
        print_separator()

        # 结束提示
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 分析完成！")
        print(f"⚠️  免责声明：本工具仅提供策略分析和建议，不构成任何投资决策，股市有风险，投资需谨慎！")
        print(f"📌 迭代优化提示：修改config.py中STRATEGY_CONFIG参数，每日运行测试，一个月后统计最优参数组合")

    except Exception as e:
        # 异常处理
        print_separator()
        print(f"❌ 程序执行失败：{str(e)}")
        print(f"💡 排查建议：")
        if "AKShare" in str(e) or "Yahoo Finance" in str(e):
            print(f"   - 检查网络连接是否正常（无需科学上网）")
            print(f"   - 更换config.py中的TARGET_SYMBOL（如000858五粮液）")
            print(f"   - 延长DATA_PERIOD（如改为60天）")
        else:
            print(f"   - 检查依赖包是否安装完整（pip install -r requirements.txt）")
            print(f"   - 确认股票代码正确（沪市6开头，深市0/3开头）")
        print_separator()
        sys.exit(1)

if __name__ == "__main__":
    main()