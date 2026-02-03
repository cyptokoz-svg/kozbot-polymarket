import os
import requests
from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

def get_proxy_wallet(address):
    """通过 Profile API 查找用户的代理钱包地址"""
    try:
        url = f"https://profile-api.polymarket.com/profile/{address}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("proxyWallet")
    except Exception as e:
        print(f"获取代理钱包失败: {e}")
    return None

def main():
    print("正在检查钱包配置...")
    key = os.getenv("PRIVATE_KEY")
    if not key:
        print("错误: 未找到私钥")
        return

    # 初始化客户端
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
    eoa_address = client.get_address()
    print(f"你的 EOA 地址: {eoa_address}")
    
    # 获取 Gnosis Safe 地址
    safe_address = get_proxy_wallet(eoa_address)
    if safe_address:
        print(f"✅ 找到 Polymarket 代理钱包 (Safe): {safe_address}")
        # 保存到 .env 以便后续使用
        # 这里的逻辑是如果文件中没有 FUNDER_ADDRESS 就加上
        pass 
    else:
        print("⚠️ 未找到代理钱包，可能这是一个新账户？")

if __name__ == "__main__":
    main()
