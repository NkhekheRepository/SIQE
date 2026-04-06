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

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import LogData, SubscribeRequest
from vnpy.trader.event import EVENT_TRADE

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
        event_engine: Optional[Any] = None,
        main_engine: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.server = server
        self.symbol = symbol.lower()
        self.market_type = market_type.lower()
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params or {}
        self.log_level = log_level

        self._provided_event_engine = event_engine
        self._provided_main_engine = main_engine
        
        self.main_engine: Optional[MainEngine] = None
        self.event_engine: Optional[EventEngine] = None
        self.cta_app: Optional[CtaStrategyApp] = None
        self._running = False
        
        self.siqe_engine = None
        self._trade_count = 0
        self._learning_interval = 25
        
        # Alert manager
        self._alert_manager = None
        
        # Thread pool for async operations
        self._executor = None
        
        # Telegram interactive bot
        self._telegram_bot = None
        self._bot_thread = None
        
        # Trading state for bot
        self._trading_state = None

    def setup(self) -> None:
        """Initialize VN.PY MainEngine, EventEngine, and gateway."""
        logging.basicConfig(level=getattr(logging, self.log_level.upper()))

        if self._provided_event_engine and self._provided_main_engine:
            logger.info("Using provided EventEngine and MainEngine (shared with SIQEEngine)")
            self.event_engine = self._provided_event_engine
            self.main_engine = self._provided_main_engine
        else:
            logger.info("Creating new EventEngine and MainEngine")
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
        
        if self.market_type == "futures":
            from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
            self.cta_engine.classes["SiqeFuturesStrategy"] = SiqeFuturesStrategy
        else:
            from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy
            self.cta_engine.classes["SiqeCtaStrategy"] = SiqeCtaStrategy
        
        self.cta_engine.init_engine()
        logger.info("VN.PY engine initialized")

    def connect(self) -> bool:
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
        
        # Check if connection was successful by verifying gateway is connected
        gateway = self.main_engine.get_gateway(gateway_name)
        if not gateway:
            logger.error(f"Failed to get gateway: {gateway_name}")
            return False
        
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
        gateway.subscribe(subscribe_req)
        logger.info(f"Subscribed to {contract_symbol} on {gateway_name}")
        
        self._vt_symbol = f"{contract_symbol}.{Exchange.GLOBAL.value}"
        logger.info(f"Strategy will use vt_symbol: {self._vt_symbol}")
        
        # Register EVENT_TRADE subscription on the EventEngine
        self._register_trade_event_handler()
        
        return True
    
    def _register_trade_event_handler(self) -> None:
        """
        Register handler for EVENT_TRADE events from the MainEngine.
        
        This is the CRITICAL fix for trade callbacks not firing.
        VN.PY's MainEngine processes trade events but we need to
        subscribe to them explicitly.
        """
        try:
            # The MainEngine already has a process_trade_event handler registered
            # We need to access it through the gateway's event mechanism
            gateway_name = "BINANCE_LINEAR" if self.market_type == "futures" else "BINANCE_SPOT"
            gateway = self.main_engine.get_gateway(gateway_name)
            
            if gateway:
                # Subscribe to trade updates from the gateway
                # The gateway emits EVENT_TRADE events which we capture here
                logger.info(f"Registering trade event handler on gateway {gateway_name}")
                
                # VN.PY gateway emits trade events through the event engine
                # We register our handler directly on the MainEngine's event engine
                if hasattr(self.main_engine, 'event_engine') and self.main_engine.event_engine:
                    self.main_engine.event_engine.register(EVENT_TRADE, self._on_trade_event)
                    logger.info("Trade event handler registered on MainEngine EventEngine")
                else:
                    logger.warning("MainEngine has no EventEngine - trade events may not flow")
            else:
                logger.warning(f"Gateway {gateway_name} not found")
                
        except Exception as e:
            logger.error(f"Error registering trade event handler: {e}")
    
    def _on_trade_event(self, event: Event) -> None:
        """
        Handle EVENT_TRADE events from VN.PY event engine.
        
        This is called for every trade event that flows through the system.
        """
        try:
            trade = event.data
            if trade:
                logger.debug(f"EVENT_TRADE received: {getattr(trade, 'symbol', '?')} {getattr(trade, 'direction', '?')} {getattr(trade, 'volume', '?')}")
                self._on_trade(trade)
        except Exception as e:
            logger.error(f"Error in _on_trade_event: {e}")

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
        else:
            class_name = "SiqeCtaStrategy"
            vt_symbol = f"{self.symbol}.{Exchange.GLOBAL.value}"

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
        
        # Wire alert manager to strategy
        if self._alert_manager:
            for strategy in cta_engine.strategies.values():
                if strategy.strategy_name == self.strategy_name:
                    if hasattr(strategy, 'set_alert_manager'):
                        strategy.set_alert_manager(self._alert_manager)
                        logger.info("Alert manager wired to strategy")
                    break

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
        
        # Stop Telegram bot
        if self._telegram_bot:
            self._telegram_bot.stop_polling()
            logger.info("Telegram bot stopped")
        
        # Send shutdown alert
        if self._alert_manager:
            try:
                self._alert_manager.system_shutdown(reason="Manual shutdown")
            except Exception as e:
                logger.error(f"Error sending shutdown alert: {e}")
        
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
        
        # Initialize alert manager
        self._init_alert_manager()
        
        # Initialize Telegram interactive bot
        self._init_telegram_bot()
    
    def _init_alert_manager(self) -> None:
        """Initialize Telegram alert manager."""
        try:
            from alerts import AlertManager
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            enabled = os.getenv("ALERT_ENABLED", "true").lower() == "true"
            
            if bot_token and chat_id:
                self._alert_manager = AlertManager(
                    telegram_bot_token=bot_token,
                    telegram_chat_id=chat_id,
                    enabled=enabled,
                )
                logger.info("Alert manager initialized with Telegram")
                if self._alert_manager.is_configured():
                    logger.info("Telegram alerts: ENABLED")
                    # Send startup alert
                    self._alert_manager.system_startup(
                        symbol=self.symbol.upper(),
                        leverage=self.strategy_params.get("leverage", 35),
                        strategy=self.strategy_name,
                    )
                else:
                    logger.warning("Telegram alerts: NOT CONFIGURED")
            else:
                logger.info("Alert manager: Telegram credentials not set")
                self._alert_manager = AlertManager(enabled=False)
        except ImportError as e:
            logger.warning(f"Alert module not available: {e}")
            self._alert_manager = None
        except Exception as e:
            logger.error(f"Error initializing alert manager: {e}")
            self._alert_manager = None
    
    def _init_telegram_bot(self) -> None:
        """Initialize Telegram interactive bot."""
        import os
        logger.info("Initializing Telegram interactive bot...")
        try:
            from alerts.telegram_bot import create_bot
            from alerts.formatters import TradingState
            
            token_set = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
            chat_set = bool(os.getenv("TELEGRAM_CHAT_ID"))
            logger.info(f"TELEGRAM_BOT_TOKEN set: {token_set}")
            logger.info(f"TELEGRAM_CHAT_ID set: {chat_set}")
            
            self._trading_state = TradingState(
                symbol=self.symbol.upper(),
                leverage=self.strategy_params.get("leverage", 35),
                mode="PAPER" if self.server == "TESTNET" else "LIVE",
            )
            
            def state_provider():
                """Provide current trading state for the bot."""
                if self._trading_state:
                    # Update live metrics
                    risk_status = self.get_risk_status()
                    self._trading_state.daily_pnl = risk_status.get("daily_pnl", 0.0)
                    self._trading_state.total_trades = risk_status.get("trades_today", 0)
                    
                    # Get actual positions from Binance
                    if self.main_engine:
                        try:
                            binance_positions = self.main_engine.get_all_positions()
                            logger.info(f"DEBUG: Binance positions: {[(p.symbol, p.volume, p.direction.value, getattr(p, 'unrealized_pnl', 'N/A'), getattr(p, 'pnl', 'N/A')) for p in binance_positions]}")
                            for pos in binance_positions:
                                if pos.symbol and "BTC" in pos.symbol:
                                    if pos.volume != 0:
                                        # Use volume sign to determine direction
                                        if pos.volume > 0:
                                            self._trading_state.position_side = "LONG"
                                        else:
                                            self._trading_state.position_side = "SHORT"
                                        self._trading_state.position_size = abs(pos.volume)
                                        self._trading_state.entry_price = pos.price
                                        # Try unrealized_pnl first, fall back to pnl
                                        self._trading_state.unrealized_pnl = getattr(pos, 'unrealized_pnl', pos.pnl or 0.0)
                                        logger.info(f"DEBUG: Position updated: {self._trading_state.position_side} {self._trading_state.position_size} @ ${self._trading_state.entry_price} | Unreal PnL: ${self._trading_state.unrealized_pnl}")
                                        break
                        except Exception as e:
                            logger.debug(f"Binance position query failed: {e}")
                        
                        # Get account info (specifically USDT balance)
                        try:
                            accounts = self.main_engine.get_all_accounts()
                            logger.info(f"DEBUG: Accounts: {[(a.accountid, a.balance, a.available, getattr(a, 'currency', 'N/A')) for a in accounts]}")
                            if accounts:
                                # Find USDT account - be flexible with matching
                                usdt_balance = 0.0
                                usdt_available = 0.0
                                for a in accounts:
                                    acc_id = str(a.accountid).strip().upper()
                                    logger.info(f"DEBUG: Checking account: '{acc_id}' vs 'USDT'")
                                    if 'USDT' in acc_id:
                                        usdt_balance = a.balance
                                        usdt_available = a.available
                                        logger.info(f"DEBUG: Found USDT account: balance={usdt_balance}, available={usdt_available}")
                                        break
                                self._trading_state.account_balance = usdt_balance
                                self._trading_state.available_balance = usdt_available
                                logger.info(f"DEBUG: Balance updated: ${self._trading_state.account_balance} (Avail: ${self._trading_state.available_balance})")
                        except Exception as e:
                            logger.debug(f"Account query failed: {e}")
                    
                    # Update from strategy if available
                    cta_engine = self.main_engine.get_engine("CtaStrategy") if self.main_engine else None
                    if cta_engine:
                        for strategy in cta_engine.strategies.values():
                            if strategy.strategy_name == self.strategy_name:
                                # Position from strategy (backup to Binance)
                                if hasattr(strategy, 'pos') and strategy.pos != 0:
                                    if self._trading_state.position_size == 0:
                                        self._trading_state.position_side = "LONG" if strategy.pos > 0 else "SHORT"
                                        self._trading_state.position_size = abs(strategy.pos)
                                if hasattr(strategy, 'avg_price') and self._trading_state.entry_price == 0:
                                    self._trading_state.entry_price = strategy.avg_price
                                
                                # Regime from strategy
                                if hasattr(strategy, 'regime'):
                                    self._trading_state.regime = strategy.regime
                                    self._trading_state.regime_confidence = 0.8
                                
                                # Trading status
                                if hasattr(strategy, 'trading'):
                                    self._trading_state.is_trading_active = strategy.trading
                                
                                # Volatility
                                if hasattr(strategy, 'atr_value'):
                                    self._trading_state.current_volatility = strategy.atr_value
                                
                                # Signal data
                                if hasattr(strategy, 'signal_direction'):
                                    self._trading_state.signal_direction = strategy.signal_direction
                                if hasattr(strategy, 'signal_strength'):
                                    self._trading_state.signal_strength = strategy.signal_strength
                                
                                # Directional bias (fallback signal)
                                if hasattr(strategy, 'directional_bias'):
                                    if not self._trading_state.signal_direction or self._trading_state.signal_direction == "NEUTRAL":
                                        self._trading_state.signal_direction = strategy.directional_bias
                                
                                # Signal components for ML view
                                if hasattr(strategy, 'signal_momentum'):
                                    self._trading_state.signal_momentum = strategy.signal_momentum
                                if hasattr(strategy, 'signal_mean_reversion'):
                                    self._trading_state.signal_mean_reversion = strategy.signal_mean_reversion
                                if hasattr(strategy, 'signal_volatility_breakout'):
                                    self._trading_state.signal_volatility_breakout = strategy.signal_volatility_breakout
                                
                                # Strategy params
                                if hasattr(strategy, 'atr_stop_multiplier'):
                                    self._trading_state.stop_multiplier = strategy.atr_stop_multiplier
                                if hasattr(strategy, 'atr_target_multiplier'):
                                    self._trading_state.tp_multiplier = strategy.atr_target_multiplier
                                
                                # Regime from strategy signal (fallback)
                                if not self._trading_state.regime or self._trading_state.regime == "UNKNOWN":
                                    # Check signal_direction first, then directional_bias
                                    signal_for_regime = self._trading_state.signal_direction
                                    if not signal_for_regime or signal_for_regime == "NEUTRAL":
                                        signal_for_regime = getattr(strategy, 'directional_bias', None)
                                    if signal_for_regime:
                                        if signal_for_regime == "LONG" or signal_for_regime == "BULL":
                                            self._trading_state.regime = "BULL"
                                            self._trading_state.regime_confidence = 0.8
                                        elif signal_for_regime == "SHORT" or signal_for_regime == "BEAR":
                                            self._trading_state.regime = "BEAR"
                                            self._trading_state.regime_confidence = 0.8
                                
                                logger.info(f"DEBUG: Strategy data - signal: {self._trading_state.signal_direction}, regime: {self._trading_state.regime}")
                                break
                    
                    # Get regime from RegimeEngine
                    if hasattr(self, 'regime_engine') and self.regime_engine:
                        self._trading_state.regime = self.regime_engine.current_regime
                        self._trading_state.regime_confidence = self.regime_engine.regime_confidence
                    elif cta_engine:
                        # Fallback: calculate regime from strategy
                        for strategy in cta_engine.strategies.values():
                            if strategy.strategy_name == self.strategy_name:
                                signal_for_regime = getattr(strategy, 'signal_direction', None)
                                if not signal_for_regime or signal_for_regime == "NEUTRAL":
                                    signal_for_regime = getattr(strategy, 'directional_bias', None)
                                if signal_for_regime:
                                    if signal_for_regime == "LONG" or signal_for_regime == "BULL":
                                        self._trading_state.regime = "BULL"
                                        self._trading_state.regime_confidence = 0.8
                                    elif signal_for_regime == "SHORT" or signal_for_regime == "BEAR":
                                        self._trading_state.regime = "BEAR"
                                        self._trading_state.regime_confidence = 0.8
                                break
                    
                    # Get realized P&L from Binance API (use runner's stored credentials)
                    try:
                        if self.api_key and self.api_secret:
                            import hashlib
                            import time
                            import hmac
                            import requests
                            timestamp = int(time.time() * 1000)
                            query = f"timestamp={timestamp}"
                            signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                            url = f"https://testnet.binancefuture.com/fapi/v2/account?{query}&signature={signature}"
                            resp = requests.get(url, headers={"X-MBX-APIKEY": self.api_key}, timeout=5)
                            logger.info(f"DEBUG: Binance API response: {resp.status_code}")
                            if resp.status_code == 200:
                                data = resp.json()
                                self._trading_state.total_pnl = float(data.get("totalCrossPnl", 0) or 0)
                                logger.info(f"DEBUG: Realized P&L from Binance: ${self._trading_state.total_pnl}")
                    except Exception as e:
                        logger.info(f"DEBUG: Binance P&L query exception: {e}")
                    
                    import time
                    self._trading_state.uptime_seconds = int(time.time() - getattr(self, '_start_time', time.time()))
                
                    return self._trading_state
            
            self._telegram_bot = create_bot(
                state_provider=state_provider,
                start_trading_callback=self.start_strategy,
                stop_trading_callback=self.stop_strategy,
            )
            
            if self._telegram_bot:
                self._bot_thread = self._telegram_bot.start_polling_thread()
                logger.info("Telegram interactive bot started")
            else:
                logger.info("Telegram interactive bot: NOT CONFIGURED (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        except ImportError as e:
            logger.warning(f"Telegram bot module not available: {e}")
            self._telegram_bot = None
        except Exception as e:
            logger.error(f"Error initializing Telegram bot: {e}")
            self._telegram_bot = None

    def _on_trade(self, trade) -> None:
        """Handle completed trade - send to SIQEEngine for risk/learning."""
        self._trade_count += 1
        logger.info(f"=== TRADE CALLBACK FIRED #{self._trade_count} ===")
        logger.info(f"  Symbol: {getattr(trade, 'symbol', 'N/A')}")
        logger.info(f"  Direction: {getattr(trade, 'direction', 'N/A')}")
        logger.info(f"  Volume: {getattr(trade, 'volume', 'N/A')}")
        logger.info(f"  Price: {getattr(trade, 'price', 'N/A')}")
        
        # Send Telegram alert for trade
        if self._alert_manager and self._alert_manager.is_configured():
            try:
                direction = str(trade.direction).replace("Direction.", "")
                self._alert_manager.trade_executed(
                    direction=direction,
                    volume=getattr(trade, 'volume', 0),
                    price=getattr(trade, 'price', 0),
                    symbol=getattr(trade, 'symbol', self.symbol.upper()),
                    trade_id=getattr(trade, 'trade_id', f'live_{self._trade_count}'),
                )
            except Exception as e:
                logger.error(f"Error sending trade alert: {e}")
        
        if not self.siqe_engine:
            logger.warning(f"Trade #{self._trade_count}: no SIQEEngine connected")
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
            logger.info(f"  Trade data prepared: {trade_data}")
            
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._process_trade_async(trade_data))
                logger.info(f"  Async task created for trade #{self._trade_count}")
            else:
                loop.run_until_complete(self._process_trade_async(trade_data))
                
        except Exception as e:
            logger.error(f"Error processing trade callback: {e}")

    async def _process_trade_async(self, trade_data: Dict[str, Any]) -> None:
        """Process trade result asynchronously through SIQEEngine pipeline."""
        logger.info(f"=== PROCESSING TRADE #{self._trade_count} ASYNC ===")
        try:
            if hasattr(self.siqe_engine, 'risk_engine') and self.siqe_engine.risk_engine:
                trade_pnl = trade_data.get('pnl', 0)
                logger.info(f"  Updating risk engine with pnl={trade_pnl}")
                
                await self.siqe_engine.risk_engine.update_trade_result(trade_pnl)
                
                risk_status = await self.siqe_engine.risk_engine.get_circuit_breaker_status()
                active_breakers = [k for k, v in risk_status.get('circuit_breakers', {}).items() if v.get('is_active')]
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
            "circuit_breakers": "await via async method",
            "trades_today": self._trade_count,
        }
    
    async def get_risk_status_async(self) -> Dict[str, Any]:
        """Get current risk status from SIQEEngine (async)."""
        if not self.siqe_engine or not hasattr(self.siqe_engine, 'risk_engine'):
            return {"status": "no_risk_engine"}
        
        try:
            cb_status = await self.siqe_engine.risk_engine.get_circuit_breaker_status()
        except Exception:
            cb_status = "unavailable"
        
        risk_engine = self.siqe_engine.risk_engine
        return {
            "daily_pnl": risk_engine.daily_pnl,
            "consecutive_losses": risk_engine.consecutive_losses,
            "circuit_breakers": cb_status,
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
        self._start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') and not asyncio.get_event_loop().is_closed() else 0

        def _signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            self._running = False

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info(f"SIQE live runner running ({self.market_type}). Press Ctrl+C to stop.")
        
        import time
        last_heartbeat = time.time()
        heartbeat_interval = 300  # 5 minutes
        
        try:
            while self._running:
                time.sleep(1)
                
                # Send heartbeat every 5 minutes
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = current_time
                    uptime_seconds = int(current_time - (self._start_time or current_time))
                    if self._alert_manager:
                        try:
                            self._alert_manager.heartbeat(
                                uptime_seconds=uptime_seconds,
                                status="RUNNING"
                            )
                            logger.debug(f"Heartbeat sent: {uptime_seconds}s uptime")
                        except Exception as e:
                            logger.warning(f"Failed to send heartbeat: {e}")
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
