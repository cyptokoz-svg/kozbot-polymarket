#!/usr/bin/env python3
"""
查询 Polymarket 交易所持仓和订单
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(".env")

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from btc_15m_bot_v3 import PolymarketBotV3

async def main():
    bot = PolymarketBotV3()
    
    print("=" * 50)
    print("🔍 Polymarket 持仓查询工具")
    print("=" * 50)
    
    # 查询持仓
    print("\n📊 查询交易所持仓...")
    positions = await bot.query_exchange_positions()
    
    if positions:
        print(f"\n找到 {len(positions)} 笔持仓:")
        for i, pos in enumerate(positions, 1):
            market = pos.get('market', 'N/A')
            side = pos.get('side', 'N/A')
            size = pos.get('size', 0)
            price = pos.get('avg_price', 0)
            pnl = pos.get('unrealized_pnl', 0)
            print(f"  {i}. {side} {size:.4f} 份 @ ${price:.2f}")
            print(f"     市场: {market[:50]}...")
            print(f"     未实现盈亏: ${pnl:.2f}")
            print()
    else:
        print("📭 无持仓")
    
    # 查询未成交订单
    print("\n📋 查询未成交订单...")
    orders = await bot.query_exchange_orders(status="OPEN")
    
    if orders:
        print(f"\n找到 {len(orders)} 笔未完成订单:")
        for i, order in enumerate(orders, 1):
            oid = order.get('id', 'N/A')
            side = order.get('side', 'N/A')
            price = order.get('price', 0)
            size = order.get('size', 0)
            filled = order.get('maker_amount', 0)
            remaining = size - filled
            print(f"  {i}. 订单ID: {oid}")
            print(f"     {side} {remaining:.4f} 份 @ ${price:.2f}")
            print(f"     已成交: {filled:.4f} / {size:.4f}")
            print()
    else:
        print("📭 无未成交订单")
    
    # 本地持仓对比
    print("\n💾 本地持仓记录:")
    if bot.positions:
        for i, pos in enumerate(bot.positions, 1):
            status = pos.get('status', 'N/A')
            dir = pos.get('direction', 'N/A')
            entry = pos.get('entry_price', 0)
            print(f"  {i}. {dir} @ ${entry:.2f} | 状态: {status}")
    else:
        print("  📭 无本地持仓记录")
    
    print("\n" + "=" * 50)
    print("查询完成")

if __name__ == "__main__":
    asyncio.run(main())
