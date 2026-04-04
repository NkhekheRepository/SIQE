"""
SIQE V3 - VN.PY Native Live/Paper Trading Runner

Connects SIQE CTA strategy to VN.PY's live trading engine with
Binance gateway for paper trading or live execution.
"""
from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import LogData
from vnpy.trader.setting import SETTINGS

from vnpy_binance import BinanceSpotGateway
from vnpy.trader.constant import Exchange

from vnpy_ctastrategy import CtaStrategyApp
from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy

logger = logging.getLogger(__name__)


class SiqeLiveRunner:
    """Manages VN.PY live/paper trading with SIQE CTA strategy."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        server: str = "SIMULATOR",
        symbol: str = "btcusdt",
        exchange: str = "BINANCE",
        strategy_name: str = "siqe_live",
        strategy_params: Optional[Dict[str, Any]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.server = server
        self.symbol = symbol.lower()
        self.exchange = exchange
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params or {}
        self.log_level = log_level

        self.main_engine: Optional[MainEngine] = None
        self.event_engine: Optional[EventEngine] = None
        self.cta_app: Optional[CtaStrategyApp] = None
        self._running = False

    def setup(self) -> None:
        """Initialize VN.PY MainEngine, EventEngine, and gateway."""
        logging.basicConfig(level=getattr(logging, self.log_level.upper()))

        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)

        # Add Binance Spot gateway
        gateway = BinanceSpotGateway(self.event_engine)
        self.main_engine.add_gateway(gateway)

        # Add CTA Strategy app
        self.cta_app = CtaStrategyApp(self.main_engine)
        self.main_engine.add_app(self.cta_app)

        logger.info("VN.PY engine initialized")

    def connect(self) -> None:
        """Connect to Binance exchange."""
        if not self.main_engine:
            raise RuntimeError("Call setup() before connect()")

        gateway_setting = {
            "API Key": self.api_key,
            "API Secret": self.api_secret,
            "Server": self.server,
            "Kline Stream": True,
        }

        self.main_engine.connect(gateway_setting, "BINANCE_SPOT")
        logger.info(f"Connecting to Binance ({self.server})...")

    def add_strategy(self) -> None:
        """Add SIQE CTA strategy to the engine."""
        if not self.cta_app:
            raise RuntimeError("Call setup() before add_strategy()")

        cta_engine = self.cta_app.engine

        vt_symbol = f"{self.symbol}.{Exchange.BINANCE.value}"

        cta_engine.add_strategy(
            class_name="SiqeCtaStrategy",
            strategy_name=self.strategy_name,
            vt_symbol=vt_symbol,
            setting=self.strategy_params,
        )
        logger.info(f"Strategy '{self.strategy_name}' added for {vt_symbol}")

    def init_strategy(self) -> None:
        """Initialize strategy (loads history, calls on_init)."""
        if not self.cta_app:
            raise RuntimeError("Strategy not added yet")
        self.cta_app.engine.init_strategy(self.strategy_name)
        logger.info("Strategy initialized")

    def start_strategy(self) -> None:
        """Start strategy trading."""
        if not self.cta_app:
            raise RuntimeError("Strategy not added yet")
        self.cta_app.engine.start_strategy(self.strategy_name)
        self._running = True
        logger.info("Strategy started")

    def stop_strategy(self) -> None:
        """Stop strategy trading."""
        if not self.cta_app:
            return
        self.cta_app.engine.stop_strategy(self.strategy_name)
        self._running = False
        logger.info("Strategy stopped")

    def close(self) -> None:
        """Shut down all engines."""
        self.stop_strategy()
        if self.main_engine:
            self.main_engine.close()
        logger.info("VN.PY engine closed")

    def run(self) -> None:
        """Full lifecycle: setup, connect, add strategy, run until interrupted."""
        self.setup()
        self.connect()
        self.add_strategy()
        self.init_strategy()
        self.start_strategy()

        self._running = True

        def _signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            self._running = False

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info("SIQE live runner running. Press Ctrl+C to stop.")
        try:
            import time
            while self._running:
                time.sleep(1)
        finally:
            self.close()


def run_live(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Convenience function: run live/paper trading from config.

    Example config:
    {
        "api_key": "your_key",
        "api_secret": "your_secret",
        "server": "SIMULATOR",
        "symbol": "btcusdt",
        "strategy_name": "siqe_paper",
        "strategy_params": {"fixed_size": 1},
    }
    """
    if config is None:
        config = {}

    runner = SiqeLiveRunner(
        api_key=config.get("api_key", ""),
        api_secret=config.get("api_secret", ""),
        server=config.get("server", "SIMULATOR"),
        symbol=config.get("symbol", "btcusdt"),
        strategy_name=config.get("strategy_name", "siqe_live"),
        strategy_params=config.get("strategy_params", {}),
        log_level=config.get("log_level", "INFO"),
    )
    runner.run()


if __name__ == "__main__":
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    config = {
        "api_key": os.environ.get("BINANCE_API_KEY", ""),
        "api_secret": os.environ.get("BINANCE_API_SECRET", ""),
        "server": os.environ.get("EXCHANGE_SERVER", "SIMULATOR"),
        "symbol": "btcusdt",
        "strategy_name": "siqe_paper",
        "strategy_params": {
            "fixed_size": 1,
            "mr_boll_period": 20,
            "mom_fast_period": 10,
            "mom_slow_period": 30,
            "bo_donchian_period": 20,
        },
        "log_level": "INFO",
    }

    run_live(config)
