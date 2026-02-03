from web3 import Web3
from eth_account import Account
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Config
RPC_URL = "https://polygon-rpc.com"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_ABI = '[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"}]'

def check():
    pk = os.getenv("PK") or os.getenv("PRIVATE_KEY")
    if not pk:
        print("❌ No Private Key found in .env")
        return

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ Failed to connect to Polygon RPC")
        return

    # Manual Override based on check_balance.py finding
    target_address = "0x45dCeb24119296fB57D06d83c1759cC191c3c96E" 
    print(f"👛 检查目标地址 (Funder/Safe): {target_address}")

    # MATIC Balance
    matic_wei = w3.eth.get_balance(target_address)
    matic = w3.from_wei(matic_wei, 'ether')
    print(f"🔹 MATIC: {matic:.4f}")

    # USDC Balance
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=json.loads(USDC_ABI))
    usdc_wei = usdc_contract.functions.balanceOf(target_address).call()
    decimals = usdc_contract.functions.decimals().call()
    usdc = usdc_wei / (10 ** decimals)
    print(f"💵 USDC : ${usdc:.2f}")

if __name__ == "__main__":
    check()
