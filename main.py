#!/usr/bin/env python3
"""
SIQE V3 - Self-Improving Quant Engine
Deterministic, event-driven, risk-constrained trading system.
Sole entry point: async def on_market_event(self, event: dict)
"""
import asyncio
import logging
import os
import random
import signal
import sys
import tracemalloc
from typing import Dict, Any, Optional

import numpy as np

from core.data_engine import DataEngine
from strategy_engine.strategy_base import StrategyEngine
from ev_engine.ev_calculator import EVEngine
from decision_engine.decision_maker import DecisionEngine
from risk_engine.risk_manager import RiskEngine
from meta_harness.meta_governor import MetaHarness
from execution_adapter.vnpy_bridge import ExecutionAdapter
from feedback.feedback_loop import FeedbackLoop
from memory.state_manager import StateManager
from regime.regime_engine import RegimeEngine
from learning.learning_engine import LearningEngine
from config.settings import Settings
from alerts.alert_manager import AlertManager, get_alert_manager
from infra.logger import setup_logging, InterceptHandler
from core.clock import EventClock, IDGenerator
from core.retry import with_retry
from models.trade import (
    MarketEvent, Signal, EVResult, Decision, Trade,
    ExecutionResult, PnLDecomposition, RegimeResult,
    ApprovalResult, SignalType, RegimeType,
)

logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)
logger = logging.getLogger(__name__)


class SIQEEngine:
    """Main SIQE V3 Engine — deterministic, event-driven, risk-constrained."""

    def __init__(self):
        random.seed(0)
        np.random.seed(0)
        tracemalloc.start()

        self.settings = Settings()
        self.running = False
        self.shutdown_event = asyncio.Event()

        self.clock = EventClock()
        self.id_gen = lambda prefix: IDGenerator(prefix, self.clock)

        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=self.settings.max_queue_size)
        self.semaphore = asyncio.Semaphore(self.settings.max_concurrent_events)

        self.data_engine = DataEngine(self.settings, self.clock)
        self.strategy_engine = StrategyEngine(self.settings, self.clock)
        self.ev_engine = EVEngine(self.settings, self.clock)
        self.decision_engine = DecisionEngine(self.settings, self.clock)
        self.risk_engine = RiskEngine(self.settings, self.clock)
        self.meta_harness = MetaHarness(self.settings, self.clock)
        self.execution_adapter = ExecutionAdapter(self.settings, self.clock)
        self.feedback_loop = FeedbackLoop(self.settings, self.clock)
        self.state_manager = StateManager(self.settings)
        self.regime_engine = RegimeEngine(self.settings, self.clock)
        self.learning_engine = LearningEngine(self.settings, self.clock)
        
        # Alert manager
        self.alert_manager: Optional[AlertManager] = None

        self.start_seq = 0
        self.total_trades = 0
        self.total_events_processed = 0
        self.total_events_rejected = 0
        self.system_state = "INITIALIZING"
        self._learning_interval = 50

        self._stage_latencies: Dict[str, list] = {
            "regime": [], "strategy": [], "ev": [],
            "decision": [], "meta": [], "risk": [], "execution": [],
        }
        self._max_latency_samples = 1000

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing SIQE V3 Engine...")
            await self.state_manager.initialize()
            await self.execution_adapter.initialize()
            self.data_engine.set_execution_adapter(self.execution_adapter)
            await self.data_engine.initialize()
            await self.strategy_engine.initialize()
            await self.ev_engine.initialize()
            await self.decision_engine.initialize()
            await self.risk_engine.initialize()
            await self.meta_harness.initialize()
            await self.feedback_loop.initialize()
            await self.regime_engine.initialize()
            await self.learning_engine.initialize()
            
            # Initialize and wire alert manager
            self.alert_manager = get_alert_manager()
            self.risk_engine.set_alert_manager(self.alert_manager)
            self.regime_engine.set_alert_manager(self.alert_manager)
            self.learning_engine.set_alert_manager(self.alert_manager)
            self.execution_adapter.set_alert_manager(self.alert_manager)
            
            await self.state_manager.load_state()
            await self.state_manager.restore_state_to_components(
                risk_engine=self.risk_engine,
                strategy_engine=self.strategy_engine,
                meta_harness=self.meta_harness,
            )

            self.feedback_loop.set_modules(
                learning_engine=self.learning_engine,
                state_manager=self.state_manager,
                risk_engine=self.risk_engine,
                meta_harness=self.meta_harness,
                ev_engine=self.ev_engine,
                regime_engine=self.regime_engine,
                strategy_engine=self.strategy_engine,
            )
            self.feedback_loop.set_alert_manager(self.alert_manager)

            logger.info("SIQE V3 Engine initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SIQE Engine: {e}")
            return False

    async def on_market_event(self, event: dict) -> Optional[Trade]:
        """Sole entry point for all trading. No other component may trigger trades."""
        try:
            market_event = MarketEvent.validate(event)
        except ValueError as e:
            logger.warning(f"Invalid market event: {e}")
            self.total_events_rejected += 1
            return None

        try:
            self.event_queue.put_nowait(market_event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — backpressure, rejecting event")
            self.total_events_rejected += 1
            if self.alert_manager:
                max_size = self.event_queue.maxsize
                current_size = max_size
                self.alert_manager.queue_full(
                    queue_size=current_size,
                    max_size=max_size
                )
            return None

        return None

    async def validate_signal(self, signal_data: dict) -> ApprovalResult:
        """
        Standalone signal validation for hybrid VN.PY mode.
        Validates signal against RiskEngine without full pipeline.
        """
        try:
            signal_type_str = signal_data.get('signal_type', 'momentum')
            try:
                signal_type = SignalType(signal_type_str)
            except ValueError:
                signal_type = SignalType.LONG
            
            decision = Decision(
                decision_id=self.id_gen("decision").next(),
                signal_id=self.id_gen("signal").next(),
                symbol=signal_data.get('symbol', 'BTCUSDT'),
                signal_type=signal_type,
                strength=signal_data.get('strength', 0.5),
                price=signal_data.get('price', 0.0),
                strategy="SiqeFuturesStrategy",
                ev_score=signal_data.get('ev', 0.0),
                confidence=signal_data.get('confidence', 0.5),
                actionable=True,
                event_seq=self.clock.now,
                reasoning="hybrid_validation",
            )
            return await self.risk_engine.validate_trade(decision)
        except Exception as e:
            logger.error(f"Signal validation error: {e}")
            return ApprovalResult(False, str(e), self.clock.now)

    async def process_trade_result(self, trade_data: dict) -> dict:
        """
        Process completed trade from VN.PY strategy.
        Updates risk state and triggers learning if needed.
        """
        try:
            trade_pnl = trade_data.get('pnl', 0)
            await self.risk_engine.update_trade_result(trade_pnl)
            
            circuit_status = await self.risk_engine.get_circuit_breaker_status()
            risk_status = {
                'daily_pnl': self.risk_engine.daily_pnl,
                'consecutive_losses': self.risk_engine.consecutive_losses,
                'circuit_breakers': circuit_status,
            }
            
            self.total_trades += 1
            
            if self.total_trades > 0 and self.total_trades % self._learning_interval == 0:
                perf = await self.state_manager.get_trade_statistics()
                perf['sample_size'] = self.total_trades
                await self.learning_engine.update_parameters("SiqeFuturesStrategy", perf)
                logger.info(f"Learning update at trade #{self.total_trades}")
            
            return risk_status
        except Exception as e:
            logger.error(f"Trade result processing error: {e}")
            return {'error': str(e)}

    def get_risk_status(self) -> dict:
        """Get current risk status (sync, for API endpoint)."""
        try:
            return {
                'daily_pnl': self.risk_engine.daily_pnl,
                'consecutive_losses': self.risk_engine.consecutive_losses,
                'max_drawdown': self.risk_engine.max_drawdown,
                'trades_total': self.total_trades,
                'events_rejected': self.total_events_rejected,
                'system_state': self.system_state,
            }
        except Exception as e:
            logger.error(f"Risk status error: {e}")
            return {'error': str(e)}

    async def get_learning_status(self) -> dict:
        """Get current learning engine status."""
        try:
            history = await self.learning_engine.get_learning_history(limit=10)
            return {
                'recent_updates': history,
                'trades_total': self.total_trades,
            }
        except Exception as e:
            logger.error(f"Learning status error: {e}")
            return {'error': str(e)}

    async def _process_events(self):
        while self.running and not self.shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            async with self.semaphore:
                await self._run_pipeline(event)

    async def _run_pipeline(self, event: MarketEvent):
        strict_timeout = self.settings.stage_timeout
        max_retries = self.settings.max_retries
        base_delay = self.settings.retry_base_delay

        try:
            t0 = self.clock.now

            regime = await asyncio.wait_for(
                with_retry(
                    lambda: self.regime_engine.detect_regime(event),
                    max_retries=max_retries, base_delay=base_delay, name="regime_detect"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("regime", self.clock.now - t0)

            signals = await asyncio.wait_for(
                with_retry(
                    lambda: self.strategy_engine.generate_signals(event, regime_result=regime),
                    max_retries=max_retries, base_delay=base_delay, name="generate_signals"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("strategy", self.clock.now - t0)
            if not signals:
                return

            ev_results = await asyncio.wait_for(
                with_retry(
                    lambda: self.ev_engine.calculate_ev(signals, event, regime_result=regime),
                    max_retries=max_retries, base_delay=base_delay, name="calculate_ev"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("ev", self.clock.now - t0)
            if not ev_results:
                return

            decision = await asyncio.wait_for(
                with_retry(
                    lambda: self.decision_engine.make_decision(ev_results, regime_result=regime),
                    max_retries=max_retries, base_delay=base_delay, name="make_decision"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("decision", self.clock.now - t0)
            if not decision or not decision.actionable:
                return

            meta = await asyncio.wait_for(
                with_retry(
                    lambda: self.meta_harness.validate_trade(decision),
                    max_retries=max_retries, base_delay=base_delay, name="meta_validate"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("meta", self.clock.now - t0)
            if not meta.approved:
                logger.debug(f"Trade rejected by Meta Harness: {meta.reason}")
                return

            risk = await asyncio.wait_for(
                with_retry(
                    lambda: self.risk_engine.validate_trade(decision, risk_scaling=regime.risk_scaling),
                    max_retries=max_retries, base_delay=base_delay, name="risk_validate"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("risk", self.clock.now - t0)
            if not risk.approved:
                logger.debug(f"Trade rejected by Risk Engine: {risk.reason}")
                return

            exec_result = await asyncio.wait_for(
                with_retry(
                    lambda: self.execution_adapter.execute_trade(decision),
                    max_retries=max_retries, base_delay=base_delay, name="execute_trade"
                ),
                timeout=strict_timeout,
            )
            self._record_latency("execution", self.clock.now - t0)

            trade = Trade.from_decision(
                decision,
                trade_id=self.id_gen("trade").next(),
                size=exec_result.filled_quantity,
                event_clock=self.clock.now,
            )

            await self.feedback_loop.process_trade_result(exec_result, trade)
            self.total_trades += 1
            await self.state_manager.save_trade(exec_result)

            if self.total_trades > 0 and self.total_trades % self._learning_interval == 0:
                perf = await self.state_manager.get_trade_statistics()
                perf["sample_size"] = perf.get("total_trades", 0)
                strategy = decision.strategy
                update_result = await self.learning_engine.update_parameters(strategy, perf)
                if update_result.get("success"):
                    await self.strategy_engine.update_strategy_params(
                        strategy, update_result.get("new_parameters", {})
                    )
                    logger.info(f"Learning update for {strategy} (trade #{self.total_trades})")

            self.total_events_processed += 1

        except asyncio.TimeoutError as e:
            logger.error(f"Pipeline stage timeout: {e}")
            self.total_events_rejected += 1
            if self.alert_manager:
                self.alert_manager.pipeline_error(
                    stage="pipeline_timeout",
                    error=str(e)
                )
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            self.total_events_rejected += 1
            if self.alert_manager:
                self.alert_manager.pipeline_error(
                    stage="pipeline_execution",
                    error=str(e)
                )

    def _record_latency(self, stage: str, ticks: int):
        samples = self._stage_latencies[stage]
        samples.append(ticks)
        if len(samples) > self._max_latency_samples:
            self._stage_latencies[stage] = samples[-self._max_latency_samples:]

    async def start(self):
        if not await self.initialize():
            logger.error("Failed to initialize engine")
            return False

        self.running = True
        self.start_seq = self.clock.now
        self.system_state = "NORMAL"
        logger.info("SIQE V3 Engine started")

        try:
            consumer = asyncio.create_task(self._process_events())
            producer = asyncio.create_task(self._produce_events())
            await asyncio.gather(consumer, producer)
        except Exception as e:
            logger.error(f"Fatal error in engine: {e}")
            self.system_state = "CRITICAL"
        finally:
            await self.shutdown()

    async def _produce_events(self):
        while self.running and not self.shutdown_event.is_set():
            try:
                market_data = await self.data_engine.get_latest_data()
                if market_data:
                    for symbol, event in market_data.items():
                        event_dict = {
                            "event_id": event.event_id,
                            "symbol": event.symbol,
                            "bid": event.bid,
                            "ask": event.ask,
                            "volume": event.volume,
                            "volatility": event.volatility,
                            "event_seq": event.event_seq,
                        }
                        await self.on_market_event(event_dict)
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error producing events: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def shutdown(self):
        logger.info("Shutting down SIQE V3 Engine...")
        self.running = False
        self.shutdown_event.set()

        await self.meta_harness.halt_system("System shutdown")
        await self.state_manager.save_state(
            risk_engine=self.risk_engine,
            meta_harness=self.meta_harness,
        )

        await self.data_engine.shutdown()
        await self.execution_adapter.shutdown()
        await self.feedback_loop.shutdown()
        await self.regime_engine.shutdown()
        await self.learning_engine.shutdown()
        await self.state_manager.shutdown()

        current, peak = tracemalloc.get_traced_memory()
        logger.info(f"Memory at shutdown: current={current / 1024 / 1024:.1f}MB, peak={peak / 1024 / 1024:.1f}MB")
        tracemalloc.stop()

        logger.info("SIQE V3 Engine shutdown complete")

    def get_status(self) -> Dict[str, Any]:
        uptime = self.clock.now - self.start_seq if self.start_seq else 0
        return {
            "system_state": self.system_state,
            "running": self.running,
            "uptime_ticks": uptime,
            "total_trades": self.total_trades,
            "total_events_processed": self.total_events_processed,
            "total_events_rejected": self.total_events_rejected,
            "start_seq": self.start_seq,
        }

    def get_metrics(self) -> Dict[str, Any]:
        current, peak = tracemalloc.get_traced_memory()
        avg_latencies = {}
        for stage, samples in self._stage_latencies.items():
            avg_latencies[stage] = sum(samples) / len(samples) if samples else 0.0

        return {
            "queue_depth": self.event_queue.qsize(),
            "queue_capacity": self.settings.max_queue_size,
            "active_concurrent": self.settings.max_concurrent_events - self.semaphore._value,
            "max_concurrent": self.settings.max_concurrent_events,
            "stage_latencies_avg_ticks": avg_latencies,
            "throughput_events": self.total_events_processed,
            "rejected_events": self.total_events_rejected,
            "memory_mb": current / 1024 / 1024,
            "peak_memory_mb": peak / 1024 / 1024,
        }


def setup_signal_handlers(engine: SIQEEngine):
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(engine.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main():
    setup_logging()
    logger.info("Starting SIQE V3 - Self-Improving Quant Engine")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")

    engine = SIQEEngine()

    try:
        from api.main import set_engine_instance, app
        set_engine_instance(engine)
        logger.info("API engine instance wired")
    except Exception as e:
        logger.warning(f"Could not wire API engine instance: {e}")
        app = None

    setup_signal_handlers(engine)

    if app:
        from uvicorn import Config, Server
        config = Config(app=app, host="0.0.0.0", port=8000, log_level="info", log_config=None)
        server = Server(config)
        asyncio.create_task(server.serve())
        logger.info("API server started on port 8000")

    await engine.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
