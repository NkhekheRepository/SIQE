"""
Circuit Breaker Tests
Tests for circuit breaker functionality in risk engine.
"""
import pytest
from unittest.mock import Mock, AsyncMock

from risk_engine.risk_manager import (
    RiskEngine, CircuitBreakerType, CircuitBreakerState
)
from models.trade import Decision, SignalType, ApprovalResult
from core.clock import EventClock


class TestCircuitBreakerState:
    def test_activate_sets_state(self):
        breaker = CircuitBreakerState(CircuitBreakerType.DAILY_LOSS)
        breaker.activate(100, "Test reason")

        assert breaker.is_active is True
        assert breaker.triggered_at == 100
        assert breaker.trigger_reason == "Test reason"
        assert breaker.trigger_count == 1

    def test_deactivate_clears_state(self):
        breaker = CircuitBreakerState(CircuitBreakerType.DAILY_LOSS)
        breaker.activate(100, "Test reason")
        breaker.deactivate()

        assert breaker.is_active is False
        assert breaker.triggered_at == 0
        assert breaker.trigger_reason == ""

    def test_to_dict_returns_correct_structure(self):
        breaker = CircuitBreakerState(CircuitBreakerType.DRAWDOWN)
        breaker.activate(200, "Drawdown exceeded")

        result = breaker.to_dict()

        assert result["type"] == "drawdown"
        assert result["is_active"] is True
        assert result["triggered_at"] == 200
        assert result["trigger_reason"] == "Drawdown exceeded"
        assert result["trigger_count"] == 1


class TestRiskEngineCircuitBreakers:
    @pytest.fixture
    def risk_engine(self):
        settings = {
            "initial_equity": 10000.0,
            "max_daily_loss": 0.05,
            "max_drawdown": 0.20,
            "max_position_size": 0.1,
            "max_consecutive_losses": 5,
            "max_trades_per_hour": 100,
            "volatility_scaling": True,
        }
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        engine.is_initialized = True
        return engine

    @pytest.mark.asyncio
    async def test_daily_loss_breaker_activation(self, risk_engine):
        risk_engine.current_equity = 10000.0
        risk_engine.peak_equity = 10000.0
        risk_engine.daily_pnl = -600.0

        decision = Decision(
            decision_id="dec_1",
            signal_id="sig_1",
            event_seq=1,
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.8,
            price=50000.0,
            strategy="test",
            ev_score=0.05,
            confidence=0.7,
            actionable=True,
        )

        result = await risk_engine.validate_trade(decision)

        assert result.approved is False
        assert "Daily loss" in result.reason or "circuit breaker" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_drawdown_breaker_activation(self, risk_engine):
        risk_engine.current_equity = 7500.0
        risk_engine.peak_equity = 10000.0
        risk_engine.daily_pnl = -2500.0

        decision = Decision(
            decision_id="dec_1",
            signal_id="sig_1",
            event_seq=1,
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.8,
            price=50000.0,
            strategy="test",
            ev_score=0.05,
            confidence=0.7,
            actionable=True,
        )

        result = await risk_engine.validate_trade(decision)

        assert result.approved is False

    @pytest.mark.asyncio
    async def test_consecutive_losses_breaker(self, risk_engine):
        risk_engine.consecutive_losses = 5

        decision = Decision(
            decision_id="dec_1",
            signal_id="sig_1",
            event_seq=1,
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.8,
            price=50000.0,
            strategy="test",
            ev_score=0.05,
            confidence=0.7,
            actionable=True,
        )

        result = await risk_engine.validate_trade(decision)

        assert result.approved is False
        assert "consecutive losses" in result.reason.lower() or "circuit breaker" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_trades_blocked_by_active_breaker(self, risk_engine):
        await risk_engine.emergency_stop("Manual test stop")

        decision = Decision(
            decision_id="dec_1",
            signal_id="sig_1",
            event_seq=1,
            symbol="BTCUSDT",
            signal_type=SignalType.LONG,
            strength=0.8,
            price=50000.0,
            strategy="test",
            ev_score=0.05,
            confidence=0.7,
            actionable=True,
        )

        result = await risk_engine.validate_trade(decision)

        assert result.approved is False
        assert "circuit breaker" in result.reason.lower() or "emergency" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_emergency_stop(self, risk_engine):
        result = await risk_engine.emergency_stop("Test emergency")

        assert result["success"] is True
        assert result["reason"] == "Test emergency"

        breaker_status = await risk_engine.get_circuit_breaker_status()
        assert breaker_status["any_active"] is True
        assert "emergency_stop" in breaker_status["active_breakers"]

    @pytest.mark.asyncio
    async def test_emergency_resume(self, risk_engine):
        await risk_engine.emergency_stop("Test emergency")
        result = await risk_engine.emergency_resume()

        assert result["success"] is True

        breaker_status = await risk_engine.get_circuit_breaker_status()
        assert breaker_status["any_active"] is False

    @pytest.mark.asyncio
    async def test_api_failure_breaker(self, risk_engine):
        for _ in range(3):
            await risk_engine.record_api_failure()

        breaker_status = await risk_engine.get_circuit_breaker_status()
        assert breaker_status["api_failure_count"] == 3

        assert breaker_status["circuit_breakers"]["api_failures"]["is_active"] is True


class TestCircuitBreakerIntegration:
    @pytest.mark.asyncio
    async def test_trade_rejected_when_any_breaker_active(self):
        settings = {
            "initial_equity": 10000.0,
            "max_daily_loss": 0.05,
            "max_drawdown": 0.20,
            "max_position_size": 0.1,
            "max_consecutive_losses": 5,
            "max_trades_per_hour": 100,
            "volatility_scaling": True,
        }
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        await engine.initialize()

        await engine.emergency_stop("Integration test")

        decision = Decision(
            decision_id="dec_1",
            signal_id="sig_1",
            event_seq=1,
            symbol="ETHUSDT",
            signal_type=SignalType.SHORT,
            strength=0.5,
            price=3000.0,
            strategy="test",
            ev_score=0.03,
            confidence=0.6,
            actionable=True,
        )

        result = await engine.validate_trade(decision)

        assert result.approved is False
        assert "circuit breaker" in result.reason.lower() or "emergency" in result.reason.lower()
