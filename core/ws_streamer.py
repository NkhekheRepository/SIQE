"""
WebSocket Streaming Module
Live exchange WebSocket streaming using ccxt.pro for SIQE V3.
"""
import asyncio
import hashlib
import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Optional

import ccxt.pro as ccxtpro
import pandas as pd

from config.settings import Settings
from models.trade import MarketEvent

logger = logging.getLogger("siqe.ws_streamer")


class WebSocketStreamer:
    """Manages WebSocket connections to exchange for live market data streaming."""

    RECONNECT_MIN_DELAY = 1.0
    RECONNECT_MAX_DELAY = 60.0
    RECONNECT_MAX_ATTEMPTS = 20
    OHLCV_BUFFER_DEPTH = 500
    DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    def __init__(self, settings: Settings, clock: Optional[Any] = None):
        self.settings = settings
        self.clock = clock
        self._exchange: Optional[ccxtpro.Exchange] = None
        self._running = False
        self._connection_state = "disconnected"
        self._message_count = 0
        self._reconnect_attempts = 0
        self._latency_ms = 0.0
        self._ohlcv_buffers: dict[str, deque] = {}
        self._latest_ticker_data: dict[str, dict] = {}
        self._subscribed_symbols: set[str] = set()
        self._event_seq = 0
        self._tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def connection_state(self) -> str:
        return self._connection_state

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_attempts

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    def _get_symbols(self) -> list[str]:
        symbols = self.settings.get("binance_symbols", self.DEFAULT_SYMBOLS)
        if not symbols:
            symbols = self.DEFAULT_SYMBOLS
        return symbols

    def _init_ohlcv_buffer(self, symbol: str) -> None:
        if symbol not in self._ohlcv_buffers:
            self._ohlcv_buffers[symbol] = deque(maxlen=self.OHLCV_BUFFER_DEPTH)

    def _make_event_id(self, symbol: str, ts: float) -> str:
        raw = f"{symbol}:{ts}:{time.monotonic_ns()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _next_seq(self) -> int:
        if self.clock is not None:
            try:
                return int(self.clock.tick())
            except Exception:
                pass
        self._event_seq += 1
        return self._event_seq

    def _build_exchange(self) -> ccxtpro.Exchange:
        exchange_name = self.settings.ccxt_exchange
        exchange_class = getattr(ccxtpro, exchange_name)
        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {
                "defaultType": self.settings.ccxt_market_type,
            },
        }
        if self.settings.futures_api_key:
            config["apiKey"] = self.settings.futures_api_key
        if self.settings.futures_api_secret:
            config["secret"] = self.settings.futures_secret if hasattr(self.settings, "futures_secret") else self.settings.futures_api_secret
        exchange = exchange_class(config)
        return exchange

    async def initialize(self) -> None:
        self._exchange = self._build_exchange()
        symbols = self._get_symbols()
        await self.subscribe(symbols)
        self._connection_state = "initialized"
        logger.info("WebSocketStreamer initialized for symbols: %s", symbols)

    async def subscribe(self, symbols: list[str]) -> None:
        async with self._lock:
            for sym in symbols:
                self._subscribed_symbols.add(sym)
                self._init_ohlcv_buffer(sym)
        logger.info("Subscribed to symbols: %s", symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        async with self._lock:
            for sym in symbols:
                self._subscribed_symbols.discard(sym)
                self._ohlcv_buffers.pop(sym, None)
        logger.info("Unsubscribed from symbols: %s", symbols)

    async def _watch_ohlcv_loop(self) -> None:
        while self._running and not self._shutdown_event.is_set():
            try:
                for symbol in list(self._subscribed_symbols):
                    if not self._running:
                        break
                    ohlcv = await self._exchange.watch_ohlcv(symbol)
                    self._message_count += 1
                    self._on_ohlcv(symbol, ohlcv)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("OHLCV stream error: %s", exc)
                if not self._running:
                    break
                await self._handle_reconnect()

    async def _watch_ticker_loop(self) -> None:
        while self._running and not self._shutdown_event.is_set():
            try:
                for symbol in list(self._subscribed_symbols):
                    if not self._running:
                        break
                    ticker = await self._exchange.watch_ticker(symbol)
                    self._message_count += 1
                    self._on_ticker(symbol, ticker)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Ticker stream error: %s", exc)
                if not self._running:
                    break
                await self._handle_reconnect()

    def _on_ohlcv(self, symbol: str, ohlcv: list[list]) -> None:
        for candle in ohlcv:
            self._ohlcv_buffers[symbol].append(candle)

    def _on_ticker(self, symbol: str, ticker: dict) -> None:
        start = time.monotonic()
        bid = ticker.get("bid")
        ask = ticker.get("ask")
        volume = ticker.get("baseVolume", 0.0) or 0.0
        if bid is None or ask is None:
            return
        close_prices = [c[4] for c in self._ohlcv_buffers.get(symbol, []) if len(c) >= 5]
        if len(close_prices) >= 2:
            returns = [
                (close_prices[i] - close_prices[i - 1]) / close_prices[i - 1]
                for i in range(1, len(close_prices))
            ]
            volatility = float(pd.Series(returns).std()) if len(returns) > 1 else 0.0
        else:
            volatility = 0.0
        event = MarketEvent(
            event_id=self._make_event_id(symbol, ticker.get("timestamp", time.time())),
            symbol=symbol,
            bid=float(bid),
            ask=float(ask),
            volume=float(volume),
            volatility=volatility,
            event_seq=self._next_seq(),
        )
        self._latency_ms = (time.monotonic() - start) * 1000
        logger.debug("MarketEvent: %s bid=%s ask=%s vol=%s", symbol, bid, ask, volume)
        
        # Store latest ticker data for direct access
        self._latest_ticker_data[symbol] = {
            'bid': float(bid),
            'ask': float(ask),
            'volume': float(volume),
            'timestamp': ticker.get('timestamp', time.time() * 1000),
            'volatility': volatility
        }

    async def _handle_reconnect(self) -> None:
        if self._reconnect_attempts >= self.RECONNECT_MAX_ATTEMPTS:
            logger.error("Max reconnect attempts reached. Giving up.")
            self._connection_state = "failed"
            self._running = False
            return
        delay = min(
            self.RECONNECT_MIN_DELAY * (2 ** self._reconnect_attempts),
            self.RECONNECT_MAX_DELAY,
        )
        self._reconnect_attempts += 1
        self._connection_state = "reconnecting"
        logger.info(
            "Reconnecting (attempt %d/%d) in %.1fs...",
            self._reconnect_attempts,
            self.RECONNECT_MAX_ATTEMPTS,
            delay,
        )
        await asyncio.sleep(delay)
        try:
            if self._exchange:
                await self._exchange.close()
        except Exception:
            pass
        self._exchange = self._build_exchange()
        self._connection_state = "connected"
        logger.info("Reconnected successfully.")
        self._reconnect_attempts = 0

    async def start_streaming(self) -> None:
        if not self._exchange:
            raise RuntimeError("Call initialize() before start_streaming()")
        self._running = True
        self._shutdown_event.clear()
        self._connection_state = "connected"
        self._reconnect_attempts = 0
        logger.info("Starting WebSocket streaming for symbols: %s", self._subscribed_symbols)
        ohlcv_task = asyncio.create_task(self._watch_ohlcv_loop())
        ticker_task = asyncio.create_task(self._watch_ticker_loop())
        self._tasks = [ohlcv_task, ticker_task]
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._connection_state = "disconnected"

    async def get_latest_ohlcv(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        buffer = self._ohlcv_buffers.get(symbol, deque())
        rows = list(buffer)[-limit:]
        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    async def get_latest_ticker(self, symbol: str) -> Optional[dict]:
        """Get the latest ticker data for a symbol."""
        return self._latest_ticker_data.get(symbol)

    async def get_orderbook_snapshot(self, symbol: str) -> dict[str, Any]:
        if not self._exchange:
            raise RuntimeError("Exchange not initialized")
        ob = await self._exchange.watch_order_book(symbol)
        bid = ob["bids"][0][0] if ob["bids"] else None
        ask = ob["asks"][0][0] if ob["asks"] else None
        spread = (ask - bid) if (bid is not None and ask is not None) else None
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "timestamp": ob.get("timestamp"),
        }

    async def shutdown(self) -> None:
        logger.info("Shutting down WebSocketStreamer...")
        self._running = False
        self._shutdown_event.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as exc:
                logger.warning("Error closing exchange: %s", exc)
        self._connection_state = "disconnected"
        logger.info("WebSocketStreamer shut down.")
