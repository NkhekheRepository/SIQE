"""
Stage 6: Runtime Validator
Executes code N>=3 times in Docker, requires:
- "SYSTEM_OK" in stdout
- Zero stderr
- Identical normalized output across all runs
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from docker_sandbox import DockerSandbox, DockerSandboxResult


@dataclass
class RuntimeValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    runs: List[dict] = field(default_factory=list)
    run_count: int = 0


REQUIRED_OUTPUT = "SYSTEM_OK"
MIN_RUNS = 3


class RuntimeValidator:
    """Validates runtime behavior across multiple executions."""

    def __init__(self, min_runs: int = MIN_RUNS):
        self.min_runs = min_runs
        self.sandbox = DockerSandbox()

    def validate(self, source: str) -> RuntimeValidationResult:
        """Run code N times and validate consistency."""
        errors = []
        warnings = []
        runs = []

        wrapper = self._build_wrapper(source)

        for i in range(self.min_runs):
            result = self.sandbox.execute(wrapper)
            run_info = {
                "run": i + 1,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timeout": result.timeout,
                "execution_time_ms": result.execution_time_ms,
            }
            runs.append(run_info)

            if result.timeout:
                errors.append(f"Run {i + 1} timed out")
            elif result.exit_code != 0:
                errors.append(f"Run {i + 1} exited with code {result.exit_code}")

            if result.stderr.strip():
                errors.append(f"Run {i + 1} produced stderr: {result.stderr.strip()[:200]}")

            if REQUIRED_OUTPUT not in result.stdout:
                errors.append(
                    f"Run {i + 1} missing '{REQUIRED_OUTPUT}' in stdout"
                )

        normalized_outputs = [
            self._normalize(r["stdout"]) for r in runs
        ]

        if len(set(normalized_outputs)) > 1:
            errors.append("Non-deterministic output detected across runs")

        return RuntimeValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            runs=runs,
            run_count=len(runs),
        )

    def _build_wrapper(self, source: str) -> str:
        """Wrap source with deterministic seed and SYSTEM_OK print."""
        return (
            "import random\n"
            "random.seed(0)\n"
            f"{source}\n"
            'print("SYSTEM_OK")\n'
        )

    @staticmethod
    def _normalize(output: str) -> str:
        """Normalize output for comparison."""
        output = re.sub(r'\s+', ' ', output.strip())
        output = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', output)
        return output
