"""
Stage 11: API Contract Validator
Validates that AI-generated code exposes only the 4 allowed endpoints:
- /health
- /meta/status
- /halt
- /resume
All must be routed exclusively through meta_harness.handle_command().
No direct module calls from API endpoints.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional


@dataclass
class APIContractResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    endpoints_found: List[str] = field(default_factory=list)


ALLOWED_ENDPOINTS = {"/health", "/meta/status", "/halt", "/resume"}
ALLOWED_COMMANDS = {"health", "status", "halt", "resume"}


class APIContractValidator:
    """Validates API contract compliance."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.endpoints_found: List[str] = []

    def validate(self, source: str) -> APIContractResult:
        """Run API contract validation."""
        self.errors = []
        self.warnings = []
        self.endpoints_found = []

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return APIContractResult(
                passed=False,
                errors=[f"Syntax error: {e}"],
            )

        self._check_endpoints(tree, source)
        self._check_routing(source)
        self._check_no_direct_module_calls(tree, source)

        return APIContractResult(
            passed=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
            endpoints_found=list(self.endpoints_found),
        )

    def _check_endpoints(self, tree: ast.AST, source: str) -> None:
        """Check that only allowed endpoints are defined."""
        route_patterns = [
            r'@[a-z_]*\.route\s*\(\s*["\'](/[^"\']+)["\']',
            r'@[a-z_]*\.(get|post|put|delete)\s*\(\s*["\'](/[^"\']+)["\']',
            r'["\'](/[^"\']+)["\'].*:\s*(handler|endpoint|view)',
        ]

        found_endpoints = set()

        for pattern in route_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    endpoint = match[-1]
                else:
                    endpoint = match
                found_endpoints.add(endpoint)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        for arg in decorator.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                if arg.value.startswith('/'):
                                    found_endpoints.add(arg.value)

        self.endpoints_found = list(found_endpoints)

        unauthorized = found_endpoints - ALLOWED_ENDPOINTS
        if unauthorized:
            self.errors.append(
                f"Unauthorized endpoints found: {', '.join(sorted(unauthorized))}. "
                f"Only allowed: {', '.join(sorted(ALLOWED_ENDPOINTS))}"
            )

    def _check_routing(self, source: str) -> None:
        """Check that endpoints route through meta_harness.handle_command()."""
        if not self.endpoints_found:
            self.warnings.append("No API endpoints detected (may be intentional)")
            return

        has_handle_command = 'handle_command' in source
        has_meta_harness = 'meta_harness' in source or 'MetaHarness' in source

        if self.endpoints_found and not has_handle_command:
            self.errors.append(
                "Endpoints defined but no handle_command() method found. "
                "All endpoints must route through meta_harness.handle_command()"
            )

    def _check_no_direct_module_calls(self, tree: ast.AST, source: str) -> None:
        """Check that API endpoints don't call modules directly."""
        direct_call_patterns = [
            r'(risk_engine|risk_manager)\.(approve|check|calculate)',
            r'(decision_engine|decision_maker)\.(decide|make_decision)',
            r'(strategy_engine|strategy)\.(generate|create_signal)',
            r'(execution_adapter|executor)\.(execute|place_order)',
            r'(ev_engine)\.(calculate|compute)',
        ]

        for pattern in direct_call_patterns:
            matches = re.findall(pattern, source)
            if matches:
                self.warnings.append(
                    f"Possible direct module call pattern: {pattern}. "
                    f"Modules should be accessed through the kernel pipeline, not directly from API."
                )
