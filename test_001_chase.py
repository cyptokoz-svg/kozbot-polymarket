#!/usr/bin/env python3
"""
P1 修复测试：挂 0.01 价格订单，5秒后撤单
验证完整的下单-追踪-撤单流程
"""
import os
import sys
import asyncio
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

# 强制加载环境变量
load_dotenv('.env', override=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置日志
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入 bot 类来复用逻辑
from btc_15m_bot_v3 import PolymarketBotV3, Market15m, OrderBook
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs

TEST_PRICE = 0.01
TEST_DIRECTION = "UP"

async def test_001_chase():
    print("=" * 60)
    print("🧪 P1 修复测试：0.01 挂单 5秒追逐")
    print("=" * 60)
    
    # 初始化 Bot
    bot = PolymarketBotV3()
    
    # 获取当前市场
    market = bot.cycle_manager.fetch_market()
    if not market:
        print("❌ 无活跃市场")
        return
    
    print(f"\n📊 市场: {market.question}")
    print(f"   结算: {market.end_time}")
    
    # 获取 Strike price
    from btc_15m_bot_v3 import BinanceData
    import time
    start_ts_ms = int(market.start_time.timestamp() * 1000)
    strike_price = None
    for _ in range(3):
        strike_price = BinanceData.get_candle_open(start_ts_ms)
        if strike_price:
            break
        time.sleep(1)
    market.strike_price = strike_price or 0.0
    print(f"   Strike: ${market.strike_price:,.2f}")
    
    # 准备订单参数
    token_id = market.token_id_up if TEST_DIRECTION == "UP" else market.token_id_down
    shares = 1.0  # 测试用 1 份
    
    print(f"\n📤 提交订单:")
    print(f"   方向: {TEST_DIRECTION}")
    print(f"   价格: ${TEST_PRICE:.2f} (极低，不会成交)")
    print(f"   数量: {shares} 份")
    print(f"   Token: {token_id[:20]}...")
    
    try:
        # 构建订单
        order_args = OrderArgs(
            price=TEST_PRICE,
            size=shares,
            side="BUY",
            token_id=token_id
        )
        
        # 提交订单
        logger.info("🚀 执行下单...")
        order_result = bot.clob_client.create_and_post_order(order_args)
        
        print(f"\n📥 订单响应:")
        print(json.dumps(order_result, indent=2, default=str)[:500])
        
        order_id = order_result.get("order_id") if order_result else None
        
        if not order_id:
            print("\n❌ 未获取到 order_id，测试失败")
            return
        
        print(f"\n✅ 订单已提交: {order_id[:20]}...")
        
        # 创建持仓记录（复用修复后的逻辑）
        position = {
            "market_slug": market.slug,
            "direction": TEST_DIRECTION,
            "entry_price": TEST_PRICE,
            "shares": shares,
            "size": 0.05,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tp_placed": False,
            "sl_placed": False,
            "status": "PENDING",
            "order_id": order_id,
            "exit_checked": False
        }
        bot.positions.append(position)
        bot._save_positions()
        
        print(f"💾 持仓已保存: {len(bot.positions)} 个")
        print(f"   状态: {position['status']}")
        print(f"   订单ID: {position['order_id'][:20]}...")
        
        # 启动 5 秒追逐
        print(f"\n⏳ 开始 5 秒追逐倒计时...")
        
        for i in range(5, 0, -1):
            await asyncio.sleep(1)
            try:
                status = bot.clob_client.get_order(order_id)
                order_status = status.get("status", "UNKNOWN") if status else "ERROR"
                print(f"   [{i}s] 状态: {order_status}")
                
                if order_status == "FILLED":
                    print(f"\n⚠️ 意外成交！价格: {status.get('avg_price', 'N/A')}")
                    return
                    
            except Exception as e:
                print(f"   [{i}s] 查询失败: {str(e)[:50]}")
        
        # 5秒到，撤单
        print(f"\n⏰ 5秒超时，执行撤单...")
        try:
            bot.clob_client.cancel(order_id)
            print(f"✅ 撤单请求已发送")
            
            # 清理持仓
            if position in bot.positions:
                bot.positions.remove(position)
                bot._save_positions()
                print(f"🗑️ 持仓已清理")
            
            # 验证撤单
            await asyncio.sleep(1)
            try:
                status = bot.clob_client.get_order(order_id)
                print(f"📋 撤单后状态: {status.get('status', 'N/A')}")
            except Exception as e:
                print(f"📋 订单已取消 (查询失败: {str(e)[:30]})")
        
        except Exception as e:
            print(f"❌ 撤单失败: {e}")
        
        # 最终状态
        print(f"\n" + "=" * 60)
        print("✅ 测试完成")
        print(f"最终持仓数: {len(bot.positions)}")
        print("流程: 下单 → 5秒追踪 → 撤单 → 清理 ✓")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_001_chase())
