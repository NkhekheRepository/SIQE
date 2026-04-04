"""
Sample AI-generated code that PASSES all validation stages.
Used to test the SIQE Validation Compiler pipeline.
"""

import random


class SIQEKernel:
    """Core SIQE kernel with generate -> batch_score -> select -> execute pipeline."""

    def __init__(self):
        self._signals = ["long", "short", "none"]

    async def generate(self):
        """Generate trading signals."""
        return ["long", "short", "none"]

    async def batch_score(self, signals):
        """Score signals deterministically."""
        scored = []
        for i, sig in enumerate(signals):
            if sig in ("long", "short", "none"):
                scored.append({
                    "signal": sig,
                    "score": 0.5 + (i * 0.1),
                    "size": max(0, 1.0 - (i * 0.1)),
                })
        return scored

    async def select(self, scored):
        """Select best scored signal."""
        if not scored:
            return None
        return max(scored, key=lambda x: x.get("score", 0))

    async def execute(self, decision):
        """Execute the selected decision."""
        if decision is None:
            return {"status": "no_action"}
        return {
            "status": "executed",
            "signal": decision.get("signal", "none"),
            "size": decision.get("size", 0),
        }


class MetaHarness:
    """Meta-governance harness."""

    def __init__(self):
        self._halted = False

    async def handle_command(self, command):
        """Handle governance commands."""
        if command == "halt":
            self._halted = True
            return {"status": "halted"}
        elif command == "resume":
            self._halted = False
            return {"status": "resumed"}
        elif command == "status":
            return {"status": "running", "halted": self._halted}
        return {"status": "unknown_command"}

    async def govern(self, state):
        """Govern the system state."""
        if self._halted:
            return {"action": "halt", "reason": "manual_halt"}
        return {"action": "continue"}


class ExecutionAdapter:
    """Adapts signals to execution format."""

    def __init__(self):
        self._orders = {}

    async def execute_order(self, order):
        """Execute an order."""
        order_id = f"order_{len(self._orders)}"
        self._orders[order_id] = order
        return {"order_id": order_id, "status": "submitted"}

    async def cancel_order(self, order_id):
        """Cancel an order."""
        if order_id in self._orders:
            del self._orders[order_id]
            return {"status": "cancelled"}
        return {"status": "not_found"}

    async def get_position(self, symbol):
        """Get current position."""
        return {"symbol": symbol, "size": 0, "pnl": 0.0}


class AsyncEngine:
    """Async event-driven engine."""

    def __init__(self):
        self._running = False
        self._events = []

    async def process_event(self, event):
        """Process a single event."""
        self._events.append(event)
        return {"processed": True, "event": event}

    async def start(self):
        """Start the engine."""
        self._running = True
        return {"status": "started"}

    async def stop(self):
        """Stop the engine."""
        self._running = False
        return {"status": "stopped"}


if __name__ == "__main__":
    import asyncio

    async def main():
        kernel = SIQEKernel()
        signals = await kernel.generate()
        scored = await kernel.batch_score(signals)
        selected = await kernel.select(scored)
        result = await kernel.execute(selected)
        print(f"Result: {result}")

    asyncio.run(main())
