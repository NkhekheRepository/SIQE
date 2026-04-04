"""
SIQE V3 - VN.PY Native Live/Paper Trading Runner

Connects SIQE CTA strategy to VN.PY's live trading engine with
Binance gateway for spot or USDT-M futures paper trading/live execution.
"""
from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import LogData, SubscribeRequest

from vnpy_binance import BinanceSpotGateway, BinanceLinearGateway
from vnpy.trader.constant import Exchange

from vnpy_ctastrategy import CtaStrategyApp
from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy
from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy

logger = logging.getLogger(__name__)


class SiqeLiveRunner:
    """Manages VN.PY live/paper trading with SIQE CTA strategy."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        server: str = "SIMULATOR",
        symbol: str = "btcusdt",
        market_type: str = "spot",
        strategy_name: str = "siqe_live",
        strategy_params: Optional[Dict[str, Any]] = None,
        log_level: str = "INFO",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.server = server
        self.symbol = symbol.lower()
        self.market_type = market_type.lower()
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

        if self.market_type == "futures":
            self.main_engine.add_gateway(BinanceLinearGateway, "BINANCE_LINEAR")
            logger.info("Binance USDT-M Futures gateway added")
        else:
            self.main_engine.add_gateway(BinanceSpotGateway, "BINANCE_SPOT")
            logger.info("Binance Spot gateway added")

        self.main_engine.add_app(CtaStrategyApp)
        
        apps = self.main_engine.get_all_apps()
        self.cta_app = None
        for app in apps:
            if hasattr(app, '__class__') and app.__class__.__name__ == 'CtaStrategyApp':
                self.cta_app = app
                break
        if not self.cta_app:
            raise RuntimeError("Failed to get CtaStrategyApp")

        self.cta_engine = self.main_engine.get_engine("CtaStrategy")
        self.cta_engine.init_engine()
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
            "Proxy Host": "",
            "Proxy Port": 0,
        }

        gateway_name = "BINANCE_LINEAR" if self.market_type == "futures" else "BINANCE_SPOT"
        self.main_engine.connect(gateway_setting, gateway_name)
        logger.info(f"Connecting to Binance {self.market_type} ({self.server})...")
        
        import time
        time.sleep(3)
        
        symbol_map = {
            "btcusdt": "BTCUSDT_SWAP_BINANCE",
            "ethusdt": "ETHUSDT_SWAP_BINANCE",
            "solusdt": "SOLUSDT_SWAP_BINANCE",
            "bnbusdt": "BNBUSDT_SWAP_BINANCE",
            "xrpusdt": "XRPUSDT_SWAP_BINANCE",
            "dogeusdt": "DOGEUSDT_SWAP_BINANCE",
        }
        contract_symbol = symbol_map.get(self.symbol, self.symbol.upper() + "_SWAP_BINANCE")
        
        subscribe_req = SubscribeRequest(
            symbol=contract_symbol,
            exchange=Exchange.GLOBAL
        )
        gateway = self.main_engine.get_gateway(gateway_name)
        gateway.subscribe(subscribe_req)
        logger.info(f"Subscribed to {contract_symbol} on {gateway_name}")
        
        self._vt_symbol = f"{contract_symbol}.{Exchange.GLOBAL.value}"
        logger.info(f"Strategy will use vt_symbol: {self._vt_symbol}")

    def add_strategy(self) -> None:
        """Add SIQE CTA strategy to the engine."""
        if not self.cta_app:
            raise RuntimeError("Call setup() before add_strategy()")

        cta_engine = self.main_engine.get_engine("CtaStrategy")

        if self.market_type == "futures":
            class_name = "SiqeFuturesStrategy"
            vt_symbol = getattr(self, "_vt_symbol", None)
            if not vt_symbol:
                symbol_map = {
                    "btcusdt": "BTCUSDT_SWAP_BINANCE",
                    "ethusdt": "ETHUSDT_SWAP_BINANCE",
                    "solusdt": "SOLUSDT_SWAP_BINANCE",
                    "bnbusdt": "BNBUSDT_SWAP_BINANCE",
                    "xrpusdt": "XRPUSDT_SWAP_BINANCE",
                    "dogeusdt": "DOGEUSDT_SWAP_BINANCE",
                }
                contract_symbol = symbol_map.get(self.symbol, self.symbol.upper() + "_SWAP_BINANCE")
                vt_symbol = f"{contract_symbol}.{Exchange.GLOBAL.value}"
            
            from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
            cta_engine.classes[class_name] = SiqeFuturesStrategy
        else:
            class_name = "SiqeCtaStrategy"
            vt_symbol = f"{self.symbol}.{Exchange.GLOBAL.value}"
            
            from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy
            cta_engine.classes[class_name] = SiqeCtaStrategy

        cta_engine.add_strategy(
            class_name=class_name,
            strategy_name=self.strategy_name,
            vt_symbol=vt_symbol,
            setting=self.strategy_params,
        )
        logger.info(f"Strategy '{self.strategy_name}' ({class_name}) added for {vt_symbol}")

    def init_strategy(self) -> None:
        """Initialize strategy (loads history, calls on_init)."""
        if not self.cta_app:
            raise RuntimeError("Strategy not added yet")
        cta_engine = self.main_engine.get_engine("CtaStrategy")
        fut = cta_engine.init_strategy(self.strategy_name)
        if fut:
            fut.result()
        logger.info("Strategy initialized")

    def start_strategy(self) -> None:
        """Start strategy trading."""
        if not self.cta_app:
            raise RuntimeError("Strategy not added yet")
        cta_engine = self.main_engine.get_engine("CtaStrategy")
        cta_engine.start_strategy(self.strategy_name)
        self._running = True
        logger.info("Strategy started")

    def stop_strategy(self) -> None:
        """Stop strategy trading."""
        if not self.cta_app:
            return
        cta_engine = self.main_engine.get_engine("CtaStrategy")
        cta_engine.stop_strategy(self.strategy_name)
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

        logger.info(f"SIQE live runner running ({self.market_type}). Press Ctrl+C to stop.")
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
        "server": "TESTNET",
        "market_type": "futures",
        "symbol": "btcusdt",
        "strategy_name": "siqe_futures_paper",
        "strategy_params": {"leverage": 50, "fixed_volume": 0.01},
    }
    """
    if config is None:
        config = {}

    runner = SiqeLiveRunner(
        api_key=config.get("api_key", ""),
        api_secret=config.get("api_secret", ""),
        server=config.get("server", "SIMULATOR"),
        symbol=config.get("symbol", "btcusdt"),
        market_type=config.get("market_type", "spot"),
        strategy_name=config.get("strategy_name", "siqe_live"),
        strategy_params=config.get("strategy_params", {}),
        log_level=config.get("log_level", "INFO"),
    )
    runner.run()


if __name__ == "__main__":
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    config = {
        "api_key": os.environ.get("EXCHANGE_API_KEY", ""),
        "api_secret": os.environ.get("EXCHANGE_API_SECRET", ""),
        "server": os.environ.get("EXCHANGE_SERVER", "SIMULATOR"),
        "market_type": "spot",
        "symbol": "btcusdt",
        "strategy_name": "siqe_paper",
        "strategy_params": {
            "fixed_volume": 0.01,
            "mr_boll_period": 20,
            "mom_fast_period": 10,
            "mom_slow_period": 30,
            "bo_donchian_period": 20,
        },
        "log_level": "INFO",
    }

    run_live(config)
