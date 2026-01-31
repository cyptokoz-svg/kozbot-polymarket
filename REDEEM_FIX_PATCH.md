"""
Polymarket Redeem Fix - Patch Guide
====================================

PROBLEM:
--------
The current implementation uses `tx-relay.polymarket.com` which no longer resolves.
This causes automatic redemption to fail with DNS errors.

SOLUTION:
---------
Replace the old _raw_redeem method with the new RedeemManager class that:
1. Tries new relayer endpoints
2. Falls back to direct CTF contract interaction (requires MATIC)
3. Falls back to manual redemption notification

PATCH INSTRUCTIONS:
-------------------

1. ADD IMPORTS (after existing imports in btc_15m_bot_v3.py):
   
   # Add this import
   from redeem_fixed import RedeemManager

2. REPLACE the _raw_redeem method in PolymarketBotV3 class:

   OLD CODE (lines ~750-815):
   ----------------------------
   def _raw_redeem(self, condition_id):
       """Execute Auto-Redeem via Gasless Relayer"""
       if not self.clob_client or not FUNDER_ADDRESS:
           logger.error("❌ 无法赎回: 缺 Client 或 代理地址")
           return

       try:
           logger.info(f"🏦 [EIP-712] 正在构建免 Gas 赎回交易... ID: {condition_id[:8]}")
           
           # 1. Construct Data for redeemPositions
           func_selector = bytes.fromhex("8679b734") # redeemPositions
           parent_id = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")
           cond_id_bytes = bytes.fromhex(condition_id.replace("0x", ""))
           index_sets = [1, 2] # Yes and No

           tx_data = func_selector + encode(
               ['address', 'bytes32', 'bytes32', 'uint256[]'],
               [USDC_ADDRESS, parent_id, cond_id_bytes, index_sets]
           )
           
           # 2. Get Nonce
           nonce = self._get_safe_nonce()
           if nonce is None:
               logger.error("❌ 无法获取 Nonce，跳过赎回")
               return

           logger.info(f"✅ Nonce: {nonce}. 正在签名...")
           
           # 3. Sign
           pk = os.getenv("PRIVATE_KEY")
           signature = sign_safe_tx(
               safe_address=FUNDER_ADDRESS,
               to=CTF_EXCHANGE,
               value=0,
               data=tx_data,
               operation=0,
               safe_tx_gas=0,
               base_gas=0,
               gas_price=0,
               gas_token="0x0000000000000000000000000000000000000000",
               refund_receiver="0x0000000000000000000000000000000000000000",
               nonce=nonce,
               private_key=pk
           )
           
           # 4. Post to Relayer
           payload = {
               "safe": FUNDER_ADDRESS,
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
               "signature": "0x" + signature.hex()
           }
           
           resp = requests.post(RELAYER_URL, json=payload, headers={"Content-Type": "application/json"})
           if resp.status_code == 200 or resp.status_code == 201:
               logger.info(f"🎉 自动赎回成功! TX Hash: {resp.text}")
           else:
               logger.error(f"❌ Relayer 拒绝: {resp.status_code} - {resp.text}")
           
       except Exception as e:
           logger.error(f"❌ 赎回出错: {e}")

   NEW CODE:
   ---------
   def _raw_redeem(self, condition_id):
       """Execute Auto-Redeem with fallback methods"""
       if not self.clob_client or not FUNDER_ADDRESS:
           logger.error("❌ 无法赎回: 缺 Client 或 代理地址")
           return

       try:
           logger.info(f"🏦 启动自动赎回流程... Condition: {condition_id[:8]}")
           
           # Initialize redeem manager
           from redeem_fixed import RedeemManager
           manager = RedeemManager()
           
           # Attempt redemption with automatic fallback
           result = manager.redeem(condition_id, try_gasless=True)
           
           if result["success"]:
               logger.info(f"🎉 赎回成功! 方法: {result['method']}, TX: {result.get('tx_hash', 'N/A')}")
               self._notify_user(f"💰 自动赎回成功!\n方法: {result['method']}\nTX: {result.get('tx_hash', 'N/A')[:20]}...")
           else:
               error_msg = result.get('error', 'Unknown error')
               fallback = result.get('fallback', 'manual')
               
               if fallback == 'manual':
                   manual_url = result.get('manual_url', 'https://polymarket.com')
                   logger.error(f"❌ 自动赎回失败，需手动操作: {error_msg}")
                   self._notify_user(f"⚠️ 赎回失败 - 需手动操作\n错误: {error_msg[:50]}...\n🔗 {manual_url}")
               else:
                   logger.error(f"❌ 赎回失败: {error_msg}")
                   
       except Exception as e:
           logger.error(f"❌ 赎回过程异常: {e}")
           self._notify_user(f"❌ 赎回异常: {str(e)[:100]}")

3. UPDATE settle_positions method (around line ~900):
   
   Change:
       # [Real Trading] Auto-Redeem Logic
       if not self.paper_trade and self.clob_client:
           try:
               self._raw_redeem(market.condition_id)
           except Exception as e:
               logger.error(f"赎回失败: {e}")
   
   To:
       # [Real Trading] Auto-Redeem Logic
       if not self.paper_trade and self.clob_client:
           try:
               self._raw_redeem(market.condition_id)
           except Exception as e:
               logger.error(f"赎回失败: {e}")
               # Notify user about manual redemption
               self._notify_user(f"⚠️ 自动赎回失败，请手动赎回:\nhttps://polymarket.com/market/{market.condition_id}")

ALTERNATIVE: Full File Replacement
----------------------------------
If you prefer, you can use the new redeem_fixed.py module directly:

    from redeem_fixed import redeem_position
    
    # When market settles
    result = redeem_position(condition_id)
    if not result['success']:
        # Handle failure
        pass

TESTING:
--------
1. Test the new redemption module:
   cd /home/ubuntu/clawd/polymarket-bot
   source venv/bin/activate
   python3 redeem_fixed.py <test_condition_id>

2. Monitor logs for:
   - "Trying relayer endpoint: ..."
   - "Direct redeem transaction sent: ..."
   - Any error messages

3. If all automated methods fail, the bot will notify you with a manual redemption link.

MONITORING:
-----------
Check the bot logs for redemption status:
- Successful: "🎉 赎回成功!"
- Failed with fallback: "❌ 自动赎回失败，需手动操作"

BACKUP PLAN:
------------
If automatic redemption consistently fails:
1. Ensure the wallet has some MATIC for gas (0.1 MATIC should be sufficient)
2. The bot will automatically fall back to direct contract interaction
3. Or manually redeem at: https://polymarket.com/portfolio

CONTRACT ADDRESSES (for reference):
-----------------------------------
- CTF Exchange: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
- USDC: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
- Conditional Tokens: 0x4D97DCd97eC945f40cF65F87097ACe5EA0476045
"""
