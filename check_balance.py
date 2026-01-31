#!/usr/bin/env python3
"""检查 Polymarket 钱包余额"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

funder = os.getenv("FUNDER_ADDRESS")
print(f"检查钱包: {funder}\n")

# 1. 通过 Data API 获取用户持仓
print("=" * 40)
print("持仓信息")
print("=" * 40)
try:
    resp = requests.get(
        f"https://data-api.polymarket.com/positions",
        params={"user": funder.lower()},
        timeout=15
    )
    positions = resp.json()
    print(f"持仓数量: {len(positions)}")
    for p in positions[:10]:
        market = p.get('market', {})
        print(f"  • {market.get('question', 'Unknown')[:60]}")
        print(f"    数量: {p.get('size', 0)}, 方向: {p.get('outcome', 'N/A')}")
except Exception as e:
    print(f"获取持仓失败: {e}")

# 2. Polygon USDC 余额
print("\n" + "=" * 40)
print("Polygon 链上余额")
print("=" * 40)

# USDC.e on Polygon (bridged USDC)
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
# Native USDC on Polygon
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

for name, contract in [("USDC.e", USDC_E), ("USDC", USDC_NATIVE)]:
    try:
        resp = requests.get(
            "https://api.polygonscan.com/api",
            params={
                "module": "account",
                "action": "tokenbalance",
                "contractaddress": contract,
                "address": funder,
                "tag": "latest"
            },
            timeout=10
        )
        data = resp.json()
        if data.get("status") == "1":
            balance_wei = int(data.get("result", 0))
            balance = balance_wei / 1e6
            print(f"{name}: ${balance:,.2f}")
    except Exception as e:
        print(f"{name}: 查询失败 - {e}")

# MATIC
try:
    resp = requests.get(
        "https://api.polygonscan.com/api",
        params={
            "module": "account",
            "action": "balance",
            "address": funder,
            "tag": "latest"
        },
        timeout=10
    )
    data = resp.json()
    if data.get("status") == "1":
        balance_wei = int(data.get("result", 0))
        balance = balance_wei / 1e18
        print(f"MATIC: {balance:.4f}")
except Exception as e:
    print(f"MATIC: 查询失败 - {e}")

# 3. 检查 Polymarket 交易历史
print("\n" + "=" * 40)
print("最近交易")
print("=" * 40)
try:
    resp = requests.get(
        f"https://data-api.polymarket.com/activity",
        params={"user": funder.lower(), "limit": 5},
        timeout=15
    )
    activities = resp.json()
    if activities:
        for a in activities[:5]:
            print(f"  • {a.get('type', 'Unknown')}: {a.get('market', {}).get('question', '')[:40]}")
    else:
        print("  (无交易记录)")
except Exception as e:
    print(f"获取交易历史失败: {e}")

print("\n" + "=" * 40)
