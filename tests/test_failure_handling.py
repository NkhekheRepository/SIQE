"""
Tests: Failure handling - timeouts, retries, backpressure, crashes
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings
from core.clock import EventClock
from core.retry import with_retry
from models.trade import MarketEvent


@pytest.fixture
def clock():
    return EventClock()


@pytest.mark.asyncio
async def test_retry_succeeds_after_failure():
    call_count = 0

    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError(f"Transient error {call_count}")
        return "success"

    result = await with_retry(flaky_fn, max_retries=3, base_delay=0.01)
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausts_max_retries():
    call_count = 0

    async def always_fails():
        nonlocal call_count
        call_count += 1
        raise ValueError("Permanent error")

    with pytest.raises(ValueError, match="Permanent error"):
        await with_retry(always_fails, max_retries=2, base_delay=0.01)

    assert call_count == 3


@pytest.mark.asyncio
async def test_event_queue_backpressure():
    queue = asyncio.Queue(maxsize=2)

    await queue.put("event1")
    await queue.put("event2")

    assert queue.full()

    with pytest.raises(asyncio.QueueFull):
        queue.put_nowait("event3")


@pytest.mark.asyncio
async def test_timeout_raises():
    async def slow_fn():
        await asyncio.sleep(10)
        return "done"

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_fn(), timeout=0.1)


@pytest.mark.asyncio
async def test_market_event_validation_missing_fields():
    from models.trade import MarketEvent

    with pytest.raises(ValueError, match="missing fields"):
        MarketEvent.validate({"event_id": "1", "symbol": "BTCUSDT"})


@pytest.mark.asyncio
async def test_market_event_validation_valid():
    from models.trade import MarketEvent

    event = MarketEvent.validate({
        "event_id": "evt_1",
        "symbol": "BTCUSDT",
        "bid": 42000.0,
        "ask": 42010.0,
        "volume": 50.0,
        "volatility": 0.02,
        "event_seq": 1,
    })

    assert event.event_id == "evt_1"
    assert event.symbol == "BTCUSDT"
    assert event.bid == 42000.0
    assert event.mid_price == 42005.0
