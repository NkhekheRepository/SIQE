"""
Tests: Learning engine - parameter updates, rollback, stability
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock


@pytest.fixture
def settings():
    s = Settings()
    s.min_sample_size = 50
    s.max_param_change = 0.1
    return s


@pytest.fixture
def clock():
    return EventClock()


@pytest.mark.asyncio
async def test_learning_rejects_insufficient_samples(settings, clock):
    from learning.learning_engine import LearningEngine
    engine = LearningEngine(settings, clock)
    await engine.initialize()

    result = await engine.update_parameters("mean_reversion", {"sample_size": 10})
    assert result["success"] is False
    assert "Insufficient sample size" in result["error"]

    await engine.shutdown()


@pytest.mark.asyncio
async def test_learning_accepts_sufficient_samples(settings, clock):
    from learning.learning_engine import LearningEngine
    engine = LearningEngine(settings, clock)
    await engine.initialize()

    perf = {
        "sample_size": 100,
        "win_rate": 0.52,
        "sharpe_ratio": 0.3,
        "avg_pnl": 0.01,
        "total_trades": 100,
    }

    result = await engine.update_parameters("mean_reversion", perf)
    assert result["success"] is True
    assert "version_id" in result
    assert "new_parameters" in result

    await engine.shutdown()


@pytest.mark.asyncio
async def test_learning_rollback(settings, clock):
    from learning.learning_engine import LearningEngine
    engine = LearningEngine(settings, clock)
    await engine.initialize()

    perf1 = {
        "sample_size": 100, "win_rate": 0.52, "sharpe_ratio": 0.3,
        "avg_pnl": 0.01, "total_trades": 100,
    }
    await engine.update_parameters("mean_reversion", perf1)

    perf2 = {
        "sample_size": 200, "win_rate": 0.55, "sharpe_ratio": 0.4,
        "avg_pnl": 0.015, "total_trades": 200,
    }
    await engine.update_parameters("mean_reversion", perf2)

    result = await engine.rollback_parameters("mean_reversion", steps=1)
    assert result["success"] is True
    assert "rolled_back_to" in result

    await engine.shutdown()


@pytest.mark.asyncio
async def test_learning_rollback_insufficient_history(settings, clock):
    from learning.learning_engine import LearningEngine
    engine = LearningEngine(settings, clock)
    await engine.initialize()

    result = await engine.rollback_parameters("mean_reversion", steps=1)
    assert result["success"] is False
    assert "No version history" in result["error"] or "Insufficient version history" in result["error"]

    await engine.shutdown()


@pytest.mark.asyncio
async def test_learning_history_tracking(settings, clock):
    from learning.learning_engine import LearningEngine
    engine = LearningEngine(settings, clock)
    await engine.initialize()

    perf = {
        "sample_size": 100, "win_rate": 0.52, "sharpe_ratio": 0.3,
        "avg_pnl": 0.01, "total_trades": 100,
    }

    await engine.update_parameters("mean_reversion", perf)
    history = await engine.get_learning_history()

    assert len(history) >= 1
    assert history[0]["strategy_name"] == "mean_reversion"

    await engine.shutdown()
