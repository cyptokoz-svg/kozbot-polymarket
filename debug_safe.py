import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv("polymarket-bot/.env")
key = os.getenv("PRIVATE_KEY")
client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)

print(f"EOA (Signer): {client.get_address()}") # The wallet derived from PK
try:
    # In some versions/configs this might return the Safe address if derived
    print(f"Collateral: {client.get_collateral_address()}") 
    print(f"Exchange: {client.get_exchange_address()}")
    print(f"Conditional: {client.get_conditional_address()}")
except:
    pass
