import os
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv("polymarket-bot/.env")

pk = os.getenv("PRIVATE_KEY")
if not pk:
    print("No Private Key")
    exit()

account = Account.from_key(pk)
address = account.address
print(f"Address: {address}")

# Polygon RPC
w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))

if w3.is_connected():
    balance = w3.eth.get_balance(address)
    matic = w3.from_wei(balance, 'ether')
    print(f"MATIC Balance: {matic}")
    
    if matic < 0.01:
        print("⚠️ Warning: Low MATIC for gas!")
    else:
        print("✅ Gas is sufficient.")
else:
    print("❌ RPC Connection Failed")
