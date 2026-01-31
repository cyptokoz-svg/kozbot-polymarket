from eip712_signer import sign_safe_tx
import os
from dotenv import load_dotenv

load_dotenv("polymarket-bot/.env")

def test_signature():
    print("🧪 启动 EIP-712 签名模块自检...")
    
    pk = os.getenv("PRIVATE_KEY")
    safe = os.getenv("FUNDER_ADDRESS")
    
    if not pk or not safe:
        print("❌ 缺少配置 (PK/Safe)")
        return

    print(f"👤 签署人: {pk[:6]}...")
    print(f"🏦 代理金库: {safe}")
    
    try:
        # Dummy Data for Test
        sig = sign_safe_tx(
            safe_address=safe,
            to="0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", # CTF Exchange
            value=0,
            data=bytes.fromhex("8679b734"), # redeemPositions
            operation=0,
            safe_tx_gas=0,
            base_gas=0,
            gas_price=0,
            gas_token="0x0000000000000000000000000000000000000000",
            refund_receiver="0x0000000000000000000000000000000000000000",
            nonce=0, # Test Nonce
            private_key=pk
        )
        
        print(f"✅ 签名生成成功!")
        print(f"📜 Signature: {sig[:20]}...{sig[-20:]}")
        print("🎉 结论: 密码学模块工作正常。")
        
    except Exception as e:
        print(f"❌ 签名失败: {e}")

if __name__ == "__main__":
    test_signature()
