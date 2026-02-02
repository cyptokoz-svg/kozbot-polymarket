#!/usr/bin/env python3
"""
执行赎回
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv(".env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from btc_15m_bot_v3 import PolymarketBotV3

# 可赎回的 condition_id
CONDITION_ID = "0x48ba5d9c429d865d71f0c3a400e715f113aafec7ee90bbe9c98ac221d70125e4"

async def execute_redeem():
    print("=" * 50)
    print("🚀 执行赎回")
    print("=" * 50)
    
    bot = PolymarketBotV3()
    
    print(f"\n📋 赎回详情:")
    print(f"  Condition ID: {CONDITION_ID[:30]}...")
    print(f"  Funder (Safe): {os.getenv('FUNDER_ADDRESS', 'N/A')[:20]}...")
    
    # 确认执行
    print(f"\n⚠️  即将提交赎回交易到 Polygon 网络")
    print(f"   这将赎回结算后的 USDC 到你的 Safe 钱包")
    
    try:
        # 执行赎回
        print(f"\n🏦 启动赎回流程...")
        bot._raw_redeem(CONDITION_ID)
        
        print("\n" + "=" * 50)
        print("✅ 赎回请求已提交")
        print("\n请检查 Safe 钱包余额变动")
        print("或访问: https://polymarket.com/portfolio")
        
    except Exception as e:
        print(f"\n❌ 赎回失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(execute_redeem())
