import os
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("PRIVATE_KEY")
chain_id = 137

client = ClobClient("https://clob.polymarket.com", key=key, chain_id=chain_id)

print("Creating new API key...")
try:
    # Create new API key
    creds = client.create_api_key()
    if creds:
        print(f"✅ New API Key created!")
        print(f"CLOB_API_KEY={creds.api_key}")
        print(f"CLOB_API_SECRET={creds.api_secret}")
        print(f"CLOB_API_PASSPHRASE={creds.api_passphrase}")
    else:
        print("❌ Failed to create API key")
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTrying to derive existing key...")
    try:
        creds = client.derive_api_key()
        if creds:
            print(f"✅ API Key derived!")
            print(f"CLOB_API_KEY={creds.api_key}")
            print(f"CLOB_API_SECRET={creds.api_secret}")
            print(f"CLOB_API_PASSPHRASE={creds.api_passphrase}")
    except Exception as e2:
        print(f"❌ Derive also failed: {e2}")
