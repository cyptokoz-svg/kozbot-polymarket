#!/usr/bin/env python3
"""
自动赎回已结算市场的仓位
检查持仓，如果市场已结算且持有胜出方，自动赎回 USDC
"""

import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

CLOB_HOST = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CHAIN_ID = 137

def get_positions(address: str) -> list:
    """获取所有持仓"""
    resp = requests.get(
        f"{DATA_API}/positions",
        params={"user": address.lower()},
        timeout=15
    )
    return resp.json()

def get_market_info(condition_id: str) -> dict:
    """获取市场详细信息"""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"conditionId": condition_id},
            timeout=10
        )
        markets = resp.json()
        return markets[0] if markets else {}
    except:
        return {}

def check_redeemable(client: ClobClient, positions: list) -> list:
    """检查哪些仓位可以赎回"""
    redeemable = []
    
    for pos in positions:
        condition_id = pos.get('conditionId', '')
        if not condition_id:
            continue
        
        # 获取市场信息
        market = get_market_info(condition_id)
        if not market:
            continue
        
        # 检查是否已结算
        if not market.get('closed', False):
            continue
        
        winning_outcome = market.get('winningOutcome', '').lower()
        if not winning_outcome:
            continue
        
        # 检查是否持有胜出方
        outcome = pos.get('outcome', '').lower()
        size = float(pos.get('size', 0))
        
        if outcome == winning_outcome and size > 0:
            redeemable.append({
                'question': market.get('question', 'Unknown'),
                'condition_id': condition_id,
                'outcome': outcome,
                'size': size,
                'value': size  # 胜出方每 share 价值 $1
            })
    
    return redeemable

def redeem_positions(client: ClobClient, redeemable: list) -> list:
    """赎回仓位（返回结果列表）"""
    results = []
    
    for pos in redeemable:
        try:
            # Polymarket 的赎回是自动的，当市场结算后，
            # 胜出的 token 会自动变成 USDC
            # 但如果需要手动触发，可以通过 CTF 合约
            
            # 目前 py-clob-client 不直接支持 redeem
            # 这里记录可赎回的仓位
            results.append({
                'status': 'pending',
                'question': pos['question'][:50],
                'outcome': pos['outcome'],
                'value': pos['value']
            })
            
            print(f"💰 可赎回: {pos['question'][:50]}")
            print(f"   {pos['outcome'].upper()} x {pos['size']:.4f} = ${pos['value']:.2f}")
            
        except Exception as e:
            results.append({
                'status': 'error',
                'error': str(e)
            })
    
    return results

def main():
    print("=" * 60)
    print("Polymarket 自动赎回检查")
    print("=" * 60)
    
    private_key = os.getenv("PRIVATE_KEY")
    funder = os.getenv("FUNDER_ADDRESS")
    
    if not private_key or not funder:
        print("错误: 需要设置 PRIVATE_KEY 和 FUNDER_ADDRESS")
        return
    
    print(f"\n钱包: {funder[:10]}...{funder[-6:]}")
    
    # 初始化客户端
    client = ClobClient(
        CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=2,
        funder=funder
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    
    # 获取持仓
    print("\n获取持仓...")
    positions = get_positions(funder)
    print(f"总持仓数: {len(positions)}")
    
    if not positions:
        print("没有持仓")
        return
    
    # 检查可赎回
    print("\n检查可赎回仓位...")
    redeemable = check_redeemable(client, positions)
    
    if not redeemable:
        print("没有可赎回的仓位")
        print("\n当前持仓状态:")
        for pos in positions:
            outcome = pos.get('outcome', 'N/A')
            size = float(pos.get('size', 0))
            print(f"  • {size:.4f} {outcome} (市场未结算)")
        return
    
    # 显示可赎回
    print(f"\n发现 {len(redeemable)} 个可赎回仓位:")
    total_value = 0
    for pos in redeemable:
        print(f"  💰 {pos['question'][:40]}...")
        print(f"     {pos['outcome'].upper()} x {pos['size']:.4f} = ${pos['value']:.2f}")
        total_value += pos['value']
    
    print(f"\n总可赎回: ${total_value:.2f}")
    
    # 注意：实际赎回需要调用 CTF 合约
    print("\n注意: Polymarket 的已结算仓位通常会自动转为 USDC")
    print("如果没有自动转换，请在 polymarket.com 手动赎回")

if __name__ == "__main__":
    main()
