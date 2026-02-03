import os
from web3 import Web3
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Polygon RPC
RPC_URL = "https://polygon-rpc.com"

# Contracts
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174" # USDC.e (Bridged)
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359" # Native USDC

# ABI for balanceOf
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

def check_vault():
    funder = os.getenv("FUNDER_ADDRESS")
    if not funder:
        print("❌ Error: FUNDER_ADDRESS not set in .env")
        return

    print(f"🔍 正在检查金库 (Vault): {funder}")
    
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ RPC Connection Failed")
        return

    total_usdc = 0.0

    # Check USDC.e
    try:
        contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        bal = contract.functions.balanceOf(funder).call()
        decimals = contract.functions.decimals().call()
        amount = bal / (10 ** decimals)
        print(f"💵 USDC.e (Bridged): ${amount:,.2f}")
        total_usdc += amount
    except Exception as e:
        print(f"⚠️ Failed to check USDC.e: {e}")

    # Check Native USDC
    try:
        contract = w3.eth.contract(address=USDC_NATIVE, abi=ERC20_ABI)
        bal = contract.functions.balanceOf(funder).call()
        decimals = contract.functions.decimals().call()
        amount = bal / (10 ** decimals)
        print(f"💵 USDC (Native): ${amount:,.2f}")
        total_usdc += amount
    except Exception as e:
        print(f"⚠️ Failed to check Native USDC: {e}")
        
    # Check MATIC (Gas)
    try:
        bal_wei = w3.eth.get_balance(funder)
        matic = w3.from_wei(bal_wei, 'ether')
        print(f"⛽ MATIC (Gas): {matic:.4f}")
    except Exception as e:
        print(f"⚠️ Failed to check MATIC: {e}")

    print("-" * 30)
    print(f"💰 总可用资金 (Total Vault): ${total_usdc:,.2f}")

if __name__ == "__main__":
    check_vault()
