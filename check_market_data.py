"""
检查当前活跃市场数据
Check current active market data to debug strategy
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_source import PolyMarketData
import json
import asyncio

async def check_market_data():
    """检查市场数据是否包含strike和expiry"""
    print("🔍 正在检查活跃的 BTC 15分钟市场...\\n")
    
    # 1. 获取活跃市场列表
    try:
        params = {
            "closed": False,
            "limit": 20,
        }
        markets = await PolyMarketData.fetch_markets(params)
        
        if not markets:
            print("❌ 未找到任何活跃市场")
            return
        
        print(f"✅ 找到 {len(markets)} 个活跃市场\\n")
        
        # 2. 查找 BTC 15m 市场
        btc_15m_markets = []
        for m in markets:
            slug = m.get("slug", "")
            if "btc-updown-" in slug and "15m" in slug:
                btc_15m_markets.append(m)
        
        if not btc_15m_markets:
            print("❌ 未找到 BTC 15分钟市场")
            print("\\n可用的市场 slugs：")
            for m in markets[:5]:
                print(f"  - {m.get('slug', 'Unknown')}")
            return
        
        print(f"✅ 找到 {len(btc_15m_markets)} 个 BTC 15m 市场\\n")
        
        # 3. 检查第一个市场的详细数据
        target_slug = btc_15m_markets[0].get("slug")
        print(f"📊 正在检查市场: {target_slug}\\n")
        
        market_data = await PolyMarketData.get_market(target_slug)
        
        if not market_data:
            print("❌ 无法获取市场详细数据")
            return
        
        # 4. 检查关键字段
        print("=" * 60)
        print("关键字段检查：")
        print("=" * 60)
        
        # Strike价格
        strike = market_data.get("strike")
        print(f"\\n✓ Strike (行权价): {strike}")
        if strike is None:
            print("  ⚠️  WARNING: 缺少 strike 字段！")
            print("  可能的替代字段：")
            for key in ["strikePrice", "strike_price", "strike_px", "strikePriceUsd"]:
                if key in market_data:
                    print(f"    - {key}: {market_data.get(key)}")
        else:
            print(f"  类型: {type(strike).__name__}")
        
        # Expiry时间
        expiry = market_data.get("expiry")
        print(f"\\n✓ Expiry (到期时间): {expiry}")
        if expiry is None:
            print("  ⚠️  WARNING: 缺少 expiry 字段！")
            print("  可能的替代字段：")
            for key in ["endDate", "end_date", "endTime", "end_time", "closeDate", "close_date"]:
                if key in market_data:
                    print(f"    - {key}: {market_data.get(key)}")
        else:
            print(f"  类型: {type(expiry).__name__}")
        
        # Token IDs
        token_ids = market_data.get("clobTokenIds", [])
        print(f"\\n✓ Token IDs: {token_ids}")
        
        # Condition ID
        condition_id = market_data.get("conditionId") or market_data.get("condition_id")
        print(f"\\n✓ Condition ID: {condition_id}")
        
        # 5. 完整市场数据（调试用）
        print("\\n" + "=" * 60)
        print("完整市场数据（前100个字符）：")
        print("=" * 60)
        market_json = json.dumps(market_data, indent=2, ensure_ascii=False)
        print(market_json[:1000] + "...\\n")
        
        # 6. 诊断结论
        print("=" * 60)
        print("诊断结论：")
        print("=" * 60)
        
        if strike is not None and expiry is not None:
            print("✅ 市场数据完整！策略可以正常计算公允价值。")
            print("\\n可能原因：")
            print("  1. 最小优势阈值太高 (min_edge=8%)")
            print("  2. 当前市场价格接近公允价值，无明显套利机会")
            print("\\n建议：降低 min_edge 到 3-5% 以查看更多信号")
        else:
            print("❌ 市场数据不完整！")
            missing = []
            if strike is None:
                missing.append("strike")
            if expiry is None:
                missing.append("expiry")
            print(f"  缺少字段: {', '.join(missing)}")
            print("\\n这就是为什么策略无法生成交易信号的原因。")
            print("\\n建议：检查 data_source.py 的 normalize_market 函数")
            print("      确保正确解析这些字段。")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_market_data())
