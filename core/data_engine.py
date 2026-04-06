"""
Data Engine Module
Handles market data acquisition and preprocessing.
Deterministic: uses EventClock instead of datetime.now().
Phase 1: Replaced simulated data with real ccxt REST/WS market data.
"""
import asyncio
import logging
import os
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd

from core.clock import EventClock
from models.trade import MarketEvent, SignalType
from .ws_streamer import WebSocketStreamer

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

        # Real market data infrastructure
        self._exchange = None
        self._ws_streamer: Optional[WebSocketStreamer] = None
        self._historical_cache: Dict[str, pd.DataFrame] = {}
        self._last_prices: Dict[str, float] = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._connection_state = "disconnected"
        self._use_real_data = True
        self._parquet_path = None
        self._ccxt_exchange_name = "binance"
        self._ccxt_market_type = "swap"
        self._data_source_mode = "websocket"  # websocket or rest

    def set_execution_adapter(self, execution_adapter):
        self.execution_adapter = execution_adapter

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Data Engine...")

            # Load configuration
            self._use_real_data = self.settings.get("use_real_data", True)
            self._parquet_path = self.settings.get("historical_data_path", "data/binance_futures/parquet/")
            self._ccxt_exchange_name = self.settings.get("ccxt_exchange", "binance")
            self._ccxt_market_type = self.settings.get("ccxt_market_type", "swap")
            self._data_source_mode = self.settings.get("data_source", "websocket")

            # Initialize ccxt exchange for real market data (REST fallback)
            if self._use_real_data:
                await self._init_ccxt_exchange()
                
                # Initialize WebSocket streamer if in websocket mode
                if self._data_source_mode == "websocket":
                    self._ws_streamer = WebSocketStreamer(self.settings, self.clock)
                    await self._ws_streamer.initialize()
                    await self._ws_streamer.start_streaming()

            # Load historical parquet data for fallback
            await self._load_historical_cache()

            self.is_initialized = True
            symbols = self.settings.get("binance_symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT"])
            await self.subscribe(symbols)
            logger.info(f"Data Engine initialized with symbols: {symbols}, real_data={self._use_real_data}, mode={self._data_source_mode}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Data Engine: {e}")
            # Still mark as initialized so system can run with parquet fallback
            self.is_initialized = True
            return True

    async def _init_ccxt_exchange(self):
        """Initialize ccxt async exchange for real market data."""
        try:
            import ccxt.async_support as ccxt

            exchange_class = getattr(ccxt, self._ccxt_exchange_name.lower(), None)
            if exchange_class is None:
                raise ValueError(f"Unknown ccxt exchange: {self._ccxt_exchange_name}")

            exchange_config = {
                "enableRateLimit": True,
                "options": {
                    "defaultType": self._ccxt_market_type,
                },
            }

            # Add API keys if available (for testnet or live)
            api_key = self.settings.get("futures_api_key", "") or self.settings.get("exchange_api_key", "")
            api_secret = self.settings.get("futures_api_secret", "") or self.settings.get("exchange_api_secret", "")
            if api_key and api_secret:
                exchange_config["apiKey"] = api_key
                exchange_config["secret"] = api_secret
                exchange_server = self.settings.get("exchange_server", "TESTNET")
                if exchange_server == "TESTNET":
                    exchange_config["options"]["defaultType"] = "swap"
                    if self._ccxt_exchange_name.lower() == "binance":
                        exchange_config["urls"] = {
                            "api": {
                                "public": "https://testnet.binancefuture.com/fapi",
                                "private": "https://testnet.binancefuture.com/fapi",
                            }
                        }
                        exchange_config["options"]["recvWindow"] = 10000

            self._exchange = exchange_class(exchange_config)
            logger.info(f"CCXT exchange initialized: {self._ccxt_exchange_name} ({self._ccxt_market_type})")
            self._connection_state = "connected"
            self._reconnect_attempts = 0
        except Exception as e:
            logger.warning(f"Failed to initialize CCXT exchange: {e}. Will use parquet fallback.")
            self._exchange = None
            self._connection_state = "error"

    async def _load_historical_cache(self):
        """Load historical parquet data for fallback and warm-start."""
        try:
            parquet_path = self._parquet_path
            if not parquet_path or not os.path.isdir(parquet_path):
                logger.warning(f"Parquet path not found: {parquet_path}")
                return

            for filename in os.listdir(parquet_path):
                if filename.endswith(".parquet") and "_train" not in filename and "_test" not in filename:
                    symbol = filename.replace(".parquet", "").upper()
                    try:
                        df = pd.read_parquet(os.path.join(parquet_path, filename))
                        # Normalize column names
                        cols_lower = {c.lower(): c for c in df.columns}
                        rename_map = {}
                        for std_col in ["open", "high", "low", "close", "volume"]:
                            if std_col in cols_lower:
                                rename_map[cols_lower[std_col]] = std_col
                        df = df.rename(columns=rename_map)

                        if "close" in df.columns:
                            last_close = float(df["close"].iloc[-1])
                            self._last_prices[symbol] = last_close
                            self._historical_cache[symbol] = df
                            logger.info(f"Loaded {len(df)} bars for {symbol} from parquet (last close: {last_close:.2f})")
                    except Exception as e:
                        logger.warning(f"Failed to load parquet file {filename}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load historical cache: {e}")

    async def get_latest_data(self) -> Optional[Dict[str, MarketEvent]]:
        if not self.is_initialized:
            return None

        try:
            self._event_counter += 1
            seq = self.clock.tick()

            # Priority: 1) WebSocket streamer data, 2) Live data from execution adapter bridge, 
            # 3) CCXT REST, 4) Parquet fallback
            if self._ws_streamer and self._data_source_mode == "websocket":
                # For now, we'll get data from WebSocket via the execution adapter bridge
                # In a full implementation, the WebSocket streamer would emit events directly
                market_data = await self._get_live_market_data(seq)
            elif self.execution_adapter and self.execution_adapter.is_initialized and self.execution_adapter.bridge:
                market_data = await self._get_live_market_data(seq)
            elif self._exchange and self._connection_state == "connected":
                market_data = await self._get_ccxt_market_data(seq)
            else:
                market_data = self._get_fallback_market_data(seq)

            for symbol, event in market_data.items():
                self.data_buffer[symbol] = event

            return market_data

        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            # Try fallback on error
            try:
                seq = self.clock.tick()
                market_data = self._get_fallback_market_data(seq)
                for symbol, event in market_data.items():
                    self.data_buffer[symbol] = event
                return market_data
            except Exception as fallback_error:
                logger.error(f"Fallback market data also failed: {fallback_error}")
                return None

    async def _get_live_market_data(self, seq: int) -> Dict[str, MarketEvent]:
        """Get real market data via execution adapter bridge (VN.PY) or WebSocket streamer."""
        market_data = {}
        symbols = list(self.subscriptions) if self.subscriptions else ["BTCUSDT", "ETHUSDT"]

        # Try WebSocket streamer first if available
        if self._ws_streamer and self._data_source_mode == "websocket":
            try:
                # Get latest data from WebSocket streamer (this would need to be implemented in WS streamer)
                # For now, fall back to execution adapter
                pass
            except Exception as e:
                logger.warning(f"Failed to get data from WebSocket streamer: {e}")

        # Fall back to execution adapter bridge
        for symbol in symbols:
            try:
                if self.execution_adapter and self.execution_adapter.is_initialized and self.execution_adapter.bridge:
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
                            bid=round(bid, 8),
                            ask=round(ask, 8),
                            volume=round(volume, 8),
                            volatility=round(volatility, 6),
                            event_seq=seq,
                        )
                        self._last_prices[symbol] = mid
            except Exception as e:
                logger.warning(f"Failed to get live data for {symbol}: {e}")

        return market_data

    async def _get_ccxt_market_data(self, seq: int) -> Dict[str, MarketEvent]:
        """Get real market data via CCXT REST API."""
        market_data = {}
        symbols = list(self.subscriptions) if self.subscriptions else ["BTCUSDT", "ETHUSDT"]

        for symbol in symbols:
            try:
                # Convert symbol format: BTCUSDT -> BTC/USDT for CCXT
                ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}"

                ticker = await self._exchange.fetch_ticker(ccxt_symbol)
                bid = ticker.get("bid")
                ask = ticker.get("ask")
                volume = ticker.get("baseVolume", 0.0)

                if bid and ask and bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    volatility = abs(ask - bid) / mid if mid > 0 else 0.001
                    market_data[symbol] = MarketEvent(
                        event_id=f"evt_{symbol.lower()}_{seq}",
                        symbol=symbol,
                        bid=round(bid, 8),
                        ask=round(ask, 8),
                        volume=round(volume, 8) if volume else 0.0,
                        volatility=round(volatility, 6),
                        event_seq=seq,
                    )
                    self._last_prices[symbol] = mid
                    self._connection_state = "connected"
                    self._reconnect_attempts = 0
                else:
                    raise ValueError(f"Invalid ticker data for {symbol}: bid={bid}, ask={ask}")

            except Exception as e:
                logger.warning(f"CCXT fetch failed for {symbol}: {e}")
                self._connection_state = "error"
                self._reconnect_attempts += 1

                # Attempt reconnection if too many failures
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.warning("Too many CCXT failures, attempting reconnection...")
                    await self._reconnect_exchange()

                # Fallback to last known price or parquet data
                if symbol in self._last_prices:
                    price = self._last_prices[symbol]
                    spread = price * 0.0001
                    market_data[symbol] = MarketEvent(
                        event_id=f"evt_{symbol.lower()}_{seq}_fallback",
                        symbol=symbol,
                        bid=round(price - spread / 2, 8),
                        ask=round(price + spread / 2, 8),
                        volume=0.0,
                        volatility=0.001,
                        event_seq=seq,
                    )

        return market_data

    async def _reconnect_exchange(self):
        """Reconnect CCXT exchange with exponential backoff."""
        try:
            if self._exchange:
                await self._exchange.close()
            self._exchange = None
            delay = min(30, 2 ** self._reconnect_attempts)
            logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempts})")
            await asyncio.sleep(delay)
            await self._init_ccxt_exchange()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")

    def _get_fallback_market_data(self, seq: int) -> Dict[str, MarketEvent]:
        """Fallback: use last known prices from parquet data. NO random walk."""
        market_data = {}
        symbols = list(self.subscriptions) if self.subscriptions else ["BTCUSDT", "ETHUSDT"]

        for symbol in symbols:
            if symbol in self._last_prices:
                price = self._last_prices[symbol]
                spread = price * 0.0001
                market_data[symbol] = MarketEvent(
                    event_id=f"evt_{symbol.lower()}_{seq}_cached",
                    symbol=symbol,
                    bid=round(price - spread / 2, 8),
                    ask=round(price + spread / 2, 8),
                    volume=0.0,
                    volatility=0.001,
                    event_seq=seq,
                )
            elif symbol in self._historical_cache:
                df = self._historical_cache[symbol]
                if "close" in df.columns and len(df) > 0:
                    price = float(df["close"].iloc[-1])
                    self._last_prices[symbol] = price
                    spread = price * 0.0001
                    market_data[symbol] = MarketEvent(
                        event_id=f"evt_{symbol.lower()}_{seq}_parquet",
                        symbol=symbol,
                        bid=round(price - spread / 2, 8),
                        ask=round(price + spread / 2, 8),
                        volume=0.0,
                        volatility=0.001,
                        event_seq=seq,
                    )
            else:
                logger.warning(f"No fallback data for {symbol}")

        return market_data

    async def subscribe(self, symbols: List[str]):
        self.subscriptions.update(symbols)
        logger.info(f"Subscribed to symbols: {symbols}")

    async def unsubscribe(self, symbols: List[str]):
        self.subscriptions.difference_update(symbols)
        logger.info(f"Unsubscribed from symbols: {symbols}")

    async def get_historical_data(self, symbol: str, limit: int = 100) -> Optional[pd.DataFrame]:
        """Get historical data from parquet cache or CCXT REST."""
        try:
            # First try parquet cache
            if symbol in self._historical_cache:
                df = self._historical_cache[symbol].copy()
                if len(df) > limit:
                    df = df.tail(limit)
                return df

            # Try fetching from CCXT
            if self._exchange:
                ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
                ohlcv = await self._exchange.fetch_ohlcv(ccxt_symbol, timeframe="15m", limit=limit)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    self._historical_cache[symbol] = df
                    return df

            logger.warning(f"No historical data available for {symbol}")
            return None
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return None

    async def get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculate ATR from historical data for SL/TP calculations."""
        try:
            df = await self.get_historical_data(symbol, limit=period + 1)
            if df is None or len(df) < period + 1:
                return None

            high = df["high"].values
            low = df["low"].values
            close = df["close"].values

            tr1 = high[1:] - low[1:]
            tr2 = abs(high[1:] - close[:-1])
            tr3 = abs(low[1:] - close[:-1])
            tr = np.maximum(np.maximum(tr1, tr2), tr3)

            atr = np.mean(tr[-period:])
            return float(atr)
        except Exception as e:
            logger.error(f"Error calculating ATR for {symbol}: {e}")
            return None

    async def shutdown(self):
        logger.info("Shutting down Data Engine...")
        self.is_initialized = False

        # Shutdown WebSocket streamer first
        if self._ws_streamer:
            try:
                await self._ws_streamer.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down WebSocket streamer: {e}")

        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as e:
                logger.warning(f"Error closing exchange: {e}")

        self.subscriptions.clear()
        self.data_buffer.clear()
        logger.info("Data Engine shutdown complete")
