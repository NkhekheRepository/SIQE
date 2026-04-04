"""
Walk-Forward Optimizer
Splits historical data into train/test windows for adaptive parameter validation.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from backtest.config import BacktestSettings, LearningMode
from backtest.engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Result from a single walk-forward window."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_result: Optional[BacktestResult]
    test_result: Optional[BacktestResult]
    overfit_ratio: float = 0.0


@dataclass
class WalkForwardSummary:
    """Aggregated summary across all walk-forward windows."""
    windows: List[WindowResult]
    avg_test_sharpe: float = 0.0
    avg_test_return: float = 0.0
    avg_overfit_ratio: float = 0.0
    consistent_windows: int = 0
    total_windows: int = 0
    parameter_stability: Dict[str, List[float]] = field(default_factory=dict)


class WalkForwardOptimizer:
    """Walk-forward analysis for validating parameter stability.

    Splits data into rolling train/test windows:
    - Train window: run backtest with learning enabled (adaptive mode)
    - Test window: run backtest with learned params, learning disabled
    - Compare train vs test performance to detect overfitting
    """

    def __init__(
        self,
        base_settings: BacktestSettings,
        train_bars: int = 252,
        test_bars: int = 63,
        step_bars: int = 21,
    ):
        self.base_settings = base_settings
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars

    def run(self) -> WalkForwardSummary:
        """Execute walk-forward analysis across all windows."""
        logger.info(
            f"Walk-forward: train={self.train_bars}, test={self.test_bars}, "
            f"step={self.step_bars}"
        )

        data = self._fetch_all_data()
        windows = self._generate_windows(data)
        window_results = []

        for i, (train_data, test_data) in enumerate(windows):
            logger.info(f"Window {i + 1}/{len(windows)}")

            train_result = self._run_window(train_data, adaptive=True)
            test_result = self._run_window(test_data, adaptive=False)

            overfit = self._calc_overfit_ratio(train_result, test_result)

            first_symbol = list(train_data.keys())[0] if train_data else ""
            wr = WindowResult(
                window_id=i + 1,
                train_start=str(train_data[first_symbol].index[0]) if first_symbol and len(train_data[first_symbol]) > 0 else "",
                train_end=str(train_data[first_symbol].index[-1]) if first_symbol and len(train_data[first_symbol]) > 0 else "",
                test_start=str(test_data[first_symbol].index[0]) if first_symbol and len(test_data[first_symbol]) > 0 else "",
                test_end=str(test_data[first_symbol].index[-1]) if first_symbol and len(test_data[first_symbol]) > 0 else "",
                train_result=train_result,
                test_result=test_result,
                overfit_ratio=overfit,
            )
            window_results.append(wr)

        return self._summarize(window_results)

    def _fetch_all_data(self) -> Dict[str, pd.DataFrame]:
        """Fetch all historical data for the full date range."""
        from backtest.data_provider import HistoricalDataProvider
        provider = HistoricalDataProvider(self.base_settings)
        return provider.fetch()

    def _generate_windows(
        self,
        data: Dict[str, pd.DataFrame],
    ) -> List[Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]]:
        """Generate train/test window pairs from the full dataset."""
        windows = []

        for symbol, df in data.items():
            df = df.copy()
            if "datetime" in df.columns:
                df = df.set_index("datetime")
            elif "date" in df.columns:
                df = df.set_index("date")

            df = df.sort_index()
            total_bars = len(df)
            window_size = self.train_bars + self.test_bars

            if total_bars < window_size:
                logger.warning(
                    f"Not enough data for {symbol}: {total_bars} bars < {window_size} required"
                )
                continue

            start = 0
            while start + window_size <= total_bars:
                train_end = start + self.train_bars
                test_end = train_end + self.test_bars

                train_df = df.iloc[start:train_end]
                test_df = df.iloc[train_end:test_end]

                windows.append(({symbol: train_df}, {symbol: test_df}))
                start += self.step_bars

        return windows

    def _run_window(
        self,
        data: Dict[str, pd.DataFrame],
        adaptive: bool = False,
    ) -> Optional[BacktestResult]:
        """Run a single backtest window."""
        try:
            settings = BacktestSettings(
                data_provider=self.base_settings.data_provider,
                symbols=self.base_settings.symbols,
                start_date=self.base_settings.start_date,
                end_date=self.base_settings.end_date,
                timeframe=self.base_settings.timeframe,
                initial_equity=self.base_settings.initial_equity,
                slippage_model=self.base_settings.slippage_model,
                slippage_bps=self.base_settings.slippage_bps,
                learning_mode=LearningMode.ADAPTIVE if adaptive else LearningMode.FIXED,
                learning_interval=self.base_settings.learning_interval,
                rng_seed=self.base_settings.rng_seed,
            )

            from core.clock import EventClock
            from backtest.data_provider import CSVProvider

            engine = BacktestEngine(settings)
            clock = EventClock()

            provider = CSVProvider()
            events = provider.to_market_events(data, clock, settings)

            components = engine._init_components()
            from backtest.performance import PerformanceAnalyzer, TradeRecord

            analyzer = PerformanceAnalyzer(
                initial_equity=settings.initial_equity,
                bars_per_year=engine._bars_per_year(settings.timeframe),
            )

            for event in events:
                analyzer.record_equity(engine._equity)
                engine._process_event(event, components, analyzer)

                if settings.learning_mode.value == "adaptive":
                    total_trades = len(engine._trade_log)
                    if total_trades > 0 and total_trades % settings.learning_interval == 0:
                        engine._run_learning(components, total_trades)

            analyzer.record_equity(engine._equity)
            analyzer.set_event_counts(len(events), 0)
            analyzer.set_bars_analyzed(len(events))
            metrics = analyzer.compute()

            return BacktestResult(
                metrics=metrics,
                settings=engine._settings_dict(),
                config=engine._config_dict(),
                trades=engine._trade_log,
                run_time_seconds=0,
                seed=settings.rng_seed,
                data_source="walk_forward",
                bars_analyzed=len(events),
                events_processed=len(events),
                events_rejected=0,
            )
        except Exception as e:
            logger.error(f"Window backtest failed: {e}")
            return None

    def _calc_overfit_ratio(
        self,
        train_result: Optional[BacktestResult],
        test_result: Optional[BacktestResult],
    ) -> float:
        """Calculate overfitting ratio between train and test performance."""
        if train_result is None or test_result is None:
            return 0.0

        train_sharpe = train_result.metrics.sharpe_ratio
        test_sharpe = test_result.metrics.sharpe_ratio

        if train_sharpe == 0:
            return 0.0

        return (train_sharpe - test_sharpe) / abs(train_sharpe)

    def _summarize(self, window_results: List[WindowResult]) -> WalkForwardSummary:
        """Aggregate results across all windows."""
        test_sharpes = []
        test_returns = []
        overfit_ratios = []
        consistent = 0

        for wr in window_results:
            if wr.test_result is not None:
                test_sharpes.append(wr.test_result.metrics.sharpe_ratio)
                test_returns.append(wr.test_result.metrics.total_return_pct)
                overfit_ratios.append(wr.overfit_ratio)

                if wr.train_result is not None:
                    train_pos = wr.train_result.metrics.total_return_pct > 0
                    test_pos = wr.test_result.metrics.total_return_pct > 0
                    if train_pos == test_pos:
                        consistent += 1

        return WalkForwardSummary(
            windows=window_results,
            avg_test_sharpe=sum(test_sharpes) / len(test_sharpes) if test_sharpes else 0.0,
            avg_test_return=sum(test_returns) / len(test_returns) if test_returns else 0.0,
            avg_overfit_ratio=sum(overfit_ratios) / len(overfit_ratios) if overfit_ratios else 0.0,
            consistent_windows=consistent,
            total_windows=len(window_results),
        )
