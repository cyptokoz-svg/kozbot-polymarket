import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv("polymarket-bot/.env")

def check_methods():
    print("🔍 正在检查 SDK 功能...")
    key = os.getenv("PRIVATE_KEY")
    funder = os.getenv("FUNDER_ADDRESS")
    
    if not key or not funder:
        print("❌ 缺配置！")
        return

    # 初始化客户端 (Gnosis Safe 模式)
    try:
        client = ClobClient(
            "https://clob.polymarket.com", 
            key=key, 
            chain_id=137,
            signature_type=2, 
            funder=funder
        )
        print("✅ 客户端初始化成功")
        
        # 深度检查 Client 属性
        print("\n[Client 方法检查]")
        methods = [m for m in dir(client) if "redeem" in m.lower()]
        print(f"Redeem 相关: {methods}")
        
        # 尝试查找隐藏的 Exchange 属性
        if hasattr(client, 'exchange'):
            print("\n[Exchange 属性检查]")
            ex_methods = [m for m in dir(client.exchange) if "redeem" in m.lower()]
            print(f"Redeem 相关: {ex_methods}")
        else:
            print("\n❌ 没有 Exchange 属性 (这说明我们需要手动构造交易)")

    except Exception as e:
        print(f"❌ 出错: {e}")

if __name__ == "__main__":
    check_methods()
