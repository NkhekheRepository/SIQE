"""
Deterministic Event Clock and ID Generator
Replaces all datetime.now() and uuid.uuid4() usage.
"""


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


class IDGenerator:
    """Deterministic ID generation from event sequence."""

    def __init__(self, prefix: str, clock: EventClock):
        self.prefix = prefix
        self.clock = clock

    def next(self) -> str:
        seq = self.clock.tick()
        return f"{self.prefix}_{seq}"
