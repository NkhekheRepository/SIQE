"""
Tests: Full pipeline execution
"""
import asyncio
import pytest
import pytest_asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock
from models.trade import (
    MarketEvent, Signal, SignalType, EVResult, Decision,
    Trade, ExecutionResult, OrderStatus, RegimeResult, RegimeType,
    ApprovalResult,
)
from strategy_engine.strategy_base import StrategyEngine
from ev_engine.ev_calculator import EVEngine
from decision_engine.decision_maker import DecisionEngine
from meta_harness.meta_governor import MetaHarness
from risk_engine.risk_manager import RiskEngine
from execution_adapter.vnpy_bridge import ExecutionAdapter
from regime.regime_engine import RegimeEngine


@pytest.fixture
def settings():
    s = Settings()
    s.use_mock_execution = True
    return s


@pytest.fixture
def clock():
    c = EventClock()
    return c


@pytest.fixture
def market_event(clock):
    seq = clock.tick()
    return MarketEvent(
        event_id=f"evt_test_{seq}",
        symbol="BTCUSDT",
        bid=42000.0,
        ask=42010.0,
        volume=50.0,
        volatility=0.02,
        event_seq=seq,
    )


@pytest.mark.asyncio
async def test_full_pipeline_produces_signals(settings, clock, market_event):
    strategy_engine = StrategyEngine(settings, clock)
    await strategy_engine.initialize()

    import numpy as np
    rng = np.random.RandomState(42)
    base_price = 42000.0
    for i in range(250):
        price = base_price + rng.randn() * 50 + i * 5
        spread = 10.0
        strategy_engine.update_price_history(
            market_event.symbol,
            price + spread / 2,
            price - spread / 2,
            price,
        )

    regime = RegimeResult(regime=RegimeType.MIXED, confidence=0.5, event_seq=clock.now)
    signals = await strategy_engine.generate_signals(market_event, regime_result=regime)

    assert signals is not None
    assert len(signals) > 0
    assert isinstance(signals[0], Signal)
    assert signals[0].signal_type in (SignalType.LONG, SignalType.SHORT)
    assert 0.0 <= signals[0].strength <= 1.0

    await strategy_engine.shutdown()


@pytest.mark.asyncio
async def test_pipeline_ev_calculation(settings, clock, market_event):
    strategy_engine = StrategyEngine(settings, clock)
    await strategy_engine.initialize()

    ev_engine = EVEngine(settings, clock)
    await ev_engine.initialize()

    regime = RegimeResult(regime=RegimeType.MIXED, confidence=0.5, event_seq=clock.now)
    signals = await strategy_engine.generate_signals(market_event, regime_result=regime)

    if signals:
        ev_results = await ev_engine.calculate_ev(signals, market_event, regime_result=regime)
        assert ev_results is not None
        assert isinstance(ev_results[0], EVResult)
        assert isinstance(ev_results[0].ev_score, float)
        assert isinstance(ev_results[0].actionable, bool)

    await strategy_engine.shutdown()
    await ev_engine.shutdown()


@pytest.mark.asyncio
async def test_pipeline_decision_making(settings, clock, market_event):
    strategy_engine = StrategyEngine(settings, clock)
    await strategy_engine.initialize()
    ev_engine = EVEngine(settings, clock)
    await ev_engine.initialize()
    decision_engine = DecisionEngine(settings, clock)
    await decision_engine.initialize()

    regime = RegimeResult(regime=RegimeType.MIXED, confidence=0.5, event_seq=clock.now)
    signals = await strategy_engine.generate_signals(market_event, regime_result=regime)

    if signals:
        ev_results = await ev_engine.calculate_ev(signals, market_event, regime_result=regime)
        if ev_results:
            decision = await decision_engine.make_decision(ev_results, regime_result=regime)
            if decision:
                assert isinstance(decision, Decision)
                assert 0.0 <= decision.confidence <= 1.0
                assert decision.actionable is True

    await strategy_engine.shutdown()
    await ev_engine.shutdown()
    await decision_engine.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_approval(settings, clock, market_event):
    meta = MetaHarness(settings, clock)
    await meta.initialize()

    decision = Decision(
        decision_id="dec_test_1",
        signal_id="sig_test_1",
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

    result = await meta.validate_trade(decision)
    assert isinstance(result, ApprovalResult)
    assert result.approved is True

    await meta.shutdown()


@pytest.mark.asyncio
async def test_meta_harness_rejection_when_halted(settings, clock):
    meta = MetaHarness(settings, clock)
    await meta.initialize()
    await meta.halt_system("test halt")

    decision = Decision(
        decision_id="dec_test_2",
        signal_id="sig_test_2",
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

    result = await meta.validate_trade(decision)
    assert result.approved is False
    assert "halted" in result.reason.lower()

    await meta.shutdown()


@pytest.mark.asyncio
async def test_risk_engine_approval(settings, clock):
    risk = RiskEngine(settings, clock)
    await risk.initialize()

    decision = Decision(
        decision_id="dec_test_3",
        signal_id="sig_test_3",
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

    result = await risk.validate_trade(decision, risk_scaling=1.0)
    assert isinstance(result, ApprovalResult)
    assert result.approved is True

    await risk.shutdown()


@pytest.mark.asyncio
async def test_execution_adapter_produces_result(settings, clock):
    adapter = ExecutionAdapter(settings, clock)
    await adapter.initialize()

    decision = Decision(
        decision_id="dec_test_4",
        signal_id="sig_test_4",
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

    result = await adapter.execute_trade(decision)
    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.filled_price > 0
    assert result.filled_quantity > 0

    await adapter.shutdown()
