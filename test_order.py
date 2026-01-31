#!/usr/bin/env python3
"""测试下单和撤单系统"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

load_dotenv()

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CHAIN_ID = 137

def get_current_market():
    """获取当前活跃的 BTC 15分钟市场"""
    now = datetime.now(timezone.utc)
    current_ts = int(now.timestamp())
    
    # 当前和下一个周期
    for offset in [0, 900]:
        ts = ((current_ts // 900) * 900) + offset
        slug = f"btc-updown-15m-{ts}"
        
        try:
            resp = requests.get(f"{GAMMA_API}/events?slug={slug}", timeout=10)
            events = resp.json()
            
            if events and not events[0].get("closed", True):
                event = events[0]
                markets = event.get("markets", [])
                if markets and markets[0].get("acceptingOrders", False):
                    market = markets[0]
                    token_ids = json.loads(market.get("clobTokenIds", "[]"))
                    outcomes = json.loads(market.get("outcomes", '["Up", "Down"]'))
                    
                    # 确定 UP token
                    if outcomes[0].lower() == "up":
                        token_up = token_ids[0]
                    else:
                        token_up = token_ids[1]
                    
                    return {
                        "title": event.get("title", ""),
                        "end": market.get("endDate", ""),
                        "token_id": token_up,
                        "condition_id": market.get("conditionId", "")
                    }
        except Exception as e:
            print(f"查询 {slug} 失败: {e}")
    
    return None

def main():
    print("=" * 60)
    print("Polymarket 下单/撤单测试")
    print("=" * 60)
    
    # 初始化客户端
    private_key = os.getenv("PRIVATE_KEY")
    funder = os.getenv("FUNDER_ADDRESS")
    
    print(f"\n钱包: {funder[:10]}...{funder[-6:]}")
    
    client = ClobClient(
        CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=2,  # Proxy wallet
        funder=funder
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    print("✓ 客户端初始化成功")
    
    # 获取当前市场
    print("\n查找活跃市场...")
    market = get_current_market()
    
    if not market:
        print("✗ 没有找到活跃的 BTC 15分钟市场")
        print("  可能在周期切换中，请稍后再试")
        return
    
    print(f"✓ 找到市场: {market['title']}")
    print(f"  结束时间: {market['end']}")
    print(f"  Token ID: {market['token_id'][:20]}...")
    
    # 查看当前订单
    print("\n当前开放订单:")
    try:
        orders = client.get_orders()
        print(f"  订单数: {len(orders) if orders else 0}")
        if orders:
            for o in orders[:3]:
                print(f"    - {o}")
    except Exception as e:
        print(f"  获取订单失败: {e}")
    
    # 下限价单 @ $0.01
    print("\n" + "-" * 40)
    print("测试下单: BUY UP @ $0.01, 数量 5 shares")
    print("-" * 40)
    
    try:
        order = OrderArgs(
            token_id=market["token_id"],
            price=0.01,  # 最低价格
            size=5.0,    # 最小数量
            side=BUY
        )
        
        signed_order = client.create_order(order)
        print(f"✓ 订单已签名")
        
        resp = client.post_order(signed_order, OrderType.GTC)
        print(f"✓ 订单已提交!")
        print(f"  响应: {resp}")
        
        order_id = resp.get("orderID") or resp.get("order_id") or resp.get("id")
        
        if order_id:
            print(f"\n订单 ID: {order_id}")
            
            # 等待一下
            time.sleep(2)
            
            # 查看订单状态
            print("\n检查订单状态...")
            orders = client.get_orders()
            found = False
            for o in orders or []:
                if str(o.get("id")) == str(order_id) or str(o.get("order_id")) == str(order_id):
                    print(f"  ✓ 订单在列表中")
                    found = True
                    break
            
            if not found and orders:
                print(f"  订单列表: {[o.get('id') for o in orders[:5]]}")
            
            # 撤单
            print("\n" + "-" * 40)
            print("测试撤单...")
            print("-" * 40)
            
            try:
                cancel_resp = client.cancel(order_id=order_id)
                print(f"✓ 撤单成功!")
                print(f"  响应: {cancel_resp}")
            except Exception as e:
                print(f"✗ 撤单失败: {e}")
                
                # 尝试取消所有订单
                print("\n尝试取消所有订单...")
                try:
                    cancel_all = client.cancel_all()
                    print(f"✓ 取消所有订单: {cancel_all}")
                except Exception as e2:
                    print(f"✗ 取消所有失败: {e2}")
        else:
            print(f"  无法获取订单 ID，响应: {resp}")
            
    except Exception as e:
        print(f"✗ 下单失败: {e}")
        
        # 如果是余额问题，给出建议
        if "balance" in str(e).lower() or "allowance" in str(e).lower():
            print("\n建议: 余额不足或未授权")
            print("  1. 在 Polymarket 网站存入更多 USDC")
            print("  2. 或者在网站上手动下一笔单激活授权")
    
    # 最后检查订单
    print("\n" + "=" * 60)
    print("最终订单状态:")
    try:
        final_orders = client.get_orders()
        print(f"  开放订单数: {len(final_orders) if final_orders else 0}")
    except Exception as e:
        print(f"  获取失败: {e}")
    
    print("=" * 60)
    print("测试完成")

if __name__ == "__main__":
    main()
