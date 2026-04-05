#!/usr/bin/env python3
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy_binance import BinanceLinearGateway
import asyncio

async def check():
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceLinearGateway, 'BINANCE_LINEAR')
    
    setting = {
        'API Key': os.environ.get('FUTURES_API_KEY', ''),
        'API Secret': os.environ.get('FUTURES_API_SECRET', ''),
        'Server': 'TESTNET',
        'Kline Stream': True,
        'Proxy Host': '',
        'Proxy Port': 0,
    }
    main_engine.connect(setting, 'BINANCE_LINEAR')
    await asyncio.sleep(3)
    
    accounts = main_engine.get_all_accounts()
    for acc in accounts:
        print(f"ACCOUNT: balance={acc.balance}, available={acc.available}")
    
    positions = main_engine.get_all_positions()
    for pos in positions:
        print(f"POSITION: {pos.symbol}, {pos.direction}, vol={pos.volume}, price={pos.price}, pnl={pos.pnl}")
    
    main_engine.close()

if __name__ == "__main__":
    asyncio.run(check())
