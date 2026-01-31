#!/usr/bin/env python3
"""
Test Polymarket API connection and find BTC markets (no auth needed)
"""

import requests
from py_clob_client.client import ClobClient

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

def test_clob_connection():
    """Test basic CLOB connection"""
    print("Testing CLOB API...")
    client = ClobClient(CLOB_HOST)  # Read-only, no auth
    
    ok = client.get_ok()
    server_time = client.get_server_time()
    
    print(f"  ✓ CLOB OK: {ok}")
    print(f"  ✓ Server time: {server_time}")
    return True

def find_btc_markets():
    """Find active BTC 15-min markets"""
    print("\nSearching for BTC 15-minute markets...")
    
    resp = requests.get(
        f"{GAMMA_API}/markets",
        params={
            "active": "true",
            "closed": "false",
            "limit": 200
        },
        timeout=15
    )
    resp.raise_for_status()
    markets = resp.json()
    
    btc_markets = []
    for market in markets:
        question = market.get("question", "").lower()
        if "bitcoin" in question and ("15" in question or "15m" in question):
            btc_markets.append(market)
    
    if btc_markets:
        print(f"  ✓ Found {len(btc_markets)} BTC market(s):")
        for m in btc_markets[:3]:  # Show first 3
            print(f"    - {m.get('question', 'Unknown')}")
            print(f"      Prices: {m.get('outcomePrices', 'N/A')}")
            print(f"      Volume: ${float(m.get('volume', 0)):,.2f}")
            print(f"      End: {m.get('endDate', 'N/A')}")
    else:
        print("  ⚠ No active BTC 15-min markets found right now")
        print("    (They might be between intervals)")
    
    return btc_markets

def get_btc_price():
    """Get current BTC price"""
    print("\nGetting BTC price...")
    resp = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin", "vs_currencies": "usd"},
        timeout=10
    )
    resp.raise_for_status()
    price = resp.json()["bitcoin"]["usd"]
    print(f"  ✓ BTC/USD: ${price:,.2f}")
    return price

def main():
    print("=" * 50)
    print("Polymarket BTC Bot - Connection Test")
    print("=" * 50)
    
    try:
        test_clob_connection()
        get_btc_price()
        find_btc_markets()
        
        print("\n" + "=" * 50)
        print("✓ All tests passed! Ready to trade.")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
