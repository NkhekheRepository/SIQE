"""
Feedback Loop Module
Processes trade results and feeds information back to learning and memory systems.
Deterministic: uses EventClock, PnL decomposition into signal_alpha + execution_alpha + noise.
"""
import asyncio
import logging
from typing import Dict, Any, Optional

import numpy as np

from core.clock import EventClock
from models.trade import ExecutionResult, Trade, PnLDecomposition

logger = logging.getLogger(__name__)


class FeedbackLoop:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.feedback_queue = asyncio.Queue(maxsize=settings.get("max_queue_size", 1000))
        self.processing_task = None
        self.stats = {
            "trades_processed": 0,
            "successful_feedbacks": 0,
            "failed_feedbacks": 0,
            "last_processed": None,
        }
        self.learning_engine = None
        self.state_manager = None
        self.risk_engine = None
        self.meta_harness = None
        self.ev_engine = None
        self.regime_engine = None
        self.strategy_engine = None
        self.alert_manager = None
        self.pnl_deviation_threshold = settings.get("pnl_deviation_threshold", 3.0)
        self._recent_pnls = []
        self._max_pnl_history = 50

    def set_modules(self, learning_engine=None, state_manager=None, risk_engine=None,
                    meta_harness=None, ev_engine=None, regime_engine=None, strategy_engine=None):
        self.learning_engine = learning_engine
        self.state_manager = state_manager
        self.risk_engine = risk_engine
        self.meta_harness = meta_harness
        self.ev_engine = ev_engine
        self.regime_engine = regime_engine
        self.strategy_engine = strategy_engine

    def set_alert_manager(self, alert_manager):
        self.alert_manager = alert_manager
        logger.info("Alert manager connected to Feedback Loop")

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Feedback Loop...")
            self.is_initialized = True
            self.processing_task = asyncio.create_task(self._process_feedback_queue())
            logger.info("Feedback Loop initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Feedback Loop: {e}")
            return False

    async def process_trade_result(self, execution_result: ExecutionResult, trade: Trade):
        if not self.is_initialized:
            logger.warning("Feedback loop not initialized, dropping trade result")
            return

        try:
            await self.feedback_queue.put((execution_result, trade))
            logger.debug(f"Trade result queued for feedback: {execution_result.execution_id}")
        except asyncio.QueueFull:
            logger.warning("Feedback queue full, dropping trade result")
        except Exception as e:
            logger.error(f"Error queuing trade result for feedback: {e}")

    async def _process_feedback_queue(self):
        logger.info("Feedback queue processor started")

        while self.is_initialized:
            try:
                try:
                    execution_result, trade = await asyncio.wait_for(
                        self.feedback_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._process_feedback_item(execution_result, trade)
                self.feedback_queue.task_done()
                self.stats["trades_processed"] += 1
                self.stats["last_processed"] = self.clock.now

            except Exception as e:
                logger.error(f"Error in feedback queue processing: {e}")
                self.stats["failed_feedbacks"] += 1
                await asyncio.sleep(1)

        logger.info("Feedback queue processor stopped")

    async def _process_feedback_item(self, execution_result: ExecutionResult, trade: Trade):
        try:
            if execution_result.success:
                pnl_decomp = self._decompose_pnl(execution_result, trade)
                await self._process_successful_trade(execution_result, trade, pnl_decomp)
                self.stats["successful_feedbacks"] += 1
            else:
                await self._process_failed_trade(execution_result)
                self.stats["failed_feedbacks"] += 1

            logger.debug(f"Processed feedback item: {execution_result.execution_id}")
        except Exception as e:
            logger.error(f"Error processing feedback item: {e}")
            self.stats["failed_feedbacks"] += 1
            raise

    def _decompose_pnl(self, execution_result: ExecutionResult, trade: Trade) -> PnLDecomposition:
        notional = execution_result.filled_quantity * execution_result.filled_price
        signal_alpha = trade.ev * notional
        expected_price = trade.price
        execution_alpha = (expected_price - execution_result.filled_price) * execution_result.filled_quantity
        total_pnl = signal_alpha + execution_alpha
        noise = total_pnl - signal_alpha - execution_alpha

        return PnLDecomposition(
            execution_id=execution_result.execution_id,
            signal_alpha=signal_alpha,
            execution_alpha=execution_alpha,
            noise=noise,
            total_pnl=total_pnl,
        )

    async def _process_successful_trade(self, execution_result: ExecutionResult,
                                        trade: Trade, pnl_decomp: PnLDecomposition):
        try:
            feedback_data = {
                "execution_id": execution_result.execution_id,
                "symbol": execution_result.symbol,
                "signal_type": execution_result.signal_type.value,
                "strategy": execution_result.strategy,
                "ev_score": trade.ev,
                "pnl": pnl_decomp.total_pnl,
                "signal_alpha": pnl_decomp.signal_alpha,
                "execution_alpha": pnl_decomp.execution_alpha,
                "noise": pnl_decomp.noise,
                "timestamp": self.clock.now,
                "filled_price": execution_result.filled_price,
                "filled_quantity": execution_result.filled_quantity,
                "trade_type": "successful",
            }

            # Track recent PnLs for anomaly detection
            self._recent_pnls.append(pnl_decomp.total_pnl)
            if len(self._recent_pnls) > self._max_pnl_history:
                self._recent_pnls = self._recent_pnls[-self._max_pnl_history:]

            # Check for anomalous PnL
            if len(self._recent_pnls) >= 10 and self.alert_manager:
                expected_pnl = np.mean(self._recent_pnls[:-1]) if len(self._recent_pnls) > 1 else 0
                if expected_pnl != 0:
                    std_pnl = np.std(self._recent_pnls[:-1]) if len(self._recent_pnls) > 1 else 1
                    deviation_sigma = abs(pnl_decomp.total_pnl - expected_pnl) / std_pnl if std_pnl > 0 else 0
                    
                    if deviation_sigma > self.pnl_deviation_threshold:
                        self.alert_manager.anomalous_pnl(
                            expected_pnl=expected_pnl,
                            actual_pnl=pnl_decomp.total_pnl,
                            deviation_sigma=deviation_sigma
                        )

            await self._feed_to_learning_system(feedback_data)
            await self._feed_to_memory_system(feedback_data)
            await self._feed_to_risk_system(feedback_data)
            await self._feed_to_meta_harness(feedback_data)
            await self._feed_to_ev_engine(feedback_data)
            await self._feed_to_regime_engine(feedback_data)

            logger.debug(f"Processed successful trade feedback: {execution_result.symbol} "
                         f"PnL={pnl_decomp.total_pnl:.2f} (signal={pnl_decomp.signal_alpha:.2f}, "
                         f"exec={pnl_decomp.execution_alpha:.2f}, noise={pnl_decomp.noise:.2f})")
        except Exception as e:
            logger.error(f"Error processing successful trade feedback: {e}")
            raise

    async def _process_failed_trade(self, execution_result: ExecutionResult):
        try:
            feedback_data = {
                "execution_id": execution_result.execution_id,
                "error": execution_result.error,
                "timestamp": self.clock.now,
                "trade_type": "failed_execution",
                "symbol": execution_result.symbol,
                "signal_type": execution_result.signal_type.value,
            }

            await self._feed_to_memory_system(feedback_data)
            await self._feed_to_meta_harness(feedback_data)

            logger.debug(f"Processed failed trade feedback: {execution_result.execution_id} - {execution_result.error}")
        except Exception as e:
            logger.error(f"Error processing failed trade feedback: {e}")
            raise

    async def _feed_to_learning_system(self, feedback_data: Dict[str, Any]):
        try:
            if self.learning_engine:
                strategy = feedback_data.get("strategy", "unknown")
                perf = {
                    "total_trades": 1,
                    "win_rate": 1.0 if feedback_data.get("pnl", 0) > 0 else 0.0,
                    "avg_pnl": feedback_data.get("pnl", 0),
                    "avg_ev": feedback_data.get("ev_score", 0),
                    "sample_size": 1,
                    "pnl": feedback_data.get("pnl", 0),
                }
                await self.learning_engine.update_parameters(strategy, perf)
                logger.debug(f"Feeding to learning system: {feedback_data.get('execution_id')} strategy={strategy}")
        except Exception as e:
            logger.error(f"Error feeding to learning system: {e}")

    async def _feed_to_memory_system(self, feedback_data: Dict[str, Any]):
        try:
            if self.state_manager:
                trade_record = {
                    "execution_id": feedback_data.get("execution_id"),
                    "symbol": feedback_data.get("symbol"),
                    "pnl": feedback_data.get("pnl", 0),
                    "strategy": feedback_data.get("strategy", "unknown"),
                    "timestamp": feedback_data.get("timestamp"),
                    "trade_type": feedback_data.get("trade_type", "unknown"),
                }
                await self.state_manager.save_trade(trade_record)
                logger.debug(f"Feeding to memory system: {feedback_data.get('execution_id')}")
        except Exception as e:
            logger.error(f"Error feeding to memory system: {e}")

    async def _feed_to_risk_system(self, feedback_data: Dict[str, Any]):
        try:
            if self.risk_engine:
                pnl = feedback_data.get("pnl", 0)
                await self.risk_engine.update_trade_result(pnl)
                logger.debug(f"Feeding to risk system: PnL={pnl:.2f}")
        except Exception as e:
            logger.error(f"Error feeding to risk system: {e}")

    async def _feed_to_meta_harness(self, feedback_data: Dict[str, Any]):
        try:
            if self.meta_harness:
                await self.meta_harness.update_performance_metrics(feedback_data)
                logger.debug(f"Feeding to meta harness: {feedback_data.get('execution_id')}")
        except Exception as e:
            logger.error(f"Error feeding to meta harness: {e}")

    async def _feed_to_ev_engine(self, feedback_data: Dict[str, Any]):
        try:
            if self.ev_engine:
                symbol = feedback_data.get("symbol", "")
                strategy = feedback_data.get("strategy", "unknown")
                signal_type = feedback_data.get("signal_type", "")
                pnl = feedback_data.get("pnl", 0)
                await self.ev_engine.update_performance(symbol, strategy, signal_type, pnl)
                logger.debug(f"Feeding to EV engine: {feedback_data.get('execution_id')}")
        except Exception as e:
            logger.error(f"Error feeding to EV engine: {e}")

    async def _feed_to_regime_engine(self, feedback_data: Dict[str, Any]):
        try:
            if self.regime_engine:
                pnl = feedback_data.get("pnl", 0)
                await self.regime_engine.update_trade_feedback(pnl)
                logger.debug(f"Feeding to regime engine: {feedback_data.get('execution_id')} pnl={pnl:.2f}")
        except Exception as e:
            logger.error(f"Error feeding to regime engine: {e}")

    async def get_feedback_stats(self) -> Dict[str, Any]:
        queue_size = self.feedback_queue.qsize() if hasattr(self.feedback_queue, 'qsize') else 0
        return {
            **self.stats,
            "queue_size": queue_size,
            "is_initialized": self.is_initialized,
            "is_processing": self.processing_task is not None and not self.processing_task.done(),
        }

    async def shutdown(self):
        logger.info("Shutting down Feedback Loop...")
        self.is_initialized = False

        if self.processing_task and not self.processing_task.done():
            logger.info("Waiting for feedback queue to drain...")
            await self.feedback_queue.join()
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        logger.info("Feedback Loop shutdown complete")
