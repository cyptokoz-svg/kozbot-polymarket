#!/usr/bin/env python3
"""
Polymarket Relayer V2 Client - Gasless Redemption
Uses Builder API credentials for authenticated relayer access
"""

import os
import json
import hmac
import hashlib
import base64
import time
import requests
import logging
from typing import Dict, Optional, List, Tuple
from web3 import Web3
from eth_abi import encode

logger = logging.getLogger(__name__)

# Relayer V2 Configuration
RELAYER_V2_URLS = [
    "https://relayer-v2.polymarket.com",
    "https://relayer.polymarket.com",
    "https://gasless.polymarket.com",
]
CHAIN_ID = 137  # Polygon

# Contract Addresses
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


class RelayerV2Client:
    """Polymarket Relayer V2 Client with Builder Authentication"""
    
    def __init__(self):
        # Ensure env vars are loaded
        from dotenv import load_dotenv
        load_dotenv('.env', override=True)
        
        self.api_key = os.getenv("POLY_BUILDER_API_KEY")
        self.api_secret = os.getenv("POLY_BUILDER_API_SECRET")
        self.passphrase = os.getenv("POLY_BUILDER_API_PASSPHRASE")
        self.safe_address = os.getenv("POLY_SAFE_ADDRESS") or os.getenv("FUNDER_ADDRESS")
        
        if not all([self.api_key, self.api_secret, self.passphrase]):
            raise ValueError("Missing Builder API credentials. Set POLY_BUILDER_API_KEY, POLY_BUILDER_API_SECRET, POLY_BUILDER_API_PASSPHRASE")
        
        if not self.safe_address:
            raise ValueError("Missing Safe address. Set POLY_SAFE_ADDRESS or FUNDER_ADDRESS")
        
        self.passphrase = self._normalize_passphrase(self.passphrase)
        logger.info(f"RelayerV2Client initialized for Safe: {self.safe_address[:10]}...")

    def _is_hex(self, value: str) -> bool:
        if not value:
            return False
        try:
            return all(c in "0123456789abcdefABCDEF" for c in value)
        except Exception:
            return False

    def _normalize_passphrase(self, value: str) -> str:
        if not value:
            return value
        if self._is_hex(value) and len(value) % 2 == 0:
            try:
                return bytes.fromhex(value).decode("utf-8", errors="ignore")
            except Exception:
                return value
        return value
    
    def _decode_secret(self) -> bytes:
        """Decode Builder API secret with proper padding handling"""
        secret = self.api_secret
        if self._is_hex(secret) and len(secret) % 2 == 0:
            try:
                return bytes.fromhex(secret)
            except Exception:
                pass
        
        # Try base64 decoding with padding fix
        for i in range(4):  # Try 0-3 padding chars
            try:
                padded = secret + ('=' * i)
                return base64.b64decode(padded)
            except:
                continue
        
        # Fallback to raw secret
        logger.warning("Base64 decode failed, using raw secret")
        return secret.encode('utf-8')
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for relayer authentication"""
        # [CRITICAL] message = millisecond_timestamp + method + path + compact_body
        message = timestamp + method + path + body
        
        # Decode secret properly
        secret_bytes = self._decode_secret()
        
        signature = hmac.new(
            secret_bytes,
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')
    
    def _get_headers(self, method: str, path: str, body: str, header_case: str = "lower") -> Dict[str, str]:
        """Get authentication headers for relayer requests"""
        timestamp = str(int(time.time() * 1000))  # [CRITICAL] Must be 13-digit milliseconds
        signature = self._generate_signature(timestamp, method, path, body)
        if header_case == "upper":
            return {
                "Content-Type": "application/json",
                "POLY_BUILDER_API_KEY": self.api_key,
                "POLY_BUILDER_TIMESTAMP": timestamp,
                "POLY_BUILDER_PASSPHRASE": self.passphrase,
                "POLY_BUILDER_SIGNATURE": signature
            }
        return {
            "content-type": "application/json",
            "poly-builder-api-key": self.api_key,
            "poly-builder-timestamp": timestamp,
            "poly-builder-passphrase": self.passphrase,
            "poly-builder-signature": signature
        }
    
    def _build_redeem_transaction(self, condition_id: str, index_sets: List[int] = None) -> Dict:
        """Build redeemPositions transaction data"""
        if index_sets is None:
            index_sets = [1, 2]  # Yes and No positions
        
        # Function selector for redeemPositions
        func_selector = bytes.fromhex("8679b734")
        
        # Encode parameters
        parent_id = bytes.fromhex("0" * 64)  # Empty bytes32 for Polymarket
        cond_id_bytes = bytes.fromhex(condition_id.replace("0x", ""))
        
        data = func_selector + encode(
            ['address', 'bytes32', 'bytes32', 'uint256[]'],
            [USDC_ADDRESS, parent_id, cond_id_bytes, index_sets]
        )
        
        return {
            "to": CTF_EXCHANGE,
            "data": "0x" + data.hex(),
            "value": "0"
        }
    
    def redeem_positions(self, condition_id: str, index_sets: List[int] = None) -> Dict:
        """
        Redeem positions via Relayer V2 (gasless)
        
        Args:
            condition_id: The market condition ID
            index_sets: Outcome indices to redeem (default: [1, 2] for Yes/No)
            
        Returns:
            Dict with transaction details
        """
        condition_id = condition_id.replace("0x", "")
        logger.info(f"Submitting redeem via Relayer V2... Condition: {condition_id[:10]}")
        
        # Build transaction
        tx = self._build_redeem_transaction(condition_id, index_sets)
        
        # Prepare request body
        body_dict = {
            "type": "SAFE",
            "from": self.safe_address,
            "transactions": [tx]
        }
        
        # [CRITICAL] Use compact JSON (no spaces) - separators=(',', ':')
        body_json = json.dumps(body_dict, separators=(',', ':'))
        
        try:
            path = "/submit"
            method = "POST"
            logger.info(f"Body (compact): {body_json[:100]}...")
            logger.info(f"Path for signature: {path}")

            for base_url in RELAYER_V2_URLS:
                url = f"{base_url}{path}"
                logger.info(f"Sending to relayer: {url}")

                # Try lowercase headers first, retry uppercase only on 401
                headers = self._get_headers(method, path, body_json, header_case="lower")
                resp = requests.post(url, data=body_json, headers=headers, timeout=30)

                if resp.status_code == 401:
                    headers = self._get_headers(method, path, body_json, header_case="upper")
                    resp = requests.post(url, data=body_json, headers=headers, timeout=30)

                if resp.status_code in [200, 201]:
                    result = resp.json()
                    logger.info(f"✅ Redeem submitted! Transaction ID: {result.get('transactionID', 'N/A')}")
                    return {
                        "success": True,
                        "method": "relayer_v2",
                        "transaction_id": result.get("transactionID"),
                        "transaction_hash": result.get("transactionHash"),
                        "state": result.get("state"),
                        "raw_response": result
                    }
                else:
                    logger.warning(f"Relayer {base_url} returned {resp.status_code}: {resp.text}")

            error_msg = "Relayer error: all endpoints failed"
            logger.error(error_msg)
            return {
                "success": False,
                "method": "relayer_v2",
                "error": error_msg,
                "status_code": 0
            }
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Relayer request failed: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "method": "relayer_v2",
                "error": error_msg
            }
    
    def get_transaction_status(self, transaction_id: str) -> Dict:
        """Check status of a submitted transaction"""
        try:
            path = f"/transaction/{transaction_id}"
            method = "GET"
            body = ""  # GET request has no body

            for base_url in RELAYER_V2_URLS:
                url = f"{base_url}{path}"
                headers = self._get_headers(method, path, body, header_case="lower")
                resp = requests.get(url, headers=headers, timeout=10)

                if resp.status_code == 401:
                    headers = self._get_headers(method, path, body, header_case="upper")
                    resp = requests.get(url, headers=headers, timeout=10)

                if resp.status_code == 200:
                    result = resp.json()
                    return {
                        "success": True,
                        "transaction_id": transaction_id,
                        "state": result.get("state"),
                        "transaction_hash": result.get("transactionHash"),
                        "raw_response": result
                    }

            return {
                "success": False,
                "error": "Status check failed on all endpoints"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Convenience function
def redeem_position(condition_id: str) -> Dict:
    """
    Convenience function to redeem a position via Relayer V2
    
    Args:
        condition_id: Market condition ID
        
    Returns:
        Redemption result dict
    """
    client = RelayerV2Client()
    return client.redeem_positions(condition_id)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 relayer_v2_client.py <condition_id>")
        print("Example: python3 relayer_v2_client.py 0x48ba5d9c429d865d71f0c3a400e715f113aafec7ee90bbe9c98ac221d70125e4")
        sys.exit(1)
    
    test_condition_id = sys.argv[1]
    
    print(f"Testing Relayer V2 redemption for: {test_condition_id}")
    print("-" * 60)
    
    try:
        result = redeem_position(test_condition_id)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
