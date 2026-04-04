"""
Stage 8: Concurrency Test
Runs >=10 parallel Docker executions, all must pass.
"""

import asyncio
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any

from docker_sandbox import DockerSandbox, DockerSandboxResult


@dataclass
class ConcurrencyTestResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    execution_time_ms: float = 0.0


PARALLEL_RUNS = 10


class ConcurrencyTester:
    """Runs parallel Docker executions to test concurrency."""

    def __init__(self, parallel_runs: int = PARALLEL_RUNS):
        self.parallel_runs = parallel_runs
        self.sandbox = DockerSandbox()

    def test(self, source: str) -> ConcurrencyTestResult:
        """Run parallel Docker executions."""
        errors = []
        warnings = []
        passed = 0
        failed = 0

        wrapper = (
            "import random\n"
            "random.seed(0)\n"
            f"{source}\n"
            'print("SYSTEM_OK")\n'
        )

        start = time.monotonic()

        async def run_single(idx: int) -> DockerSandboxResult:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.sandbox.execute, wrapper
            )

        async def run_all():
            tasks = [run_single(i) for i in range(self.parallel_runs)]
            return await asyncio.gather(*tasks, return_exceptions=True)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(run_all())
            loop.close()
        except Exception as e:
            return ConcurrencyTestResult(
                passed=False,
                errors=[f"Concurrency test failed: {e}"],
                total_runs=0,
                passed_runs=0,
                failed_runs=0,
            )

        elapsed_ms = (time.monotonic() - start) * 1000

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"Run {i + 1} raised exception: {result}")
                failed += 1
            elif result.exit_code != 0:
                errors.append(f"Run {i + 1} exited with code {result.exit_code}")
                failed += 1
            elif "SYSTEM_OK" not in result.stdout:
                errors.append(f"Run {i + 1} missing SYSTEM_OK in stdout")
                failed += 1
            else:
                passed += 1

        return ConcurrencyTestResult(
            passed=failed == 0,
            errors=errors,
            warnings=warnings,
            total_runs=self.parallel_runs,
            passed_runs=passed,
            failed_runs=failed,
            execution_time_ms=elapsed_ms,
        )
