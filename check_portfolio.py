import os
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

def check_portfolio():
    key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
    
    try:
        # Get Balance (Collateral)
        # Note: This usually returns the USDC balance available for trading in the Proxy
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        # Fetch balance/allowance
        # In newer clob versions, we might need to check specific endpoints
        # Let's try getting account state
        print(f"🔑 API Key Derived: {api_creds.api_key}")
        
        # Check USDC balance on the proxy
        # Since I don't know the exact method in this version, I'll try a few
        try:
            bal = client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
            print(f"💰 代理钱包余额 (Proxy USDC): ${float(bal['balance'])/1e6:.2f}")
        except Exception as e:
            print(f"Balance check 1 failed: {e}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_portfolio()
