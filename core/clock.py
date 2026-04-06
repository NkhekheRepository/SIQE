"""
Deterministic Event Clock and ID Generator
Replaces all datetime.now() and uuid.uuid4() usage.
Phase 1: Added RealTimeClock wrapper for wall-clock time awareness.
"""
import time
import asyncio
from datetime import datetime, timezone


class EventClock:
    """Monotonic deterministic event clock. No wall-clock time."""

    def __init__(self):
        self._seq = 0

    def tick(self) -> int:
        self._seq += 1
        return self._seq

    @property
    def now(self) -> int:
        return self._seq

    def reset(self):
        self._seq = 0


class RealTimeClock(EventClock):
    """Wall-clock aware event clock. Supports daily resets and time-aware operations."""

    def __init__(self, daily_reset_hour: int = 0, timezone_name: str = "UTC"):
        super().__init__()
        self._daily_reset_hour = daily_reset_hour
        self._last_reset_date = self._current_date()
        self._on_daily_reset_callbacks = []

    def _current_date(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _current_datetime(self) -> datetime:
        return datetime.now(timezone.utc)

    def tick(self) -> int:
        seq = super().tick()
        self._check_daily_reset()
        return seq

    @property
    def now(self) -> int:
        return self._seq

    @property
    def wall_clock(self) -> datetime:
        return self._current_datetime()

    @property
    def unix_timestamp(self) -> float:
        return time.time()

    def _check_daily_reset(self):
        current_date = self._current_date()
        if current_date != self._last_reset_date:
            self._last_reset_date = current_date
            self._trigger_daily_reset()

    def on_daily_reset(self, callback):
        self._on_daily_reset_callbacks.append(callback)

    def _trigger_daily_reset(self):
        for callback in self._on_daily_reset_callbacks:
            try:
                callback()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Daily reset callback error: {e}")

    def is_new_day(self) -> bool:
        return self._current_date() != self._last_reset_date

    def get_hour_utc(self) -> int:
        return self._current_datetime().hour

    def get_minute_utc(self) -> int:
        return self._current_datetime().minute

    def seconds_since(self, timestamp: float) -> float:
        return time.time() - timestamp


class IDGenerator:
    """Deterministic ID generation from event sequence."""

    def __init__(self, prefix: str, clock: EventClock):
        self.prefix = prefix
        self.clock = clock

    def next(self) -> str:
        seq = self.clock.tick()
        return f"{self.prefix}_{seq}"
