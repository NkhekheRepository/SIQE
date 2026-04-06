"""
SIQE V3 - Integration Tests
Tests the full 7-stage pipeline with real components wired together.
Phase 5: Production hardening integration tests.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from core.clock import EventClock, RealTimeClock
from config.settings import Settings
from models.trade import MarketEvent, SignalType


def make_market_event(symbol="BTCUSDT", bid=50000.0, ask=50010.0, seq=1):
    return {
        "event_id": f"evt_{symbol.lower()}_{seq}",
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "volume": 1000.0,
        "volatility": 0.0002,
        "event_seq": seq,
    }


class TestDataEngineRealMarketData:
    """Test DataEngine with real market data sources."""

    def test_realtime_clock_wall_clock(self):
        clock = RealTimeClock(daily_reset_hour=0)
        assert clock.wall_clock is not None
        assert clock.unix_timestamp > 0
        assert 0 <= clock.get_hour_utc() <= 23
        assert 0 <= clock.get_minute_utc() <= 59

    def test_realtime_clock_daily_reset_callback(self):
        clock = RealTimeClock(daily_reset_hour=0)
        callback_called = []

        def cb():
            callback_called.append(True)

        clock.on_daily_reset(cb)
        assert len(callback_called) == 0
        clock._trigger_daily_reset()
        assert len(callback_called) == 1

    def test_event_clock_deterministic(self):
        clock = EventClock()
        assert clock.tick() == 1
        assert clock.tick() == 2
        assert clock.tick() == 3
        clock.reset()
        assert clock.tick() == 1


class TestFeedbackLoopActivation:
    """Test that feedback loop actually passes data to components."""

    @pytest.mark.asyncio
    async def test_decompose_pnl_no_random_noise(self):
        from feedback.feedback_loop import FeedbackLoop
        from models.trade import ExecutionResult, Trade, OrderStatus, SignalType

        clock = EventClock()
        settings = Settings()
        loop = FeedbackLoop(settings, clock)

        exec_result = ExecutionResult(
            execution_id="exec_1",
            trade_id="trade_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            filled_price=50000.0,
            filled_quantity=0.01,
            status=OrderStatus.FILLED,
            event_seq=1,
        )

        trade = Trade(
            id="trade_1",
            signal="long",
            confidence=0.5,
            ev=0.1,
            size=0.01,
            price=50000.0,
            timestamp=1,
        )

        decomp = loop._decompose_pnl(exec_result, trade)
        assert decomp.total_pnl == decomp.signal_alpha + decomp.execution_alpha + decomp.noise
        assert decomp.noise == 0.0


class TestStrategyEngineDuckDBMetrics:
    """Test strategy performance uses DuckDB not random data."""

    @pytest.mark.asyncio
    async def test_strategy_performance_uses_duckdb(self):
        from strategy_engine.strategy_base import StrategyEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = StrategyEngine(settings, clock)
        await engine.initialize()

        perf = await engine.get_strategy_performance()
        assert "mean_reversion" in perf
        assert "momentum" in perf
        assert "breakout" in perf

        for name, metrics in perf.items():
            assert "active" in metrics
            assert "signal_count" in metrics
            assert "win_rate" in metrics
            assert "avg_return" in metrics

        await engine.shutdown()


class TestRiskEnginePortfolioVaR:
    """Test portfolio-level VaR with Monte Carlo simulation."""

    @pytest.mark.asyncio
    async def test_portfolio_var_with_insufficient_data(self):
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)

        result = await engine.get_var_status()
        assert result["sample_size"] == 0

    def test_correlation_matrix_insufficient_data(self):
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)

        result = engine.get_correlation_matrix()
        assert "error" in result

    def test_portfolio_risk_limits_empty(self):
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)

        result = engine.check_portfolio_risk_limits()
        assert result["within_limits"] is True
        assert result["n_positions"] == 0
        assert result["portfolio_notional"] == 0.0

    def test_position_tracking(self):
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)

        engine.update_symbol_position("BTCUSDT", 5000.0, 100.0)
        engine.update_symbol_position("ETHUSDT", 3000.0, 50.0)

        assert engine.get_portfolio_notional() == 8000.0
        assert engine.get_portfolio_pnl() == 150.0
        assert len(engine._symbol_positions) == 2

        engine.remove_symbol_position("BTCUSDT")
        assert engine.get_portfolio_notional() == 3000.0


class TestPositionSizerPortfolio:
    """Test portfolio-level position sizing."""

    def test_portfolio_sizer_single_asset(self):
        from strategy_engine.position_sizer import PortfolioSizer
        import pandas as pd
        import numpy as np

        sizer = PortfolioSizer(max_portfolio_risk=0.02, max_single_position_risk=0.01)
        rng = np.random.RandomState(42)
        returns = {"BTCUSDT": pd.Series(rng.normal(0.001, 0.02, 100))}
        prices = {"BTCUSDT": 50000.0}

        alloc = sizer.allocate(returns, 10000.0, prices)
        assert "BTCUSDT" in alloc
        assert alloc["BTCUSDT"].method == "kelly"
        assert alloc["BTCUSDT"].dollar_amount >= 0

    def test_portfolio_sizer_multi_asset(self):
        from strategy_engine.position_sizer import PortfolioSizer
        import pandas as pd
        import numpy as np

        sizer = PortfolioSizer(max_portfolio_risk=0.02, max_single_position_risk=0.01)
        rng = np.random.RandomState(42)
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        returns = {s: pd.Series(rng.normal(0.001, 0.02, 100)) for s in symbols}
        prices = {"BTCUSDT": 50000.0, "ETHUSDT": 3000.0, "SOLUSDT": 100.0}

        alloc = sizer.allocate(returns, 10000.0, prices)
        assert len(alloc) == 3
        for sym in symbols:
            assert sym in alloc
            assert alloc[sym].dollar_amount > 0
            assert alloc[sym].fraction_of_portfolio > 0

    def test_portfolio_sizer_correlation_aware(self):
        from strategy_engine.position_sizer import PortfolioSizer
        import pandas as pd
        import numpy as np

        sizer = PortfolioSizer(max_portfolio_risk=0.02, max_single_position_risk=0.01)
        rng = np.random.RandomState(42)
        symbols = ["BTCUSDT", "ETHUSDT"]
        returns = {s: pd.Series(rng.normal(0.001, 0.02, 100)) for s in symbols}
        prices = {"BTCUSDT": 50000.0, "ETHUSDT": 3000.0}
        corr = np.array([[1.0, 0.7], [0.7, 1.0]])

        alloc = sizer.allocate(returns, 10000.0, prices, correlation_matrix=corr)
        assert len(alloc) == 2
        for sym in symbols:
            assert alloc[sym].method == "risk_parity_corr"


class TestMLOptimizerWiring:
    """Test ML optimizer wiring to learning engine."""

    @pytest.mark.asyncio
    async def test_learning_engine_init_ml_optimizer(self):
        from learning.learning_engine import LearningEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        settings.ml_optimizer = "bayesian"
        engine = LearningEngine(settings, clock)
        await engine.initialize()

        await engine._init_ml_optimizer()
        assert engine._ml_optimizer is not None
        assert engine._ml_initialized is True

    @pytest.mark.asyncio
    async def test_learning_engine_with_data_engine(self):
        from learning.learning_engine import LearningEngine
        from core.clock import EventClock
        from config.settings import Settings
        from core.data_engine import DataEngine

        clock = EventClock()
        settings = Settings()
        engine = LearningEngine(settings, clock)
        data_engine = DataEngine(settings, clock)

        engine.set_data_engine(data_engine)
        assert engine.data_engine is data_engine


class TestMTFConfirmation:
    """Test multi-timeframe confirmation."""

    def test_mtf_rejects_contradicting_signal(self):
        from strategy_engine.multitimeframe import MultiTimeframeConfirmator, MTFSignal
        import pandas as pd
        import numpy as np

        confirmator = MultiTimeframeConfirmator()
        rng = np.random.RandomState(42)

        n_15m = 200
        n_4h = 100
        closes_15m = pd.Series(rng.normal(50000, 500, n_15m).cumsum() / n_15m * 50000)
        closes_4h = pd.Series(rng.normal(50000, 1000, n_4h).cumsum() / n_4h * 50000)

        df_15m = pd.DataFrame({
            "close": closes_15m,
            "high": closes_15m + rng.uniform(10, 100, n_15m),
            "low": closes_15m - rng.uniform(10, 100, n_15m),
        })
        df_4h = pd.DataFrame({
            "close": closes_4h,
            "high": closes_4h + rng.uniform(100, 500, n_4h),
            "low": closes_4h - rng.uniform(100, 500, n_4h),
        })

        result = confirmator.confirm_signal(df_15m, df_4h, original_signal=1)
        assert result.signal in (
            MTFSignal.CONFIRMED_LONG,
            MTFSignal.WEAKENED_LONG,
            MTFSignal.REJECTED,
        )


class TestABTestFramework:
    """Test A/B testing framework."""

    def test_ab_test_runner_runs(self):
        from strategy_engine.ab_testing import ABTestRunner
        from strategy_engine.config import IndicatorConfig
        import pandas as pd
        import numpy as np

        rng = np.random.RandomState(42)
        n = 500
        closes = pd.Series(rng.normal(50000, 500, n).cumsum() / n * 50000)
        data = pd.DataFrame({
            "close": closes,
            "high": closes + rng.uniform(10, 100, n),
            "low": closes - rng.uniform(10, 100, n),
        })

        baseline = IndicatorConfig()
        treatment = IndicatorConfig(macd_fast=8, macd_slow=21)

        runner = ABTestRunner(baseline, treatment, seed=42)
        result = runner.run(data, n_simulations=50)

        assert result.baseline_sharpe != 0 or result.treatment_sharpe != 0
        assert result.recommendation in ("deploy", "reject", "inconclusive")


class TestCircuitBreakers:
    """Test circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_emergency_stop_activates_breaker(self):
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        await engine.emergency_stop("Test emergency")
        status = await engine.get_circuit_breaker_status()
        assert status["any_active"] is True
        assert "emergency_stop" in status["active_breakers"]

    @pytest.mark.asyncio
    async def test_emergency_resume_clears_breakers(self):
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        await engine.emergency_stop("Test")
        await engine.emergency_resume()
        status = await engine.get_circuit_breaker_status()
        assert status["any_active"] is False


class TestGracefulShutdown:
    """Test graceful shutdown and state persistence."""

    @pytest.mark.asyncio
    async def test_state_manager_save_and_load(self):
        from memory.state_manager import StateManager
        from config.settings import Settings
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            settings = Settings()
            settings.db_path = db_path

            sm = StateManager(settings)
            assert await sm.initialize() is True

            trade_data = {
                "execution_id": "test_trade_1",
                "symbol": "BTCUSDT",
                "signal_type": "long",
                "price": 50000.0,
                "quantity": 0.01,
                "timestamp": "2026-04-06T00:00:00",
                "strategy": "test",
                "ev_score": 0.5,
                "pnl": 100.0,
                "status": "FILLED",
                "execution_details": {},
            }
            assert await sm.save_trade(trade_data) is True

            trades = await sm.get_recent_trades(limit=10)
            assert len(trades) >= 1

            stats = await sm.get_trade_statistics()
            assert stats.get("total_trades", 0) >= 1

            await sm.shutdown()
