from data_source import PolyMarketData, BinanceData
from datetime import datetime, timezone, timedelta
import math
from scipy.stats import norm
import asyncio
import logging

logger = logging.getLogger(__name__)

def calculate_fair_value(S, K, T_min, sigma):
    """Calculate fair value probability using Black-Scholes-like model"""
    if T_min <= 0: 
        return 1.0 if S > K else 0.0
    if S <= 0 or K <= 0:
        logger.warning(f"Invalid price: S={S}, K={K}")
        return 0.5
    
    T = T_min / (365 * 24 * 60)
    try:
        d1 = (math.log(S / K) + (0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        prob_up = norm.cdf(d2)
        return prob_up
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        logger.warning(f"Fair value calc failed: {e} (S={S:.2f}, K={K:.2f}, T={T_min:.1f}min)")
        return 0.5

async def main():
    print('=== 🔍 正在神之模式扫描市场 ===')
    now = datetime.now(timezone.utc)
    ts = int(now.timestamp())
    current_slot_ts = ts - (ts % 900)
    
    # Check calculated slot first (GOD MODE)
    active_slug = f"btc-updown-15m-{current_slot_ts}"
    print(f'计算出的当前市场: {active_slug}')
    
    market = await PolyMarketData.get_market(active_slug)
    if not market:
        # Try previous slot as fallback
        prev_slug = f"btc-updown-15m-{current_slot_ts-900}"
        print(f'尝试上一时段: {prev_slug}')
        market = await PolyMarketData.get_market(prev_slug)
        if market:
            active_slug = prev_slug
    
    if not market:
        print('❌ 未找到活跃市场 (即使是神之模式)')
        return
    
    print(f'✅ 锁定市场: {active_slug}')
    
    # 2. 获取数据
    strike = market.get('strike')
    btc_price = await BinanceData.get_current_price()
    tokens = PolyMarketData.resolve_token_ids(market)
    
    print(f'\\n🔍 Outcomes: {market.get("outcomes")}')
    print(f'🔍 Token IDs: {tokens}')
    print(f'🔍 CLOB IDs:  {market.get("clobTokenIds")}')
    
    # Calculate time remaining
    slug_parts = active_slug.split('-')
    slug_ts = int(slug_parts[-1])
    official_start = datetime.fromtimestamp(slug_ts, timezone.utc)
    official_end = official_start + timedelta(minutes=15)
    
    now = datetime.now(timezone.utc)
    time_left = (official_end - now).total_seconds() / 60
    
    print('\\n=== 📊 市场数据报告 ===')
    print(f'市场名称: {market.get("question")}')
    print(f'Slug时间: {official_start.strftime("%H:%M:%S")} -> {official_end.strftime("%H:%M:%S")}')
    print(f'剩余时间: {time_left:.1f} 分钟')
    print(f'-----------------------')
    print(f'行权价格: ${strike:,.2f}')
    print(f'当前 BTC: ${btc_price:,.2f}')
    diff = btc_price - strike
    print(f'价格差值: ${diff:.2f} ({"UP" if diff>0 else "DOWN"})')
    
    # 3. 计算公允价值
    sigma = 0.0575 # 默认波动率
    fv_up = calculate_fair_value(btc_price, strike, time_left, sigma)
    
    print(f'\\n=== 💹 模型计算 ===')
    print(f'公允概率 (UP):   {fv_up:.4f} ({fv_up*100:.1f}%)')
    print(f'公允概率 (DOWN): {1-fv_up:.4f} ({(1-fv_up)*100:.1f}%)')
    
    # 4. Orderbook
    print('\\n=== 📖 订单簿数据 ===')
    if tokens[0] and tokens[1]:
        ob_up = await PolyMarketData.get_orderbook(tokens[0])
        ob_down = await PolyMarketData.get_orderbook(tokens[1])
        
        bid_up = float(ob_up['bids'][0]['price']) if ob_up and ob_up['bids'] else 0
        ask_up = float(ob_up['asks'][0]['price']) if ob_up and ob_up['asks'] else 0
        
        bid_down = float(ob_down['bids'][0]['price']) if ob_down and ob_down['bids'] else 0
        ask_down = float(ob_down['asks'][0]['price']) if ob_down and ob_down['asks'] else 0
        
        print(f'📈 UP Token')
        print(f'  买一 (Bid): {bid_up:.3f}')
        print(f'  卖一 (Ask): {ask_up:.3f}')
        edge_up = (fv_up - ask_up) if ask_up > 0 else 0
        print(f'  Edge: {edge_up*100:.2f}% {"🚨 机会!" if edge_up > 0.08 else ""}')
        
        print(f'\\n📉 DOWN Token')
        print(f'  买一 (Bid): {bid_down:.3f}')
        print(f'  卖一 (Ask): {ask_down:.3f}')
        edge_down = ((1-fv_up) - ask_down) if ask_down > 0 else 0
        print(f'  Edge: {edge_down*100:.2f}% {"🚨 机会!" if edge_down > 0.08 else ""}')
    
    else:
        print('❌ 无法获取 Token IDs')

if __name__ == "__main__":
    asyncio.run(main())
