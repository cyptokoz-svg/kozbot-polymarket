#!/usr/bin/env python3
"""检查账户连接和余额"""

import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

def main():
    private_key = os.getenv("PRIVATE_KEY")
    funder = os.getenv("FUNDER_ADDRESS")
    
    print("=" * 50)
    print("Polymarket 账户检查")
    print("=" * 50)
    print(f"Funder 地址: {funder}")
    print(f"私钥: {private_key[:8]}...{private_key[-4:]}")
    print()
    
    # 初始化客户端
    print("初始化 CLOB 客户端...")
    client = ClobClient(
        CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=2,  # Proxy wallet
        funder=funder
    )
    
    # 创建/获取 API 凭据
    print("获取 API 凭据...")
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    print(f"  ✓ API Key: {creds.api_key[:16]}...")
    
    # 测试连接
    print("\n测试 API 连接...")
    ok = client.get_ok()
    print(f"  ✓ CLOB OK: {ok}")
    
    # 获取余额（如果API支持）
    print("\n尝试获取账户信息...")
    try:
        # 尝试获取开放订单
        orders = client.get_orders()
        print(f"  ✓ 当前开放订单: {len(orders) if orders else 0}")
    except Exception as e:
        print(f"  (无法获取订单: {e})")
    
    print("\n" + "=" * 50)
    print("✓ 账户连接成功！准备就绪。")
    print("=" * 50)

if __name__ == "__main__":
    main()
