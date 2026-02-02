#!/usr/bin/env python3
"""
测试挂单5秒追逐模式
挂一个0.01的价格（几乎不可能成交），观察5秒后撤单
"""
import os
import sys
import asyncio
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('.env', override=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, ApiCreds

# 测试参数
TEST_PRICE = 0.01  # 极低价格，几乎不可能成交
TEST_SIZE = 1.0    # 1份
TEST_MARKET_ID = "21006866936948990631797503494273329140308463619405787311915039981646923556312"  # 当前市场的token

async def test_chase_order():
    print("=" * 60)
    print("🧪 测试挂单5秒追逐模式")
    print("=" * 60)
    print(f"\n📋 测试参数:")
    print(f"   价格: ${TEST_PRICE:.2f} (极低，不会成交)")
    print(f"   数量: {TEST_SIZE} 份")
    print(f"   方向: BUY (UP)")
    
    # 初始化客户端
    key = os.getenv("PRIVATE_KEY") or os.getenv("PK")
    if not key:
        print("❌ 未设置私钥")
        return
    
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137)
    creds = client.derive_api_key()
    client.set_api_creds(creds)
    
    print("\n🔗 CLOB Client 已连接")
    
    # 构建订单
    order_args = OrderArgs(
        price=TEST_PRICE,
        size=TEST_SIZE,
        side="BUY",
        token_id=TEST_MARKET_ID
    )
    
    try:
        print(f"\n📤 提交订单: BUY {TEST_SIZE} @ ${TEST_PRICE:.2f}")
        order_result = client.create_and_post_order(order_args)
        print(f"📥 响应: {json.dumps(order_result, indent=2, default=str)[:500]}")
        
        order_id = order_result.get("order_id") if order_result else None
        
        if not order_id:
            print("❌ 未获取到订单ID")
            return
        
        print(f"\n✅ 订单已提交: {order_id[:16]}...")
        print(f"⏳ 开始5秒追逐倒计时...\n")
        
        # 5秒追逐
        for i in range(5, 0, -1):
            await asyncio.sleep(1)
            
            # 检查订单状态
            try:
                status = client.get_order(order_id)
                order_status = status.get("status") if status else "UNKNOWN"
                print(f"   [{i}s] 状态: {order_status}")
                
                if order_status == "FILLED":
                    print(f"\n✅ 订单成交！价格: {status.get('avg_price', 'N/A')}")
                    return
                    
            except Exception as e:
                print(f"   [{i}s] 查询失败: {e}")
        
        # 5秒到，撤单
        print(f"\n⏰ 5秒超时，执行撤单...")
        try:
            client.cancel(order_id)
            print(f"✅ 撤单成功")
            
            # 验证撤单
            await asyncio.sleep(1)
            try:
                status = client.get_order(order_id)
                print(f"📋 撤单后状态: {status.get('status', 'N/A')}")
            except:
                print(f"📋 订单已取消或不存在")
                
        except Exception as e:
            print(f"❌ 撤单失败: {e}")
        
        print(f"\n🔄 测试完成，准备进入新周期（重新挂单）")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_chase_order())
