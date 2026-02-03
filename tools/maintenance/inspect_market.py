import requests
import json

GAMMA_API = "https://gamma-api.polymarket.com"

def check_market():
    # Fetch a recent BTC market slug to inspect structure
    slug = "btc-updown-15m-1769538600" # From previous log
    # Or just search
    resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug})
    if resp.status_code == 200:
        data = resp.json()
        if data:
            print(json.dumps(data[0], indent=2))
        else:
            print("No data found for slug")

check_market()
