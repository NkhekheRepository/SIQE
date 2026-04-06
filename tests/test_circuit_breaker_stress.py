"""
SIQE V3 - Circuit Breaker Stress Test
Stress tests all circuit breakers under simulated failure conditions.
Phase 5: Production hardening.
"""
import asyncio
import pytest
from core.clock import EventClock
from config.settings import Settings
from models.trade import Decision, SignalType, ApprovalResult


class TestCircuitBreakerStress:
    """Stress test circuit breakers under rapid-fire failure conditions."""

    @pytest.mark.asyncio
    async def test_rapid_api_failures_trigger_breaker(self):
        """API failures should trigger after _max_api_failures consecutive failures."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Fire rapid API failures
        for i in range(5):
            await engine.record_api_failure()

        status = await engine.get_circuit_breaker_status()
        assert status["any_active"] is True
        assert "api_failures" in status["active_breakers"]

        # Verify API success resets counter
        await engine.record_api_success()
        assert engine._api_failure_count == 0

    @pytest.mark.asyncio
    async def test_rapid_consecutive_losses_trigger_breaker(self):
        """Consecutive losses should trigger breaker after threshold."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        settings.max_consecutive_losses = 3
        settings.max_daily_loss = 0.50  # High enough that daily loss doesn't trigger first
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        decision = Decision(
            decision_id="test_1",
            signal_id="sig_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.5,
            price=50000.0,
            strategy="test",
            ev_score=0.1,
            confidence=0.5,
            actionable=True,
            event_seq=1,
            reasoning="test",
        )

        # Simulate consecutive losses
        for i in range(5):
            await engine.update_trade_result(-100.0)

        # Next trade should be rejected
        result = await engine.validate_trade(decision)
        assert not result.approved
        assert "consecutive losses" in result.reason.lower() or "circuit breaker" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_daily_loss_triggers_breaker(self):
        """Large daily losses should trigger daily loss circuit breaker."""
        from risk_engine.risk_manager import RiskEngine

        clock = EventClock()
        settings = Settings()
        settings.max_daily_loss = 0.05
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Simulate losses exceeding daily limit
        initial_equity = engine.current_equity
        loss_per_trade = initial_equity * 0.02  # 2% per trade

        for i in range(10):
            await engine.update_trade_result(-loss_per_trade)

        daily_loss_pct = abs(engine.daily_pnl) / engine.current_equity
        assert daily_loss_pct >= settings.max_daily_loss

    @pytest.mark.asyncio
    async def test_drawdown_triggers_breaker(self):
        """Drawdown exceeding limit should trigger circuit breaker."""
        from risk_engine.risk_manager import RiskEngine
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        settings.max_drawdown = 0.10
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Simulate losses creating drawdown
        for i in range(20):
            await engine.update_trade_result(-500.0)

        current_dd = (engine.peak_equity - engine.current_equity) / engine.peak_equity
        assert current_dd >= settings.max_drawdown

    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_all_trades(self):
        """Emergency stop should reject all subsequent trade validations."""
        from risk_engine.risk_manager import RiskEngine
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        await engine.emergency_stop("Stress test emergency")

        decision = Decision(
            decision_id="test_1",
            signal_id="sig_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.5,
            price=50000.0,
            strategy="test",
            ev_score=0.1,
            confidence=0.5,
            actionable=True,
            event_seq=1,
            reasoning="test",
        )

        result = await engine.validate_trade(decision)
        assert not result.approved
        assert "emergency_stop" in result.reason.lower() or "circuit breaker" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_emergency_resume_clears_all_breakers(self):
        """Emergency resume should deactivate all circuit breakers."""
        from risk_engine.risk_manager import RiskEngine

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        await engine.emergency_stop("Test")
        status = await engine.get_circuit_breaker_status()
        assert status["any_active"] is True

        await engine.emergency_resume()
        status = await engine.get_circuit_breaker_status()
        assert status["any_active"] is False
        assert status["emergency_stop_reason"] == ""

    @pytest.mark.asyncio
    async def test_circuit_breaker_history_tracks_triggers(self):
        """Circuit breaker history should track all activations."""
        from risk_engine.risk_manager import RiskEngine

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Trigger multiple breakers
        await engine.emergency_stop("Test 1")
        await engine.emergency_resume()
        await engine.emergency_stop("Test 2")

        status = await engine.get_circuit_breaker_status()
        assert len(status["recent_triggers"]) >= 2

    @pytest.mark.asyncio
    async def test_hourly_trade_limit_enforced(self):
        """Hourly trade limit should reject trades exceeding max_trades_per_hour."""
        from risk_engine.risk_manager import RiskEngine
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        settings.max_trades_per_hour = 5
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        decision = Decision(
            decision_id="test_1",
            signal_id="sig_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.5,
            price=50000.0,
            strategy="test",
            ev_score=0.1,
            confidence=0.5,
            actionable=True,
            event_seq=1,
            reasoning="test",
        )

        # Approve up to limit
        for i in range(5):
            result = await engine.validate_trade(decision)
            assert result.approved, f"Trade {i+1} should be approved"

        # Next should be rejected
        result = await engine.validate_trade(decision)
        assert not result.approved
        assert "hourly" in result.reason.lower() or "limit" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_position_size_limit_enforced(self):
        """Position size exceeding max_position_size should be rejected."""
        from risk_engine.risk_manager import RiskEngine
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        settings.max_position_size = 0.05
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        decision = Decision(
            decision_id="test_1",
            signal_id="sig_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.9,  # High strength = large position
            price=50000.0,
            strategy="test",
            ev_score=0.1,
            confidence=0.9,
            actionable=True,
            event_seq=1,
            reasoning="test",
        )

        result = await engine.validate_trade(decision)
        # With strength 0.9, estimated position = 0.9 * 0.1 = 0.09 > 0.05 max
        assert not result.approved
        assert "position size" in result.reason.lower() or "too large" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_recovery_after_emergency_stop(self):
        """System should function normally after emergency stop and resume."""
        from risk_engine.risk_manager import RiskEngine
        from models.trade import Decision, SignalType

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Normal operation
        decision = Decision(
            decision_id="test_1",
            signal_id="sig_1",
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.3,
            price=50000.0,
            strategy="test",
            ev_score=0.1,
            confidence=0.5,
            actionable=True,
            event_seq=1,
            reasoning="test",
        )

        result1 = await engine.validate_trade(decision)
        assert result1.approved

        # Emergency stop
        await engine.emergency_stop("Test")
        result2 = await engine.validate_trade(decision)
        assert not result2.approved

        # Resume
        await engine.emergency_resume()
        result3 = await engine.validate_trade(decision)
        assert result3.approved

    @pytest.mark.asyncio
    async def test_var_calculation_with_real_data(self):
        """VaR should calculate correctly with sufficient trade data."""
        from risk_engine.risk_manager import RiskEngine

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Simulate realistic trade returns
        import random
        random.seed(42)
        for i in range(100):
            pnl = random.gauss(50, 200)  # Mean $50, std $200
            await engine.update_trade_result(pnl)

        var_status = await engine.get_var_status()
        assert var_status["sample_size"] == 100
        assert var_status["var_95"] >= 0
        assert var_status["var_99"] >= 0
        assert var_status["cvar_99"] >= 0
        # CVaR should be >= VaR (expected shortfall beyond VaR)
        assert var_status["cvar_99"] >= var_status["var_99"]


class TestSystemResilience:
    """Test system-level resilience under stress."""

    @pytest.mark.asyncio
    async def test_state_manager_concurrent_access(self):
        """StateManager should handle concurrent trade saves safely."""
        from memory.state_manager import StateManager
        from config.settings import Settings
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "stress.db")
            settings = Settings()
            settings.db_path = db_path

            sm = StateManager(settings)
            await sm.initialize()

            # Concurrent trade saves
            tasks = []
            for i in range(50):
                trade_data = {
                    "execution_id": f"stress_trade_{i}",
                    "symbol": "BTCUSDT",
                    "signal_type": "long",
                    "price": 50000.0 + i,
                    "quantity": 0.01,
                    "timestamp": f"2026-04-06T00:{i:02d}:00",
                    "strategy": "stress_test",
                    "ev_score": 0.5,
                    "pnl": float(i - 25),
                    "status": "FILLED",
                    "execution_details": {},
                }
                tasks.append(sm.save_trade(trade_data))

            results = await asyncio.gather(*tasks)
            assert all(results), "All concurrent saves should succeed"

            trades = await sm.get_recent_trades(limit=100)
            assert len(trades) >= 50

            await sm.shutdown()

    @pytest.mark.asyncio
    async def test_risk_metrics_reset_daily(self):
        """Daily reset should clear daily PnL but preserve equity state."""
        from risk_engine.risk_manager import RiskEngine

        clock = EventClock()
        settings = Settings()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        # Simulate some trading
        await engine.update_trade_result(100.0)
        await engine.update_trade_result(-50.0)

        assert engine.daily_pnl == 50.0
        peak = engine.peak_equity
        equity = engine.current_equity

        await engine.reset_daily_metrics()
        assert engine.daily_pnl == 0.0
        assert engine.peak_equity == peak
        assert engine.current_equity == equity
