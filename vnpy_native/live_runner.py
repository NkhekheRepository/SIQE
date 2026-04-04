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
        
        self.siqe_engine = None
        self._trade_count = 0
        self._learning_interval = 25

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
        
        self._strategy_class_name = class_name

    def register_strategy_callbacks(self) -> None:
        """Register SIQEEngine callbacks on the strategy instance."""
        cta_engine = self.main_engine.get_engine("CtaStrategy")
        strategy_instances = cta_engine.strategies
        
        for strategy in strategy_instances.values():
            if strategy.strategy_name == self.strategy_name:
                strategy.set_trade_callback(self._on_trade)
                logger.info(f"Registered trade callback for strategy '{self.strategy_name}'")
                break

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

    def set_siqe_engine(self, engine) -> None:
        """Connect SIQEEngine for risk validation and learning."""
        self.siqe_engine = engine
        logger.info("SIQEEngine connected to live runner")
        if hasattr(engine, 'risk_engine'):
            logger.info("Risk validation enabled")
        if hasattr(engine, 'learning_engine'):
            logger.info("Learning engine enabled")

    def _on_trade(self, trade) -> None:
        """Handle completed trade - send to SIQEEngine for risk/learning."""
        self._trade_count += 1
        
        if not self.siqe_engine:
            logger.debug(f"Trade #{self._trade_count}: {trade.direction} {trade.volume} @ {trade.price} (no SIQEEngine)")
            return
        
        try:
            trade_data = {
                'trade_id': getattr(trade, 'trade_id', f"live_{self._trade_count}"),
                'symbol': trade.symbol,
                'direction': str(trade.direction),
                'volume': trade.volume,
                'price': trade.price,
                'cost': getattr(trade, 'cost', 0),
                'commission': getattr(trade, 'commission', 0),
                'time': getattr(trade, 'datetime', None),
            }
            
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._process_trade_async(trade_data))
            else:
                loop.run_until_complete(self._process_trade_async(trade_data))
                
        except Exception as e:
            logger.error(f"Error processing trade callback: {e}")

    async def _process_trade_async(self, trade_data: Dict[str, Any]) -> None:
        """Process trade result asynchronously through SIQEEngine pipeline."""
        try:
            if hasattr(self.siqe_engine, 'risk_engine') and self.siqe_engine.risk_engine:
                trade_pnl = trade_data.get('pnl', 0)
                
                await self.siqe_engine.risk_engine.update_trade_result(trade_pnl)
                
                risk_status = self.siqe_engine.risk_engine.get_circuit_breaker_status()
                active_breakers = [k for k, v in risk_status.items() if v.get('is_active')]
                if active_breakers:
                    logger.warning(f"Circuit breakers active: {active_breakers}")
                
                if self._trade_count % self._learning_interval == 0:
                    logger.info(f"Triggering learning update at trade #{self._trade_count}")
                    if hasattr(self.siqe_engine, 'state_manager'):
                        perf = await self.siqe_engine.state_manager.get_trade_statistics()
                        perf['sample_size'] = self._trade_count
                    else:
                        perf = {'sample_size': self._trade_count, 'total_pnl': trade_pnl}
                    
                    if hasattr(self.siqe_engine, 'learning_engine'):
                        await self.siqe_engine.learning_engine.update_parameters(
                            "SiqeFuturesStrategy", perf
                        )
                        logger.info("Learning update completed")
                    
            logger.info(f"Trade #{self._trade_count}: {trade_data['direction']} "
                       f"{trade_data['volume']} @ {trade_data['price']}")
            
        except Exception as e:
            logger.error(f"Error in _process_trade_async: {e}")

    def get_risk_status(self) -> Dict[str, Any]:
        """Get current risk status from SIQEEngine."""
        if not self.siqe_engine or not hasattr(self.siqe_engine, 'risk_engine'):
            return {"status": "no_risk_engine"}
        
        risk_engine = self.siqe_engine.risk_engine
        return {
            "daily_pnl": risk_engine.daily_pnl,
            "consecutive_losses": risk_engine.consecutive_losses,
            "circuit_breakers": risk_engine.get_circuit_breaker_status(),
            "trades_today": self._trade_count,
        }

    def run(self) -> None:
        """Full lifecycle: setup, connect, add strategy, run until interrupted."""
        self.setup()
        self.connect()
        self.add_strategy()
        self.init_strategy()
        
        if self.siqe_engine:
            self.register_strategy_callbacks()
        
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
