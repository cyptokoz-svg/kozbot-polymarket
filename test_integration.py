import logging
import sys
import os

# 确保能找到模块
sys.path.append(os.getcwd())

# 调整日志级别以便看到 info
logging.basicConfig(level=logging.INFO)

from btc_15m_bot_v3 import PolymarketBotV3 as PolymarketBot

def test_redeem():
    print("🧪 [测试启动] 正在验证自动赎回模块...")
    
    # 初始化机器人实例
    try:
        bot = PolymarketBot()
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    # 使用已知的 Condition ID (之前赢的那单)
    test_id = "0x48ba5d9c429d865d71f0c3a400e715f113aafec7ee90bbe9c98ac221d70125e4"
    
    print(f"🎯 模拟触发赎回: ID {test_id[:8]}...")
    
    # 调用新的赎回函数
    bot._raw_redeem(test_id)
    
    print("✅ [测试完成] 请检查上方是否有 '赎回指令已构造' 的日志")

if __name__ == "__main__":
    test_redeem()
