import os
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

def check():
    key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
    
    try:
        # Just try creating creds (needed for L2)
        client.set_api_creds(client.create_or_derive_api_creds())
        
        # Get collateral balance
        # Usually asset_type is 'COLLATERAL'
        # The method might be get_balance_allowance
        resp = client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
        print(resp)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
