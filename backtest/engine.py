"""
Backtest Engine
Deterministic historical replay orchestrator.
Composes existing SIQE components, runs synchronously event-by-event.
"""
import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from core.clock import EventClock
from config.settings import Settings
from strategy_engine.strategy_base import StrategyEngine
from strategy_engine.config import (
    IndicatorConfig, RegimeDetector, AdaptiveIndicatorBounds,
    MarketRegime, ParameterSweepResult,
)
from ev_engine.ev_calculator import EVEngine
from decision_engine.decision_maker import DecisionEngine
from risk_engine.risk_manager import RiskEngine
from meta_harness.meta_governor import MetaHarness
from execution_adapter.vnpy_bridge import ExecutionAdapter
from feedback.feedback_loop import FeedbackLoop
from regime.regime_engine import RegimeEngine
from learning.learning_engine import LearningEngine
from models.trade import (
    MarketEvent, Signal, EVResult, Decision, Trade,
    ExecutionResult, SignalType, OrderStatus,
)
from backtest.config import BacktestSettings, LearningMode, SlippageModelType
from backtest.data_provider import HistoricalDataProvider
from backtest.slippage_model import create_slippage_model, SlippageModel
from backtest.performance import PerformanceAnalyzer, TradeRecord, PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Complete result from a backtest run."""
    metrics: PerformanceMetrics
    settings: Dict[str, Any]
    config: Dict[str, Any]
    trades: List[Dict[str, Any]]
    run_time_seconds: float
    seed: int
    data_source: str
    bars_analyzed: int
    events_processed: int
    events_rejected: int
    parameter_updates: int = 0
    kill_triggered: bool = False
    kill_reason: str = ""


class BacktestEngine:
    """Deterministic backtesting engine.

    Replays historical data through the SIQE pipeline synchronously,
    event-by-event, with full reproducibility guarantees.
    """

    def __init__(self, bt_settings: BacktestSettings, siqe_settings: Optional[Settings] = None):
        self.bt_settings = bt_settings
        self.siqe_settings = siqe_settings or Settings()

        self.clock = EventClock()
        self._slippage_model = self._create_slippage_model()
        self._equity = bt_settings.initial_equity
        self._trade_log: List[Dict[str, Any]] = []
        self._parameter_updates = 0
        self._kill_triggered = False
        self._kill_reason = ""

    def _create_slippage_model(self) -> SlippageModel:
        model_map = {
            SlippageModelType.FIXED_BPS: lambda: create_slippage_model(
                "fixed_bps", bps=self.bt_settings.slippage_bps,
            ),
            SlippageModelType.LINEAR: lambda: create_slippage_model(
                "linear", base_bps=self.bt_settings.slippage_bps / 2,
            ),
            SlippageModelType.VOLUME_IMPACT: lambda: create_slippage_model(
                "volume_impact", impact_factor=self.bt_settings.volume_impact_factor,
            ),
        }
        return model_map[self.bt_settings.slippage_model]()

    def run(self) -> BacktestResult:
        """Execute the full backtest run.

        Returns BacktestResult with metrics, trade log, and metadata.
        """
        start_time = time.time()

        random.seed(self.bt_settings.rng_seed)
        np.random.seed(self.bt_settings.rng_seed)

        logger.info(
            f"Starting backtest: {self.bt_settings.data_provider.value} | "
            f"{self.bt_settings.symbols} | "
            f"{self.bt_settings.start_date} -> {self.bt_settings.end_date} | "
            f"timeframe={self.bt_settings.timeframe} | "
            f"seed={self.bt_settings.rng_seed}"
        )

        data_provider = HistoricalDataProvider(self.bt_settings)
        event_iterator = data_provider.get_event_iterator(self.clock)

        components = self._init_components()
        analyzer = PerformanceAnalyzer(
            initial_equity=self.bt_settings.initial_equity,
            bars_per_year=self._bars_per_year(self.bt_settings.timeframe),
        )

        bars_count = 0
        for event in event_iterator:
            bars_count += 1
            analyzer.record_equity(self._equity)

            if self._kill_triggered:
                analyzer.record_equity(self._equity)
                continue

            self._process_event(event, components, analyzer)

            if self.bt_settings.learning_mode == LearningMode.ADAPTIVE:
                total_trades = len(self._trade_log)
                if total_trades > 0 and total_trades % self.bt_settings.learning_interval == 0:
                    self._run_learning(components, total_trades)

        analyzer.record_equity(self._equity)
        analyzer.set_event_counts(
            processed=bars_count,
            rejected=0,
        )
        analyzer.set_bars_analyzed(bars_count)

        metrics = analyzer.compute()
        run_time = time.time() - start_time

        result = BacktestResult(
            metrics=metrics,
            settings=self._settings_dict(),
            config=self._config_dict(),
            trades=self._trade_log,
            run_time_seconds=run_time,
            seed=self.bt_settings.rng_seed,
            data_source=f"{self.bt_settings.data_provider.value}:{','.join(self.bt_settings.symbols)}",
            bars_analyzed=bars_count,
            events_processed=bars_count,
            events_rejected=0,
            parameter_updates=self._parameter_updates,
            kill_triggered=self._kill_triggered,
            kill_reason=self._kill_reason,
        )

        logger.info(
            f"Backtest complete: {bars_count} bars, {metrics.total_trades} trades, "
            f"return={metrics.total_return_pct:.2f}%, sharpe={metrics.sharpe_ratio:.3f}, "
            f"max_dd={metrics.max_drawdown:.2%}, time={run_time:.1f}s"
        )

        return result

    def _process_event(
        self,
        event: MarketEvent,
        components: Dict[str, Any],
        analyzer: PerformanceAnalyzer,
    ):
        """Process a single market event through the full pipeline."""
        try:
            regime = asyncio.get_event_loop().run_until_complete(
                components["regime_engine"].detect_regime(event)
            )

            signals = asyncio.get_event_loop().run_until_complete(
                components["strategy_engine"].generate_signals(event, regime_result=regime)
            )
            if not signals:
                return

            ev_results = asyncio.get_event_loop().run_until_complete(
                components["ev_engine"].calculate_ev(signals, event, regime_result=regime)
            )
            if not ev_results:
                return

            decision = asyncio.get_event_loop().run_until_complete(
                components["decision_engine"].make_decision(ev_results, regime_result=regime)
            )
            if not decision or not decision.actionable:
                return

            meta = asyncio.get_event_loop().run_until_complete(
                components["meta_harness"].validate_trade(decision)
            )
            if not meta.approved:
                return

            risk = asyncio.get_event_loop().run_until_complete(
                components["risk_engine"].validate_trade(decision, risk_scaling=regime.risk_scaling)
            )
            if not risk.approved:
                return

            exec_result = self._simulate_execution(decision, event)
            if exec_result.status not in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                return

            pnl = self._calculate_pnl(decision, exec_result)
            self._equity += pnl

            asyncio.get_event_loop().run_until_complete(
                components["risk_engine"].update_trade_result(pnl)
            )

            asyncio.get_event_loop().run_until_complete(
                components["ev_engine"].update_performance(
                    symbol=decision.symbol,
                    strategy=decision.strategy,
                    signal_type=decision.signal_type.value,
                    profit=pnl,
                )
            )

            trade_record = {
                "trade_id": f"bt_{len(self._trade_log) + 1}",
                "symbol": decision.symbol,
                "signal_type": decision.signal_type.value,
                "entry_price": decision.price,
                "exit_price": exec_result.filled_price,
                "size": exec_result.filled_quantity,
                "pnl": pnl,
                "pnl_pct": pnl / self.bt_settings.initial_equity * 100,
                "slippage": exec_result.slippage,
                "entry_seq": decision.event_seq,
                "exit_seq": exec_result.event_seq,
                "strategy": decision.strategy,
                "regime": regime.regime.value if hasattr(regime.regime, "value") else str(regime.regime),
                "ev_score": decision.ev_score,
                "confidence": decision.confidence,
                "equity_after": self._equity,
            }
            self._trade_log.append(trade_record)

            analyzer.add_trade(TradeRecord(
                trade_id=trade_record["trade_id"],
                symbol=trade_record["symbol"],
                signal_type=trade_record["signal_type"],
                entry_price=trade_record["entry_price"],
                exit_price=trade_record["exit_price"],
                size=trade_record["size"],
                pnl=pnl,
                pnl_pct=trade_record["pnl_pct"],
                slippage=exec_result.slippage,
                entry_seq=trade_record["entry_seq"],
                exit_seq=trade_record["exit_seq"],
                strategy=trade_record["strategy"],
                regime=trade_record["regime"],
            ))

        except Exception as e:
            logger.error(f"Error processing event {event.event_id}: {e}")

    def _simulate_execution(self, decision: Decision, event: MarketEvent) -> ExecutionResult:
        """Simulate trade execution with slippage."""
        fill_price = self._slippage_model.apply(
            price=decision.price,
            signal_type=decision.signal_type,
            size=decision.strength * self.bt_settings.initial_equity * self.siqe_settings.max_position_size,
            volume=event.volume,
            volatility=event.volatility,
        )

        position_size = decision.strength * self.siqe_settings.max_position_size
        filled_qty = position_size * self._equity / decision.price if decision.price > 0 else 0

        slippage = abs(fill_price - decision.price) / decision.price if decision.price > 0 else 0

        return ExecutionResult(
            execution_id=f"bt_exec_{self.clock.now}",
            trade_id="",
            symbol=decision.symbol,
            signal_type=decision.signal_type,
            filled_price=fill_price,
            filled_quantity=filled_qty,
            status=OrderStatus.FILLED,
            event_seq=self.clock.tick(),
            strategy=decision.strategy,
            slippage=slippage,
        )

    def _calculate_pnl(self, decision: Decision, exec_result: ExecutionResult) -> float:
        """Calculate PnL for a completed trade."""
        if decision.signal_type == SignalType.LONG:
            return (exec_result.filled_price - decision.price) * exec_result.filled_quantity
        else:
            return (decision.price - exec_result.filled_price) * exec_result.filled_quantity

    def _run_learning(self, components: Dict[str, Any], total_trades: int):
        """Run parameter update if in adaptive mode."""
        stats = self._compute_live_stats()
        stats["sample_size"] = total_trades

        for strategy_name in set(t["strategy"] for t in self._trade_log):
            strategy_stats = {
                k: v for k, v in stats.items()
                if k not in ("sample_size",)
            }
            strategy_stats["sample_size"] = len([
                t for t in self._trade_log if t["strategy"] == strategy_name
            ])

            if strategy_stats["sample_size"] < self.siqe_settings.min_sample_size:
                continue

            result = asyncio.get_event_loop().run_until_complete(
                components["learning_engine"].update_parameters(strategy_name, strategy_stats)
            )
            if result.get("success"):
                asyncio.get_event_loop().run_until_complete(
                    components["strategy_engine"].update_strategy_params(
                        strategy_name, result.get("new_parameters", {})
                    )
                )
                self._parameter_updates += 1
                logger.info(f"Learning update for {strategy_name} (trade #{total_trades})")

    def _compute_live_stats(self) -> Dict[str, Any]:
        """Compute running statistics from trade log."""
        if not self._trade_log:
            return {"win_rate": 0.5, "avg_return": 0.0, "sharpe": 0.0, "total_trades": 0}

        pnls = [t["pnl"] for t in self._trade_log]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(pnls) if pnls else 0.5
        avg_return = np.mean(pnls) / self.bt_settings.initial_equity if pnls else 0.0

        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = float(np.mean(pnls) / np.std(pnls))
        else:
            sharpe = 0.0

        return {
            "win_rate": win_rate,
            "avg_return": avg_return,
            "sharpe": sharpe,
            "total_trades": len(pnls),
        }

    def _init_components(self) -> Dict[str, Any]:
        """Initialize all SIQE pipeline components for backtest mode."""
        regime_engine = RegimeEngine(self.siqe_settings, self.clock)
        strategy_engine = StrategyEngine(self.siqe_settings, self.clock)
        ev_engine = EVEngine(self.siqe_settings, self.clock)
        decision_engine = DecisionEngine(self.siqe_settings, self.clock)
        meta_harness = MetaHarness(self.siqe_settings, self.clock)
        risk_engine = RiskEngine(self.siqe_settings, self.clock)
        execution_adapter = ExecutionAdapter(self.siqe_settings, self.clock)
        feedback_loop = FeedbackLoop(self.siqe_settings, self.clock)
        regime_engine = RegimeEngine(self.siqe_settings, self.clock)
        learning_engine = LearningEngine(self.siqe_settings, self.clock)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        components = {
            "regime_engine": regime_engine,
            "strategy_engine": strategy_engine,
            "ev_engine": ev_engine,
            "decision_engine": decision_engine,
            "meta_harness": meta_harness,
            "risk_engine": risk_engine,
            "execution_adapter": execution_adapter,
            "feedback_loop": feedback_loop,
            "learning_engine": learning_engine,
        }

        for name, comp in components.items():
            try:
                loop.run_until_complete(comp.initialize())
            except Exception as e:
                logger.warning(f"Failed to initialize {name}: {e}")

        return components

    def _settings_dict(self) -> Dict[str, Any]:
        """Serialize backtest settings for result metadata."""
        return {
            "data_provider": self.bt_settings.data_provider.value,
            "symbols": self.bt_settings.symbols,
            "start_date": self.bt_settings.start_date,
            "end_date": self.bt_settings.end_date,
            "timeframe": self.bt_settings.timeframe,
            "initial_equity": self.bt_settings.initial_equity,
            "slippage_model": self.bt_settings.slippage_model.value,
            "slippage_bps": self.bt_settings.slippage_bps,
            "learning_mode": self.bt_settings.learning_mode.value,
            "learning_interval": self.bt_settings.learning_interval,
            "rng_seed": self.bt_settings.rng_seed,
        }

    def _config_dict(self) -> Dict[str, Any]:
        """Serialize SIQE config for result metadata."""
        return {
            "max_position_size": self.siqe_settings.max_position_size,
            "max_daily_loss": self.siqe_settings.max_daily_loss,
            "max_drawdown": self.siqe_settings.max_drawdown,
            "min_ev_threshold": self.siqe_settings.min_ev_threshold,
            "max_consecutive_losses": self.siqe_settings.max_consecutive_losses,
            "enable_learning": self.siqe_settings.enable_learning,
            "enable_regime_detection": self.siqe_settings.enable_regime_detection,
        }

    @staticmethod
    def _bars_per_year(timeframe: str) -> int:
        """Estimate number of bars per year for a given timeframe."""
        mapping = {
            "1m": 525600,
            "5m": 105120,
            "15m": 35040,
            "30m": 17520,
            "1h": 8760,
            "4h": 2190,
            "1d": 365,
            "1wk": 52,
            "1mo": 12,
        }
        return mapping.get(timeframe, 252)

    def run_parameter_sweep(
        self,
        data: pd.DataFrame,
        regimes: Optional[List[MarketRegime]] = None,
        n_cma_iterations: int = 30,
        grid_resolution: int = 5,
        seed: int = 42,
    ) -> Dict[MarketRegime, ParameterSweepResult]:
        """
        Sweep indicator parameters across market regimes.
        
        Args:
            data: DataFrame with 'high', 'low', 'close' columns
            regimes: List of regimes to optimize for (default: all)
            n_cma_iterations: Number of CMA-ES iterations
            grid_resolution: Grid search resolution per dimension
            seed: Random seed for reproducibility
            
        Returns:
            Dict mapping MarketRegime to ParameterSweepResult
        """
        if regimes is None:
            regimes = list(MarketRegime)
        
        adaptive_bounds = AdaptiveIndicatorBounds(
            n_cma_iterations=n_cma_iterations,
            grid_resolution=grid_resolution,
            seed=seed,
        )
        
        results = {}
        for regime in regimes:
            logger.info(f"Running parameter sweep for regime: {regime.value}")
            result = adaptive_bounds.sweep_parameters(data, regime)
            results[regime] = result
        
        logger.info(
            f"Parameter sweep complete. Optimized {len(results)} regimes."
        )
        
        return results
