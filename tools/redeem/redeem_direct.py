#!/usr/bin/env python3
"""
直接合约赎回（需要 MATIC 支付 gas）
"""
import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_abi import encode

load_dotenv(".env")

# Contract Addresses
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CONDITION_ID = "0x48ba5d9c429d865d71f0c3a400e715f113aafec7ee90bbe9c98ac221d70125e4"

# ABI for redeemPositions
CTF_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"}
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def check_balance():
    """检查钱包余额"""
    w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    pk = os.getenv("PRIVATE_KEY") or os.getenv("PK")
    
    if not pk:
        print("❌ 未设置私钥")
        return None, None
    
    account = Account.from_key(pk)
    matic_balance = w3.eth.get_balance(account.address)
    
    print(f"📊 钱包地址: {account.address}")
    print(f"💰 MATIC 余额: {w3.from_wei(matic_balance, 'ether'):.4f} MATIC")
    
    if matic_balance < w3.to_wei(0.01, 'ether'):
        print("⚠️  MATIC 余额不足（至少需要 0.01 MATIC）")
        print("   请从交易所充值 MATIC 到该地址")
        return None, None
    
    return w3, account

def redeem_direct():
    """执行直接赎回"""
    print("=" * 60)
    print("🔗 直接合约赎回（需 MATIC Gas）")
    print("=" * 60)
    
    w3, account = check_balance()
    if not w3 or not account:
        return False
    
    print(f"\n📋 赎回详情:")
    print(f"   Condition ID: {CONDITION_ID}")
    print(f"   CTF Exchange: {CTF_EXCHANGE}")
    print(f"   预计 Gas: ~0.005 MATIC")
    
    print(f"\n⚠️  即将提交交易到 Polygon 网络...")
    
    try:
        # 初始化合约
        ctf_contract = w3.eth.contract(
            address=Web3.to_checksum_address(CTF_EXCHANGE),
            abi=CTF_ABI
        )
        
        # 构建交易参数
        parent_id = bytes.fromhex("0" * 64)  # Empty bytes32
        cond_id_bytes = bytes.fromhex(CONDITION_ID.replace("0x", ""))
        index_sets = [1, 2]  # Yes and No outcomes
        
        # 构建交易
        tx = ctf_contract.functions.redeemPositions(
            USDC_ADDRESS,
            parent_id,
            cond_id_bytes,
            index_sets
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 137
        })
        
        # 签名
        signed_tx = w3.eth.account.sign_transaction(tx, account.key)
        
        # 发送
        print("📡 发送交易中...")
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"⏳ 等待确认...")
        print(f"   TX Hash: {tx_hash.hex()}")
        
        # 等待回执
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            print(f"\n✅ 赎回成功!")
            print(f"   Gas Used: {receipt['gasUsed']}")
            print(f"   TX: https://polygonscan.com/tx/{tx_hash.hex()}")
            return True
        else:
            print(f"\n❌ 交易失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 赎回失败: {e}")
        return False

if __name__ == "__main__":
    success = redeem_direct()
    sys.exit(0 if success else 1)
