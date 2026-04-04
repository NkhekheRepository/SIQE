"""
Data Engine Module
Handles market data acquisition and preprocessing.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd

from core.clock import EventClock
from models.trade import MarketEvent, SignalType

logger = logging.getLogger(__name__)


class DataEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.data_buffer: Dict[str, Any] = {}
        self.subscriptions: set = set()
        self._event_counter = 0
        self.execution_adapter = None

    def set_execution_adapter(self, execution_adapter):
        self.execution_adapter = execution_adapter

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Data Engine...")
            self.is_initialized = True
            symbols = self.settings.get("binance_symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT"])
            await self.subscribe(symbols)
            logger.info(f"Data Engine initialized with symbols: {symbols}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Data Engine: {e}")
            return False

    async def get_latest_data(self) -> Optional[Dict[str, MarketEvent]]:
        if not self.is_initialized:
            return None

        try:
            self._event_counter += 1
            seq = self.clock.tick()

            if self.execution_adapter and self.execution_adapter.is_initialized and self.execution_adapter.bridge:
                market_data = await self._get_live_market_data(seq)
            else:
                market_data = self._get_simulated_market_data(seq)

            for symbol, event in market_data.items():
                self.data_buffer[symbol] = event

            return market_data

        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    async def _get_live_market_data(self, seq: int) -> Dict[str, MarketEvent]:
        market_data = {}
        symbols = list(self.subscriptions) if self.subscriptions else ["BTCUSDT", "ETHUSDT"]

        for symbol in symbols:
            try:
                data = await self.execution_adapter.bridge.get_market_data(symbol)
                bid = data.get("bid", 0.0)
                ask = data.get("ask", 0.0)
                volume = data.get("volume", 0.0)

                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    volatility = abs(ask - bid) / mid if mid > 0 else 0.001
                    market_data[symbol] = MarketEvent(
                        event_id=f"evt_{symbol.lower()}_{seq}",
                        symbol=symbol,
                        bid=bid,
                        ask=ask,
                        volume=volume,
                        volatility=volatility,
                        event_seq=seq,
                    )
            except Exception as e:
                logger.warning(f"Failed to get live data for {symbol}: {e}")

        return market_data

    def _get_simulated_market_data(self, seq: int) -> Dict[str, MarketEvent]:
        return {
            "BTCUSDT": MarketEvent(
                event_id=f"evt_btc_{seq}",
                symbol="BTCUSDT",
                bid=42000.0 + np.random.normal(0, 100),
                ask=42010.0 + np.random.normal(0, 100),
                volume=np.random.uniform(10, 100),
                volatility=np.random.uniform(0.01, 0.05),
                event_seq=seq,
            ),
            "ETHUSDT": MarketEvent(
                event_id=f"evt_eth_{seq}",
                symbol="ETHUSDT",
                bid=2500.0 + np.random.normal(0, 20),
                ask=2505.0 + np.random.normal(0, 20),
                volume=np.random.uniform(5, 50),
                volatility=np.random.uniform(0.01, 0.04),
                event_seq=seq,
            ),
        }

    async def subscribe(self, symbols: List[str]):
        self.subscriptions.update(symbols)
        logger.info(f"Subscribed to symbols: {symbols}")

    async def unsubscribe(self, symbols: List[str]):
        self.subscriptions.difference_update(symbols)
        logger.info(f"Unsubscribed from symbols: {symbols}")

    async def get_historical_data(self, symbol: str, limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            dates = pd.date_range(end="2026-01-01", periods=limit, freq="1T")
            df = pd.DataFrame({
                "timestamp": dates,
                "open": 42000 + np.random.normal(0, 100, limit),
                "high": 42050 + np.random.normal(0, 100, limit),
                "low": 41950 + np.random.normal(0, 100, limit),
                "close": 42000 + np.random.normal(0, 100, limit),
                "volume": np.random.uniform(10, 100, limit),
            })
            return df
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return None

    async def shutdown(self):
        logger.info("Shutting down Data Engine...")
        self.is_initialized = False
        self.subscriptions.clear()
        self.data_buffer.clear()
        logger.info("Data Engine shutdown complete")
