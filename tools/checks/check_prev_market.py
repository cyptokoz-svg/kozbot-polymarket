import requests
import json
from datetime import datetime

# 18:30 UTC timestamp was 1769538600
# So previous market (18:15 UTC) start timestamp was 1769537700
slug_prev = "btc-updown-15m-1769537700"
GAMMA_API = "https://gamma-api.polymarket.com"

def check_prev_market():
    resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug_prev})
    if resp.status_code == 200:
        data = resp.json()
        if data:
            # Look for resolution details in the markets
            m = data[0].get("markets", [])[0]
            print(json.dumps(m, indent=2))
        else:
            print("No data for prev market")

check_prev_market()
