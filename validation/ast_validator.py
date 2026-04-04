"""
Stage 1: AST Validator
Parses AI-generated Python code and validates:
- Required classes exist (SIQEKernel, MetaHarness, ExecutionAdapter, AsyncEngine)
- Required async method signatures match spec
- No forbidden blocking/network calls
- No non-deterministic calls
"""

import ast
import textwrap
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


@dataclass
class ASTValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# Required classes per strict spec
REQUIRED_CLASSES = {
    "SIQEKernel",
    "MetaHarness",
    "ExecutionAdapter",
    "AsyncEngine",
}

# Required async methods per class
REQUIRED_ASYNC_METHODS: Dict[str, List[Tuple[str, List[str]]]] = {
    "SIQEKernel": [
        ("generate", ["self"]),
        ("batch_score", ["self", "signals"]),
        ("select", ["self", "scored"]),
        ("execute", ["self", "decision"]),
    ],
    "MetaHarness": [
        ("handle_command", ["self", "command"]),
        ("govern", ["self", "state"]),
    ],
    "ExecutionAdapter": [
        ("execute_order", ["self", "order"]),
        ("cancel_order", ["self", "order_id"]),
        ("get_position", ["self", "symbol"]),
    ],
    "AsyncEngine": [
        ("process_event", ["self", "event"]),
        ("start", ["self"]),
        ("stop", ["self"]),
    ],
}

# Forbidden calls (blocking / network / non-deterministic)
FORBIDDEN_CALLS = {
    "time.sleep",
    "time.time",
    "time.monotonic",
    "datetime.now",
    "datetime.today",
    "uuid.uuid4",
    "uuid.uuid1",
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.check_output",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "socket.socket",
    "urllib.request.urlopen",
    "random.random",
    "random.randint",
    "random.choice",
    "random.uniform",
    "random.randrange",
    "random.sample",
    "input",
}

# Forbidden imports
FORBIDDEN_IMPORTS = {
    "socket",
    "requests",
    "urllib",
    "multiprocessing",
    "threading",  # allowed only for Lock, but flagged
    "asyncio.get_event_loop",  # deprecated pattern
}


class ASTValidator:
    """Validates AI-generated Python code against strict spec via AST."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, source: str) -> ASTValidationResult:
        """Run all AST validation checks."""
        self.errors = []
        self.warnings = []

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return ASTValidationResult(
                passed=False,
                errors=[f"Syntax error: {e}"],
            )

        self._check_required_classes(tree)
        self._check_async_method_signatures(tree)
        self._check_forbidden_calls(tree)
        self._check_forbidden_imports(tree)
        self._check_non_deterministic_patterns(tree)

        return ASTValidationResult(
            passed=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
        )

    def _check_required_classes(self, tree: ast.AST) -> None:
        """Verify all required classes are defined."""
        defined_classes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                defined_classes.add(node.name)

        for cls in REQUIRED_CLASSES:
            if cls not in defined_classes:
                self.errors.append(f"Missing required class: {cls}")

    def _check_async_method_signatures(self, tree: ast.AST) -> None:
        """Verify required async methods have correct signatures."""
        class_methods: Dict[str, List[str]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)):
                        args = [arg.arg for arg in item.args.args]
                        methods.append((item.name, args, isinstance(item, ast.AsyncFunctionDef)))
                class_methods[node.name] = methods

        for cls_name, required_methods in REQUIRED_ASYNC_METHODS.items():
            if cls_name not in class_methods:
                continue  # Already caught by _check_required_classes

            actual_methods = {name: (args, is_async) for name, args, is_async in class_methods[cls_name]}

            for method_name, expected_args in required_methods:
                if method_name not in actual_methods:
                    self.errors.append(
                        f"Class {cls_name} missing required method: {method_name}"
                    )
                    continue

                actual_args, is_async = actual_methods[method_name]

                if not is_async:
                    self.errors.append(
                        f"Class {cls_name}.{method_name} must be async"
                    )

                if actual_args != expected_args:
                    self.errors.append(
                        f"Class {cls_name}.{method_name} has wrong signature. "
                        f"Expected ({', '.join(expected_args)}), got ({', '.join(actual_args)})"
                    )

    def _check_forbidden_calls(self, tree: ast.AST) -> None:
        """Detect forbidden blocking/network/non-deterministic calls."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name in FORBIDDEN_CALLS:
                    self.errors.append(
                        f"Forbidden call: {call_name} (line {node.lineno})"
                    )
                elif call_name == "print":
                    self.warnings.append(
                        f"Print call detected (line {node.lineno}) - may affect determinism checks"
                    )

    def _check_forbidden_imports(self, tree: ast.AST) -> None:
        """Detect forbidden imports."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORTS:
                        self.errors.append(
                            f"Forbidden import: {alias.name} (line {node.lineno})"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module in FORBIDDEN_IMPORTS:
                    self.errors.append(
                        f"Forbidden import from: {node.module} (line {node.lineno})"
                    )

    def _check_non_deterministic_patterns(self, tree: ast.AST) -> None:
        """Detect patterns that break determinism."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name and call_name.startswith("random.") and call_name not in {"random.seed"}:
                    self.errors.append(
                        f"Non-deterministic call: {call_name} (line {node.lineno}). "
                        f"Use seeded random only."
                    )

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        """Extract full call name from AST node."""
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
