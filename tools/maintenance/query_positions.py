#!/usr/bin/env python3
"""
查询 Polymarket 交易所持仓和订单
"""
import os
import asyncio
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DATA_API = "https://data-api.polymarket.com"

async def main():
    private_key = os.getenv("PRIVATE_KEY")
    funder = os.getenv("FUNDER_ADDRESS")
    if not private_key:
        print("❌ Missing PRIVATE_KEY")
        return
    client = None
    try:
        if funder:
            client = ClobClient("https://clob.polymarket.com", key=private_key, chain_id=POLYGON, signature_type=2, funder=funder)
            client.set_api_creds(client.create_or_derive_api_creds())
        else:
            client = ClobClient("https://clob.polymarket.com", key=private_key, chain_id=POLYGON)
            client.set_api_creds(client.derive_api_key())
    except Exception as e:
        print(f"❌ Failed to init CLOB client: {e}")
        return
    
    print("=" * 50)
    print("🔍 Polymarket 持仓查询工具")
    print("=" * 50)
    
    # 查询持仓
    print("\n📊 查询交易所持仓...")
    positions = []
    if funder:
        try:
            resp = requests.get(f"{DATA_API}/positions", params={"user": funder.lower()}, timeout=15)
            positions = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            print(f"查询持仓失败: {e}")
    
    if positions:
        print(f"\n找到 {len(positions)} 笔持仓:")
        for i, pos in enumerate(positions, 1):
            market = pos.get('market', {})
            question = market.get('question', 'N/A')
            side = pos.get('outcome', 'N/A')
            size = float(pos.get('size', 0) or 0)
            print(f"  {i}. {side} {size:.4f} 份")
            print(f"     市场: {question[:50]}...")
            print()
    else:
        print("📭 无持仓")
    
    # 查询未成交订单
    print("\n📋 查询未成交订单...")
    orders = []
    try:
        orders = client.get_orders(status="OPEN")
    except Exception:
        try:
            orders = client.get_orders()
        except Exception as e:
            print(f"查询订单失败: {e}")
    
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
    
    print("\n" + "=" * 50)
    print("查询完成")

if __name__ == "__main__":
    asyncio.run(main())
