from web3 import Web3
from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv()

# Get address from private key
pk = os.getenv("PRIVATE_KEY")
account = Account.from_key(pk)
print(f"Private Key Address: {account.address}")

print(f"Funder Address: {os.getenv('FUNDER_ADDRESS')}")

# Check if they match
if account.address.lower() == os.getenv("FUNDER_ADDRESS").lower():
    print("✅ Addresses match!")
else:
    print("❌ Addresses DO NOT match!")
    print("API key is tied to the private key address, not the funder address")
