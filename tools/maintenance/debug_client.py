import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)

print("Client attributes:", dir(client))
try:
    print("Exchange attributes:", dir(client.exchange))
except Exception as e:
    print("No exchange attr:", e)
