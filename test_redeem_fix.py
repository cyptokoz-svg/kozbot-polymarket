#!/usr/bin/env python3
"""
Test script for the fixed redemption functionality
Tests connection, balance checks, and mock redemption
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load env
load_dotenv()

def test_connections():
    """Test RPC and basic connectivity"""
    from web3 import Web3
    
    RPC_ENDPOINTS = [
        "https://polygon-rpc.com",
        "https://rpc.ankr.com/polygon",
        "https://polygon.llamarpc.com",
    ]
    
    print("\n" + "="*60)
    print("TEST 1: RPC Connectivity")
    print("="*60)
    
    for rpc in RPC_ENDPOINTS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 5}))
            if w3.is_connected():
                block = w3.eth.block_number
                print(f"✅ {rpc}")
                print(f"   Connected! Latest block: {block}")
            else:
                print(f"❌ {rpc} - Not connected")
        except Exception as e:
            print(f"❌ {rpc} - Error: {e}")

def test_relayer_endpoints():
    """Test relayer endpoint availability"""
    import requests
    
    RELAYER_ENDPOINTS = [
        "https://relayer.polymarket.com/relay",
        "https://gasless.polymarket.com/relay",
        "https://api.polymarket.com/relay",
        "https://tx-relay.polymarket.com/relay",  # Legacy
    ]
    
    print("\n" + "="*60)
    print("TEST 2: Relayer Endpoint Availability")
    print("="*60)
    
    for endpoint in RELAYER_ENDPOINTS:
        try:
            # Try a GET request first (most endpoints will 404 or 405, but should resolve)
            resp = requests.get(endpoint, timeout=5, allow_redirects=True)
            print(f"✅ {endpoint}")
            print(f"   Status: {resp.status_code} (Resolves)")
        except requests.exceptions.ConnectionError as e:
            if "Failed to resolve" in str(e) or "NameResolutionError" in str(e):
                print(f"❌ {endpoint}")
                print(f"   DNS Resolution Failed")
            else:
                print(f"⚠️  {endpoint}")
                print(f"   Connection Error: {type(e).__name__}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️  {endpoint}")
            print(f"   Request Error: {type(e).__name__}")
            # This might still be ok - endpoint exists but requires POST

def test_contracts():
    """Test contract connectivity"""
    from web3 import Web3
    
    CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
    USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    print("\n" + "="*60)
    print("TEST 3: Contract Verification")
    print("="*60)
    
    try:
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        
        # Check CTF Exchange
        ctf_code = w3.eth.get_code(Web3.to_checksum_address(CTF_EXCHANGE))
        if len(ctf_code) > 0:
            print(f"✅ CTF Exchange: {CTF_EXCHANGE}")
            print(f"   Contract code present ({len(ctf_code)} bytes)")
        else:
            print(f"❌ CTF Exchange: No code at address")
        
        # Check USDC
        usdc_code = w3.eth.get_code(Web3.to_checksum_address(USDC_ADDRESS))
        if len(usdc_code) > 0:
            print(f"✅ USDC Token: {USDC_ADDRESS}")
            print(f"   Contract code present ({len(usdc_code)} bytes)")
        else:
            print(f"❌ USDC: No code at address")
            
    except Exception as e:
        print(f"❌ Contract check failed: {e}")

def test_redeem_manager():
    """Test the RedeemManager initialization"""
    print("\n" + "="*60)
    print("TEST 4: RedeemManager Initialization")
    print("="*60)
    
    # Check environment
    pk = os.getenv("PRIVATE_KEY") or os.getenv("PK")
    funder = os.getenv("FUNDER_ADDRESS")
    
    if not pk:
        print("❌ PRIVATE_KEY or PK not set in environment")
        return
    if not funder:
        print("❌ FUNDER_ADDRESS not set in environment")
        return
    
    print(f"✅ Environment variables set")
    print(f"   Funder: {funder[:10]}...{funder[-6:]}")
    
    try:
        from redeem_fixed import RedeemManager
        manager = RedeemManager()
        print(f"✅ RedeemManager initialized successfully")
        print(f"   Account: {manager.account.address[:10]}...{manager.account.address[-6:]}")
        
        # Check MATIC balance
        balance = manager.w3.eth.get_balance(manager.account.address)
        balance_matic = manager.w3.from_wei(balance, 'ether')
        print(f"   MATIC Balance: {balance_matic:.4f} MATIC")
        
        if balance_matic < 0.01:
            print(f"⚠️  Low MATIC balance - direct redemption may fail")
        else:
            print(f"✅ Sufficient MATIC for direct redemption")
            
    except Exception as e:
        print(f"❌ RedeemManager initialization failed: {e}")

def test_mock_redeem():
    """Test redemption flow with mock condition ID"""
    print("\n" + "="*60)
    print("TEST 5: Mock Redemption Flow")
    print("="*60)
    
    # Use a test condition ID
    test_condition = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    
    print(f"Testing with mock condition: {test_condition[:20]}...")
    print("(This will fail due to invalid condition, but tests the flow)")
    
    try:
        from redeem_fixed import RedeemManager
        manager = RedeemManager()
        
        # This will likely fail validation but tests the code path
        result = manager.redeem(test_condition, try_gasless=True)
        
        print(f"\nResult:")
        print(f"  Success: {result.get('success')}")
        print(f"  Method: {result.get('method')}")
        print(f"  Error: {result.get('error', 'None')}")
        print(f"  Fallback: {result.get('fallback', 'None')}")
        
    except Exception as e:
        print(f"Expected error (mock test): {e}")

def main():
    print("\n" + "="*60)
    print("Polymarket Redemption Fix - Test Suite")
    print("="*60)
    
    # Run all tests
    test_connections()
    test_relayer_endpoints()
    test_contracts()
    test_redeem_manager()
    test_mock_redeem()
    
    print("\n" + "="*60)
    print("Test Suite Complete")
    print("="*60)
    print("\nNext steps:")
    print("1. If all tests pass, the fix should work correctly")
    print("2. If relayer endpoints fail, direct redemption will be used")
    print("3. Ensure wallet has some MATIC for gas as backup")
    print("4. Run a real redemption test with a settled market")

if __name__ == "__main__":
    main()
