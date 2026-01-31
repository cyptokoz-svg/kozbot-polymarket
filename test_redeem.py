import os
import sys
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

# Load env
load_dotenv()

def test_redeem():
    key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
    if not key:
        print("❌ Error: No Private Key found in environment variables.")
        return

    print("🔑 Private Key found. Initializing Client...")
    
    try:
        # Chain ID 137 = Polygon Mainnet
        client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
        
        # 1. Test Auth (Get Balance)
        # Note: derive_api_key might be needed first if not set up, 
        # but let's try a simple call.
        print("📡 Testing connection...")
        try:
            # We don't have a direct 'get_balance' in some versions, 
            # let's try getting api keys as a ping
            creds = client.get_api_keys()
            print("✅ Connection Successful! API Keys retrieved.")
        except Exception as e:
            print(f"⚠️ Connection Warning (might need L2 auth): {e}")

        # 2. Test Redeem
        # We need a condition_id. Let's use a dummy one just to see if the function exists and runs.
        # This will likely fail with "Condition not resolved" or "No winnings", which is GOOD.
        dummy_condition = "0x4363294324903249320493204932049320493204932049320493204932049320"
        
        print(f"💰 Attempting Dry-Run Redeem on dummy condition: {dummy_condition}...")
        resp = client.redeem_winning_positions(dummy_condition)
        print(f"✅ Redeem call executed. Response: {resp}")

    except Exception as e:
        print(f"❌ Test Failed: {e}")

if __name__ == "__main__":
    test_redeem()
