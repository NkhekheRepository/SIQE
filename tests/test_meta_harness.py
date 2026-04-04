"""
Tests: Meta harness kill switch and state transitions
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock
from models.trade import Decision, SignalType, SystemState


@pytest.fixture
def settings():
    s = Settings()
    return s


@pytest.fixture
def clock():
    return EventClock()


@pytest.fixture
def valid_decision(clock):
    return Decision(
        decision_id="dec_meta_1", signal_id="sig_meta_1", symbol="BTCUSDT",
        signal_type=SignalType.LONG, strength=0.5, price=42000.0,
        strategy="mean_reversion", ev_score=0.05, confidence=0.7,
        actionable=True, event_seq=clock.now,
    )


@pytest.mark.asyncio
async def test_meta_harness_initializes_to_normal(settings, clock):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()
    assert meta.system_state == SystemState.NORMAL
    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_halt_system(settings, clock):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()

    result = await meta.halt_system("test halt")
    assert result["success"] is True
    assert meta.system_state == SystemState.HALTED
    assert meta.override_active is True

    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_resume_system(settings, clock):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()
    await meta.halt_system("test halt")

    result = await meta.resume_system()
    assert result["success"] is True
    assert meta.system_state == SystemState.NORMAL
    assert meta.override_active is False

    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_rejects_when_halted(settings, clock, valid_decision):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()
    await meta.halt_system("test halt")

    result = await meta.validate_trade(valid_decision)
    assert result.approved is False
    assert "halted" in result.reason.lower()

    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_rejects_low_ev(settings, clock):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()

    decision = Decision(
        decision_id="dec_meta_2", signal_id="sig_meta_2", symbol="BTCUSDT",
        signal_type=SignalType.LONG, strength=0.5, price=42000.0,
        strategy="mean_reversion", ev_score=0.001, confidence=0.7,
        actionable=True, event_seq=clock.now,
    )

    result = await meta.validate_trade(decision)
    assert result.approved is False

    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_get_status(settings, clock):
    from meta_harness.meta_governor import MetaHarness
    meta = MetaHarness(settings, clock)
    await meta.initialize()

    status = await meta.get_status()
    assert "system_state" in status
    assert "override_active" in status
    assert "kill_conditions" in status

    await meta.shutdown()
