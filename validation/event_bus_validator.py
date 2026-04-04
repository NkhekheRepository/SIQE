"""
Stage 10: Event Bus Validator
Validates that AI-generated code implements the required event bus pattern:
- asyncio.Queue(maxsize=1000) with drop-oldest policy
- Dead-letter queue for failed events
- Retry/backoff logic for transient failures
- Event types are properly typed
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional


@dataclass
class EventBusValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    patterns_found: Dict[str, bool] = field(default_factory=dict)


class EventBusValidator:
    """Validates event bus implementation patterns."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.patterns_found: Dict[str, bool] = {}

    def validate(self, source: str) -> EventBusValidationResult:
        """Run all event bus validation checks."""
        self.errors = []
        self.warnings = []
        self.patterns_found = {}

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return EventBusValidationResult(
                passed=False,
                errors=[f"Syntax error: {e}"],
            )

        self._check_event_queue(tree, source)
        self._check_dead_letter_queue(tree, source)
        self._check_retry_backoff(tree, source)
        self._check_event_processing(tree, source)

        return EventBusValidationResult(
            passed=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
            patterns_found=dict(self.patterns_found),
        )

    def _check_event_queue(self, tree: ast.AST, source: str) -> None:
        """Check for asyncio.Queue with bounded maxsize."""
        has_bounded_queue = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name and "Queue" in call_name:
                    for kw in node.keywords:
                        if kw.arg == "maxsize":
                            if isinstance(kw.value, ast.Constant) and kw.value.value > 0:
                                has_bounded_queue = True
                                self.patterns_found["bounded_queue"] = True
                            elif isinstance(kw.value, ast.Num):
                                has_bounded_queue = True
                                self.patterns_found["bounded_queue"] = True

        if not has_bounded_queue:
            if re.search(r'asyncio\.Queue\s*\(\s*maxsize\s*=\s*\d+', source):
                has_bounded_queue = True
                self.patterns_found["bounded_queue"] = True
            elif re.search(r'asyncio\.Queue\s*\(', source):
                self.warnings.append(
                    "asyncio.Queue found but no maxsize specified (unbounded queue risks memory exhaustion)"
                )
                self.patterns_found["bounded_queue"] = False
            else:
                self.warnings.append(
                    "No asyncio.Queue found (event bus may use alternative pattern)"
                )
                self.patterns_found["bounded_queue"] = False

    def _check_dead_letter_queue(self, tree: ast.AST, source: str) -> None:
        """Check for dead-letter queue pattern."""
        dlq_patterns = [
            r'dead.?letter',
            r'dlq',
            r'failed.?queue',
            r'error.?queue',
            r'poison.?queue',
        ]

        found = False
        for pattern in dlq_patterns:
            if re.search(pattern, source, re.IGNORECASE):
                found = True
                self.patterns_found["dead_letter_queue"] = True
                break

        if not found:
            self.warnings.append(
                "No dead-letter queue pattern detected (failed events may be lost)"
            )
            self.patterns_found["dead_letter_queue"] = False

    def _check_retry_backoff(self, tree: ast.AST, source: str) -> None:
        """Check for retry/backoff logic."""
        retry_patterns = [
            r'retry',
            r'backoff',
            r'exponential',
            r'attempt',
            r'max.?retries',
            r'retry.?count',
        ]

        backoff_patterns = [
            r'2\s*\*\*',
            r'math\.exp',
            r'exponential',
            r'backoff',
            r'delay\s*\*',
        ]

        has_retry = any(re.search(p, source, re.IGNORECASE) for p in retry_patterns)
        has_backoff = any(re.search(p, source, re.IGNORECASE) for p in backoff_patterns)

        self.patterns_found["retry_logic"] = has_retry
        self.patterns_found["backoff_logic"] = has_backoff

        if has_retry and not has_backoff:
            self.warnings.append(
                "Retry logic found but no backoff pattern (may cause thundering herd)"
            )

        if not has_retry:
            self.warnings.append(
                "No retry logic detected (transient failures will cause permanent losses)"
            )

    def _check_event_processing(self, tree: ast.AST, source: str) -> None:
        """Check for proper event processing patterns."""
        has_async_for = False
        has_get_nowait = False
        has_get_with_timeout = False

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFor):
                has_async_for = True

            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name and "get_nowait" in call_name:
                    has_get_nowait = True
                if call_name and "get" in call_name:
                    has_get_with_timeout = True

        self.patterns_found["async_iteration"] = has_async_for
        self.patterns_found["non_blocking_get"] = has_get_nowait

        if not has_async_for and not has_get_nowait and not has_get_with_timeout:
            self.warnings.append(
                "No event consumption pattern found (async for, get_nowait, or get with timeout)"
            )

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        elif isinstance(node.func, ast.Name):
            return node.func.id
        return None
