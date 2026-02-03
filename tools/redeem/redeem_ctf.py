#!/usr/bin/env python3
"""
Polymarket Gasless Redeemer (Official SDK)
Uses py_clob_client to redeem winnings via Relayer (No MATIC needed).
"""

import os
import sys
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

def redeem_gasless(condition_id):
    key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
    if not key:
        print("❌ Error: Private Key not found.")
        return

    try:
        # Init Client (Polygon Mainnet)
        client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
        
        # In py_clob_client, we need to create API creds first to sign messages
        try:
            client.create_api_key() 
        except: 
            pass # Already exists or valid

        print(f"💰 Redeeming (Gasless) Condition: {condition_id}...")
        
        # Use exchange client to redeem
        # This sends a meta-transaction to Polymarket's relayer
        resp = client.exchange.redeem_positions(condition_id=condition_id)
        
        print(f"✅ Redeem Request Sent! TX Hash: {resp}")

    except Exception as e:
        print(f"❌ Redeem Failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 redeem_ctf.py <condition_id>")
    else:
        redeem_gasless(sys.argv[1])
