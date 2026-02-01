import os
import json
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from dotenv import load_dotenv

load_dotenv()

def check_balance():
    print("Checking Polymarket Balance...")
    
    key = os.getenv("PRIVATE_KEY")
    if not key:
        print("❌ Error: PRIVATE_KEY not found in .env")
        return

    # Load API Creds if available
    creds = None
    if os.getenv("CLOB_API_KEY"):
        creds = ApiCreds(
            api_key=os.getenv("CLOB_API_KEY"),
            api_secret=os.getenv("CLOB_API_SECRET"),
            api_passphrase=os.getenv("CLOB_API_PASSPHRASE")
        )
        print("✅ Using API Credentials")

    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137, creds=creds)

    try:
        # Get Collateral Balance (USDC on Polymarket Proxy)
        # Note: get_balance_allowance returns {'balance': '1000000', 'allowance': '...'} in wei (6 decimals for USDC)
        resp = client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
        
        balance_wei = int(resp.get('balance', 0))
        balance_usdc = balance_wei / 1_000_000
        
        print(f"\n💰 余额 (USDC): ${balance_usdc:,.2f}")
        
        # Also check allowance
        allowance = int(resp.get('allowance', 0))
        if allowance == 0:
            print("⚠️ 警告: USDC 授权额度为 0 (需 approve)")
        else:
            print(f"✅ 授权状态: 正常")
            
    except Exception as e:
        print(f"❌ Failed to fetch balance: {e}")

if __name__ == "__main__":
    check_balance()
