"""
Tests: Determinism verification
"""
import asyncio
import pytest
import sys
import os
import random
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock
from models.trade import MarketEvent, SignalType
from strategy_engine.strategy_base import StrategyEngine
from ev_engine.ev_calculator import EVEngine
from decision_engine.decision_maker import DecisionEngine


@pytest.fixture
def settings():
    s = Settings()
    s.use_mock_execution = True
    return s


def test_event_clock_determinism():
    c1 = EventClock()
    c2 = EventClock()

    seqs1 = [c1.tick() for _ in range(10)]
    seqs2 = [c2.tick() for _ in range(10)]

    assert seqs1 == seqs2
    assert seqs1 == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_random_seed_determinism():
    random.seed(0)
    r1 = [random.random() for _ in range(5)]

    random.seed(0)
    r2 = [random.random() for _ in range(5)]

    assert r1 == r2


def test_numpy_seed_determinism():
    np.random.seed(0)
    n1 = np.random.uniform(0, 1, 5).tolist()

    np.random.seed(0)
    n2 = np.random.uniform(0, 1, 5).tolist()

    assert n1 == n2


@pytest.mark.asyncio
async def test_strategy_signals_deterministic(settings):
    c1 = EventClock()
    c2 = EventClock()

    random.seed(0)
    np.random.seed(0)
    engine1 = StrategyEngine(settings, c1)
    await engine1.initialize()
    event1 = MarketEvent(event_id="evt_1", symbol="BTCUSDT", bid=42000.0, ask=42010.0,
                         volume=50.0, volatility=0.02, event_seq=c1.tick())
    signals1 = await engine1.generate_signals(event1)

    random.seed(0)
    np.random.seed(0)
    engine2 = StrategyEngine(settings, c2)
    await engine2.initialize()
    event2 = MarketEvent(event_id="evt_1", symbol="BTCUSDT", bid=42000.0, ask=42010.0,
                         volume=50.0, volatility=0.02, event_seq=c2.tick())
    signals2 = await engine2.generate_signals(event2)

    if signals1 and signals2:
        assert len(signals1) == len(signals2)
        for s1, s2 in zip(signals1, signals2):
            assert s1.signal_type == s2.signal_type
            assert s1.strength == s2.strength
            assert s1.price == s2.price

    await engine1.shutdown()
    await engine2.shutdown()
