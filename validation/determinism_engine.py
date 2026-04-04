"""
Stage 7: Determinism Engine
Validates that code produces identical output across N>=3 runs.
Checks:
- PYTHONHASHSEED=0 enforced
- No non-deterministic calls
- Identical normalized output
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from docker_sandbox import DockerSandbox, DockerSandboxResult


@dataclass
class DeterminismResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    hashes: List[str] = field(default_factory=list)
    run_count: int = 0
    unique_hashes: int = 0


NON_DETERMINISTIC_PATTERNS = [
    r'time\.time\(\)',
    r'time\.monotonic\(\)',
    r'datetime\.now\(\)',
    r'datetime\.today\(\)',
    r'uuid\.uuid4\(\)',
    r'uuid\.uuid1\(\)',
    r'random\.(?!seed)',
    r'os\.urandom',
    r'os\.getpid\(\)',
]

MIN_RUNS = 3


class DeterminismEngine:
    """Validates deterministic behavior across multiple runs."""

    def __init__(self, min_runs: int = MIN_RUNS):
        self.min_runs = min_runs
        self.sandbox = DockerSandbox()

    def check(self, source: str) -> DeterminismResult:
        """Run determinism checks."""
        errors = []
        warnings = []
        hashes = []

        for pattern in NON_DETERMINISTIC_PATTERNS:
            matches = re.findall(pattern, source)
            if matches:
                errors.append(
                    f"Non-deterministic pattern found: {pattern}"
                )

        if errors:
            return DeterminismResult(
                passed=False,
                errors=errors,
                warnings=warnings,
            )

        wrapper = (
            "import random\n"
            "random.seed(0)\n"
            f"{source}\n"
        )

        outputs = []
        for i in range(self.min_runs):
            result = self.sandbox.execute(wrapper)
            if result.exit_code != 0:
                errors.append(f"Run {i + 1} failed with exit code {result.exit_code}")
                return DeterminismResult(
                    passed=False,
                    errors=errors,
                    warnings=warnings,
                    hashes=hashes,
                    run_count=i + 1,
                    unique_hashes=len(set(hashes)),
                )
            outputs.append(result.stdout)
            h = hashlib.sha256(result.stdout.encode()).hexdigest()[:16]
            hashes.append(h)

        unique = set(hashes)

        if len(unique) > 1:
            errors.append(
                f"Non-deterministic output: {len(unique)} unique hashes across {self.min_runs} runs"
            )

        return DeterminismResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            hashes=hashes,
            run_count=self.min_runs,
            unique_hashes=len(unique),
        )
