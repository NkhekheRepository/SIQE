"""
Sample AI-generated code that FAILS validation.
Contains forbidden calls, missing classes, non-deterministic patterns.
"""

import time
import random
import os


class BadKernel:
    """Missing required class name (should be SIQEKernel)."""

    def generate(self):
        """Not async, uses time.time()."""
        t = time.time()
        return random.choice(["long", "short", "invalid_signal"])

    def batch_score(self, signals):
        """Not async, uses random without seed."""
        return [{"signal": s, "score": random.random(), "size": -1} for s in signals]


class ExecutionAdapter:
    """Missing required methods."""

    def execute_order(self, order):
        """Not async, uses os.system (forbidden)."""
        os.system("echo hello")
        return {"status": "ok"}


class AsyncEngine:
    """Missing required methods."""

    def process_event(self, event):
        """Not async."""
        return {"processed": True}

    def start(self):
        """Not async."""
        pass

    def stop(self):
        """Not async."""
        pass
