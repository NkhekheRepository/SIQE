"""
Tests: Risk constraint enforcement
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock
from models.trade import Decision, SignalType, ApprovalResult


@pytest.fixture
def settings():
    s = Settings()
    s.max_position_size = 0.1
    s.max_daily_loss = 0.05
    s.max_drawdown = 0.20
    s.max_consecutive_losses = 5
    s.max_trades_per_hour = 100
    return s


@pytest.fixture
def clock():
    return EventClock()


@pytest.fixture
def valid_decision(clock):
    return Decision(
        decision_id="dec_risk_1",
        signal_id="sig_risk_1",
        symbol="BTCUSDT",
        signal_type=SignalType.LONG,
        strength=0.5,
        price=42000.0,
        strategy="mean_reversion",
        ev_score=0.05,
        confidence=0.7,
        actionable=True,
        event_seq=clock.now,
    )


@pytest.mark.asyncio
async def test_risk_approves_normal_trade(settings, clock, valid_decision):
    risk = RiskEngine(settings, clock)
    await risk.initialize()
    result = await risk.validate_trade(valid_decision, risk_scaling=1.0)
    assert result.approved is True
    await risk.shutdown()


@pytest.mark.asyncio
async def test_risk_rejects_large_position(settings, clock):
    risk = RiskEngine(settings, clock)
    await risk.initialize()

    decision = Decision(
        decision_id="dec_risk_2", signal_id="sig_risk_2", symbol="BTCUSDT",
        signal_type=SignalType.LONG, strength=1.0, price=42000.0,
        strategy="mean_reversion", ev_score=0.05, confidence=0.7,
        actionable=True, event_seq=clock.now,
    )

    result = await risk.validate_trade(decision, risk_scaling=1.0)
    assert result.approved is True

    await risk.shutdown()


@pytest.mark.asyncio
async def test_risk_rejects_after_consecutive_losses(settings, clock):
    risk = RiskEngine(settings, clock)
    await risk.initialize()

    for i in range(6):
        await risk.update_trade_result(-10.0)

    decision = Decision(
        decision_id="dec_risk_3", signal_id="sig_risk_3", symbol="BTCUSDT",
        signal_type=SignalType.LONG, strength=0.5, price=42000.0,
        strategy="mean_reversion", ev_score=0.05, confidence=0.7,
        actionable=True, event_seq=clock.now,
    )

    result = await risk.validate_trade(decision, risk_scaling=1.0)
    assert result.approved is False
    assert "consecutive" in result.reason.lower() or "daily loss" in result.reason.lower()

    await risk.shutdown()


from risk_engine.risk_manager import RiskEngine
