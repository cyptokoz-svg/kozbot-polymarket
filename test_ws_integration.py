#!/usr/bin/env python3
"""
Quick test: WebSocket integrated into bot loop
"""
import asyncio
import logging
from data_source import BinanceData, PolyMarketData
from websocket_client import MarketWebSocket

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_main_loop():
    print("🧪 测试 WebSocket 集成到主循环")
    print()
    
    # Find active market
    market_slug = 'btc-updown-15m-1770121800' 
    market = await PolyMarketData.get_market(market_slug)
    
    if not market:
        print("❌ 无法获取市场")
        return
    
    print(f"✅ Market: {market.get('question')}")
    print(f"Strike: ${market.get('strike', 0):,.2f}")
    print()
    
    # Get tokens
    token_up, token_down = PolyMarketData.resolve_token_ids(market)
    print(f"UP token: {token_up[:30]}...")
    print(f"DOWN token: {token_down[:30]}...")
    print()
    
    # Start WebSocket
    ws_manager = MarketWebSocket()
    await ws_manager.subscribe([token_up, token_down], replace=True, fetch_initial=False)
    
    # Run WebSocket in background
    run_task = asyncio.create_task(ws_manager.run(auto_reconnect=True))
    
    # Wait for initial data
    await asyncio.sleep(2)
    
    # Main loop (10 iterations)
    print("🔄 主循环开始 (10次迭代)...\n")
    for i in range(10):
        # Get BTC price
        btc_price = await BinanceData.get_current_price()
        strike = market.get('strike', 0)
        
        # Get orderbook from WebSocket
        market_data = {}
        ob_up = ws_manager.get_orderbook(token_up)
        ob_down = ws_manager.get_orderbook(token_down)
        
        if ob_up and ob_down:
            market_data["ask_up"] = ob_up.best_ask
            market_data["ask_down"] = ob_down.best_ask
            source = "WebSocket"
        else:
            # Fallback to REST
            ob_up_rest = await PolyMarketData.get_orderbook(token_up)
            ob_down_rest = await PolyMarketData.get_orderbook(token_down)
            if ob_up_rest and "asks" in ob_up_rest and len(ob_up_rest["asks"]) > 0:
                market_data["ask_up"] = float(ob_up_rest["asks"][0]["price"])
            if ob_down_rest and "asks" in ob_down_rest and len(ob_down_rest["asks"]) > 0:
                market_data["ask_down"] = float(ob_down_rest["asks"][0]["price"])
            source = "REST API"
        
        # Display
        diff = btc_price - strike
        direction = "📈 UP" if diff > 0 else "📉 DOWN"
        
        print(f"[{i+1}] BTC: ${btc_price:,.2f} | {direction} ${abs(diff):.2f} | "
              f"Ask UP: {market_data.get('ask_up', 'N/A'):.3f} | "
              f"Ask DOWN: {market_data.get('ask_down', 'N/A'):.3f} | "
              f"Source: {source}")
        
        await asyncio.sleep(1)
    
    # Cleanup
    ws_manager.stop()
    await ws_manager.disconnect()
    
    print()
    print("✅ 测试完成!")

if __name__ == "__main__":
    try:
        asyncio.run(test_main_loop())
    except KeyboardInterrupt:
        print("\n\n⚠️ 中断")
