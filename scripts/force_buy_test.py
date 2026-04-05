#!/usr/bin/env python3
"""
Quick Test: Force a BUY order to verify the full trade callback chain.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import OrderRequest
from vnpy.trader.constant import Direction, Offset, OrderType, Exchange
from vnpy_binance import BinanceLinearGateway

async def main():
    print("=" * 50)
    print("FORCE BUY TEST")
    print("=" * 50)
    
    api_key = __import__('os').environ.get('FUTURES_API_KEY', '')
    api_secret = __import__('os').environ.get('FUTURES_API_SECRET', '')
    
    print(f"API Key: {api_key[:10]}...")
    print(f"Time: {datetime.now()}")
    print()
    
    # Create engines
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceLinearGateway, "BINANCE_LINEAR")
    
    # Connect
    setting = {
        "API Key": api_key,
        "API Secret": api_secret,
        "Server": "TESTNET",
        "Kline Stream": True,
        "Proxy Host": "",
        "Proxy Port": 0,
    }
    main_engine.connect(setting, "BINANCE_LINEAR")
    print("Connecting to Binance TESTNET...")
    
    await asyncio.sleep(3)
    print("Connected!")
    print()
    
    # Get gateway
    gateway = main_engine.get_gateway("BINANCE_LINEAR")
    
    # Create market buy order - minimum 100 USDT notional
    req = OrderRequest(
        symbol="BTCUSDT_SWAP_BINANCE",
        exchange=Exchange.GLOBAL,
        direction=Direction.LONG,
        type=OrderType.MARKET,
        volume=0.002,  # 0.002 BTC = ~$134 (above 100 USDT minimum)
        price=0,
        offset=Offset.OPEN,
        reference="FORCE_BUY_TEST"
    )
    
    print(f"ORDER REQUEST: {req}")
    print()
    print("Sending MARKET BUY order for 0.002 BTC (~$134)...")
    
    vt_orderid = gateway.send_order(req)
    print(f"Order sent! VT_OrderID: {vt_orderid}")
    print()
    
    # Wait for fill
    print("Waiting for fill (10 seconds)...")
    await asyncio.sleep(10)
    
    # Check positions
    print("\nChecking positions via MainEngine...")
    try:
        pos = main_engine.get_all_positions()
        print(f"All positions: {pos}")
    except Exception as e:
        print(f"Could not get positions: {e}")
    
    print()
    print("=" * 50)
    print("TEST COMPLETE")
    print("Check /tmp/autonomous.log for trade callback")
    print("=" * 50)
    
    main_engine.close()

if __name__ == "__main__":
    asyncio.run(main())
