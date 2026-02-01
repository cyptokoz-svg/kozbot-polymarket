import os
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

# Test API connection
key = os.getenv("PRIVATE_KEY")
chain_id = 137

client = ClobClient("https://clob.polymarket.com", key=key, chain_id=chain_id)

print("Testing Level 1 Auth...")
try:
    # Try to derive API key
    creds = client.create_or_derive_api_creds()
    if creds:
        print(f"✅ API Key derived successfully!")
        print(f"API Key: {creds.api_key}")
        print(f"Secret: {creds.api_secret[:20]}...")
        print(f"Passphrase: {creds.api_passphrase[:20]}...")
        
        # Test Level 2 Auth
        client.set_api_creds(creds)
        print("\nTesting Level 2 Auth...")
        balance = client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
        print(f"✅ Balance: {balance}")
    else:
        print("❌ Failed to derive API key")
except Exception as e:
    print(f"❌ Error: {e}")
