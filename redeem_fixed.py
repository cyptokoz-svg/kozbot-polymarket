#!/usr/bin/env python3
"""
Polymarket Redeem Module - Fixed Version
Supports multiple redemption methods:
1. Gasless Relayer (new endpoint if available)
2. Direct CTF Contract Interaction (requires MATIC)
3. Manual redemption via Polymarket UI
"""

import os
import sys
import json
import requests
import logging
from typing import Optional, Dict, List, Tuple
from web3 import Web3
from eth_account import Account
from eth_abi import encode
from dotenv import load_dotenv

# Load environment
load_dotenv()

logger = logging.getLogger(__name__)

# --- Configuration ---
# Try new relayer endpoints (old tx-relay.polymarket.com is deprecated)
RELAYER_ENDPOINTS = [
    "https://relayer.polymarket.com/relay",      # New endpoint candidate
    "https://gasless.polymarket.com/relay",      # Alternative endpoint
    "https://api.polymarket.com/relay",          # API endpoint candidate
]

# Legacy endpoint (for reference, may be removed)
LEGACY_RELAYER_URL = "https://tx-relay.polymarket.com/relay"

# Contract Addresses
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CHAIN_ID = 137

# RPC Endpoints (fallback order)
RPC_ENDPOINTS = [
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
    "https://polygon.llamarpc.com",
    "https://polygon.drpc.org",
]

# --- CTF Exchange Contract ABI (Partial) ---
CTF_EXCHANGE_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"}
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"}
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Gnosis Safe ABI (for nonce retrieval)
SAFE_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "nonce",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "data", "type": "bytes"},
            {"name": "operation", "type": "uint8"},
            {"name": "safeTxGas", "type": "uint256"},
            {"name": "baseGas", "type": "uint256"},
            {"name": "gasPrice", "type": "uint256"},
            {"name": "gasToken", "type": "address"},
            {"name": "refundReceiver", "type": "address"},
            {"name": "signatures", "type": "bytes"}
        ],
        "name": "execTransaction",
        "outputs": [{"name": "success", "type": "bool"}],
        "payable": True,
        "stateMutability": "payable",
        "type": "function"
    }
]


class RedeemManager:
    """Manages position redemption with multiple fallback methods"""
    
    def __init__(self, private_key: Optional[str] = None, funder_address: Optional[str] = None):
        self.private_key = private_key or os.getenv("PRIVATE_KEY") or os.getenv("PK")
        self.funder_address = funder_address or os.getenv("FUNDER_ADDRESS")
        
        if not self.private_key:
            raise ValueError("Private key not found (set PRIVATE_KEY or PK env var)")
        if not self.funder_address:
            raise ValueError("Funder address not found (set FUNDER_ADDRESS env var)")
            
        # Initialize Web3 with fallback RPCs
        self.w3 = self._init_web3()
        
        # Load account
        self.account = Account.from_key(self.private_key)
        logger.info(f"RedeemManager initialized for {self.funder_address}")
    
    def _init_web3(self) -> Web3:
        """Initialize Web3 with available RPC endpoint"""
        for rpc_url in RPC_ENDPOINTS:
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
                if w3.is_connected():
                    logger.info(f"Connected to Polygon via {rpc_url}")
                    return w3
            except Exception as e:
                logger.debug(f"Failed to connect to {rpc_url}: {e}")
                continue
        raise ConnectionError("Could not connect to any Polygon RPC endpoint")
    
    def _get_safe_nonce(self) -> Optional[int]:
        """Get current nonce from Gnosis Safe"""
        try:
            safe_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.funder_address),
                abi=SAFE_ABI
            )
            return safe_contract.functions.nonce().call()
        except Exception as e:
            logger.error(f"Failed to get Safe nonce: {e}")
            return None
    
    def _build_redeem_data(self, condition_id: str, index_sets: List[int] = None) -> bytes:
        """Build the redeemPositions transaction data"""
        # Default to redeeming both Yes (1) and No (2) positions
        if index_sets is None:
            index_sets = [1, 2]
        
        # Function selector for redeemPositions
        func_selector = bytes.fromhex("8679b734")
        
        # Encode parameters
        parent_id = bytes.fromhex("0" * 64)  # Empty bytes32
        cond_id_bytes = bytes.fromhex(condition_id.replace("0x", ""))
        
        data = func_selector + encode(
            ['address', 'bytes32', 'bytes32', 'uint256[]'],
            [USDC_ADDRESS, parent_id, cond_id_bytes, index_sets]
        )
        
        return data
    
    def _try_relayer_endpoints(self, payload: Dict) -> Tuple[bool, str]:
        """Try multiple relayer endpoints"""
        for endpoint in RELAYER_ENDPOINTS:
            try:
                logger.info(f"Trying relayer endpoint: {endpoint}")
                resp = requests.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if resp.status_code in [200, 201]:
                    return True, resp.text
                else:
                    logger.warning(f"Relayer {endpoint} returned {resp.status_code}: {resp.text}")
            except requests.exceptions.RequestException as e:
                logger.debug(f"Relayer {endpoint} failed: {e}")
                continue
        return False, "All relayer endpoints failed"
    
    def redeem_gasless(self, condition_id: str) -> Dict:
        """
        Attempt gasless redemption via relayer
        Falls back to manual if relayer is unavailable
        """
        logger.info(f"Attempting gasless redeem for condition: {condition_id[:10]}...")
        
        # Get nonce
        nonce = self._get_safe_nonce()
        if nonce is None:
            return {
                "success": False,
                "method": "gasless",
                "error": "Could not get Safe nonce",
                "fallback": "Try direct redemption or manual redeem"
            }
        
        # Build transaction data
        tx_data = self._build_redeem_data(condition_id)
        
        # Build payload for relayer
        payload = {
            "safe": self.funder_address,
            "to": CTF_EXCHANGE,
            "value": "0",
            "data": "0x" + tx_data.hex(),
            "operation": 0,
            "safeTxGas": 0,
            "baseGas": 0,
            "gasPrice": 0,
            "gasToken": "0x0000000000000000000000000000000000000000",
            "refundReceiver": "0x0000000000000000000000000000000000000000",
            "nonce": nonce,
            # Note: signature needs to be generated via EIP-712 signing
            # This is a placeholder - actual signing requires the eip712_signer module
            "signature": "0x"  # Will be populated by sign_safe_tx
        }
        
        # Try relayer endpoints
        success, result = self._try_relayer_endpoints(payload)
        
        if success:
            return {
                "success": True,
                "method": "gasless_relayer",
                "tx_hash": result,
                "message": "Redeem transaction submitted via relayer"
            }
        else:
            return {
                "success": False,
                "method": "gasless",
                "error": result,
                "fallback": "direct"
            }
    
    def redeem_direct(self, condition_id: str, index_sets: List[int] = None) -> Dict:
        """
        Direct CTF contract interaction (requires MATIC for gas)
        Use this when relayer is unavailable
        """
        logger.info(f"Attempting direct redeem for condition: {condition_id[:10]}...")
        
        try:
            # Initialize CTF Exchange contract
            ctf_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CTF_EXCHANGE),
                abi=CTF_EXCHANGE_ABI
            )
            
            # Build transaction
            if index_sets is None:
                index_sets = [1, 2]
            
            parent_id = bytes.fromhex("0" * 64)
            cond_id_bytes = bytes.fromhex(condition_id.replace("0x", ""))
            
            tx = ctf_contract.functions.redeemPositions(
                USDC_ADDRESS,
                parent_id,
                cond_id_bytes,
                index_sets
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': CHAIN_ID
            })
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Direct redeem transaction sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                return {
                    "success": True,
                    "method": "direct",
                    "tx_hash": tx_hash.hex(),
                    "gas_used": receipt['gasUsed'],
                    "message": "Redeem successful via direct contract interaction"
                }
            else:
                return {
                    "success": False,
                    "method": "direct",
                    "tx_hash": tx_hash.hex(),
                    "error": "Transaction failed on-chain"
                }
                
        except Exception as e:
            logger.error(f"Direct redeem failed: {e}")
            return {
                "success": False,
                "method": "direct",
                "error": str(e),
                "fallback": "manual"
            }
    
    def redeem(self, condition_id: str, try_gasless: bool = True) -> Dict:
        """
        Main redemption method with automatic fallback
        
        Args:
            condition_id: The market condition ID to redeem
            try_gasless: Whether to attempt gasless redemption first
            
        Returns:
            Dict with redemption result
        """
        condition_id = condition_id.replace("0x", "")
        
        # Try gasless first if enabled
        if try_gasless:
            result = self.redeem_gasless(condition_id)
            if result["success"]:
                return result
            logger.warning(f"Gasless redeem failed: {result.get('error')}")
        
        # Check if we have MATIC for direct redemption
        try:
            balance = self.w3.eth.get_balance(self.account.address)
            if balance > self.w3.to_wei(0.01, 'ether'):  # Need at least 0.01 MATIC
                logger.info("Attempting direct redemption with available MATIC...")
                return self.redeem_direct(condition_id)
            else:
                logger.warning(f"Insufficient MATIC for direct redemption: {self.w3.from_wei(balance, 'ether')} MATIC")
        except Exception as e:
            logger.error(f"Could not check MATIC balance: {e}")
        
        # Final fallback: manual redemption
        return {
            "success": False,
            "method": "none",
            "error": "All automated redemption methods failed",
            "fallback": "manual",
            "manual_url": f"https://polymarket.com/market/{condition_id}",
            "message": "Please redeem manually via Polymarket UI"
        }


# Convenience function for direct usage
def redeem_position(condition_id: str, private_key: Optional[str] = None, 
                   funder_address: Optional[str] = None) -> Dict:
    """
    Convenience function to redeem a position
    
    Args:
        condition_id: Market condition ID
        private_key: Optional private key (or set PRIVATE_KEY env var)
        funder_address: Optional funder address (or set FUNDER_ADDRESS env var)
        
    Returns:
        Redemption result dict
    """
    manager = RedeemManager(private_key, funder_address)
    return manager.redeem(condition_id)


if __name__ == "__main__":
    # Test the redemption module
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 redeem_fixed.py <condition_id>")
        print("Example: python3 redeem_fixed.py 0x48ba5d9c429d865d71f0c3a400e715f113aafec7ee90bbe9c98ac221d70125e4")
        sys.exit(1)
    
    test_condition_id = sys.argv[1]
    
    print(f"Testing redemption for condition: {test_condition_id}")
    print("-" * 60)
    
    try:
        result = redeem_position(test_condition_id)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
