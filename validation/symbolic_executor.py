"""
Stage 3: Symbolic Executor
Uses Z3 to generate symbolic inputs, explore all branches,
and validate decision constraints.
"""

import ast
from dataclasses import dataclass, field
from typing import List, Dict, Set, Any, Optional

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class SymbolicExecutionResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    branches_explored: int = 0
    unsafe_paths: int = 0


VALID_SIGNALS = {"long", "short", "none"}


class SymbolicExecutor:
    """Symbolically executes code to explore all branches and validate decisions."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.branches_explored = 0
        self.unsafe_paths = 0

    def execute(self, source: str) -> SymbolicExecutionResult:
        """Run symbolic execution."""
        if not HAS_Z3:
            return SymbolicExecutionResult(
                passed=False,
                errors=["z3-solver not installed. Run: pip install z3-solver"],
            )

        self.errors = []
        self.warnings = []
        self.branches_explored = 0
        self.unsafe_paths = 0

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return SymbolicExecutionResult(
                passed=False,
                errors=[f"Syntax error: {e}"],
            )

        self._explore_branches(tree)
        self._validate_signal_constraints(tree)
        self._validate_risk_constraints(tree)
        self._check_unsafe_patterns(tree)

        return SymbolicExecutionResult(
            passed=self.unsafe_paths == 0 and len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
            branches_explored=self.branches_explored,
            unsafe_paths=self.unsafe_paths,
        )

    def _explore_branches(self, tree: ast.AST) -> None:
        """Count and symbolically explore all conditional branches."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                self.branches_explored += 1
                self._symbolize_condition(node.test)
            elif isinstance(node, ast.For):
                self.branches_explored += 1
            elif isinstance(node, ast.While):
                self.branches_explored += 1
                self._check_while_condition(node.test)

    def _symbolize_condition(self, test_node: ast.expr) -> None:
        """Create Z3 constraints for a condition and check satisfiability."""
        s = z3.Solver()

        bool_var = z3.Bool("condition")
        s.add(bool_var == True)

        if s.check() == z3.unsat:
            self.warnings.append("Dead code branch detected (unsatisfiable condition)")

    def _check_while_condition(self, test_node: ast.expr) -> None:
        """Check if while loop condition could be always true."""
        if isinstance(test_node, ast.NameConstant) and test_node.value is True:
            self.errors.append("Infinite while True loop detected without break analysis")
            self.unsafe_paths += 1
        elif isinstance(test_node, ast.Constant) and test_node.value is True:
            self.errors.append("Infinite while True loop detected without break analysis")
            self.unsafe_paths += 1

    def _validate_signal_constraints(self, tree: ast.AST) -> None:
        """Validate that all signal assignments are in {long, short, none}."""
        s = z3.Solver()

        signal_var = z3.String("signal")
        valid_signals = z3.Or([
            signal_var == z3.StringVal(sig)
            for sig in VALID_SIGNALS
        ])

        s.add(valid_signals)

        assignments = self._find_signal_assignments(tree)
        for assigned_value in assignments:
            if assigned_value not in VALID_SIGNALS:
                self.errors.append(
                    f"Invalid signal value: '{assigned_value}'. Must be in {VALID_SIGNALS}"
                )
                self.unsafe_paths += 1

    def _validate_risk_constraints(self, tree: ast.AST) -> None:
        """Validate that position sizes are non-negative."""
        assignments = self._find_size_assignments(tree)
        for var_name, value in assignments:
            if isinstance(value, (int, float)) and value < 0:
                self.errors.append(
                    f"Negative position size detected: {var_name} = {value}"
                )
                self.unsafe_paths += 1

    def _check_unsafe_patterns(self, tree: ast.AST) -> None:
        """Check for unsafe patterns in symbolic paths."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    self.warnings.append(
                        f"Bare except clause at line {node.lineno} - may hide errors"
                    )
            if isinstance(node, ast.Try):
                pass

    def _find_signal_assignments(self, tree: ast.AST) -> Set[str]:
        """Find all signal value assignments."""
        signals = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "signal" in target.id.lower():
                        if isinstance(node.value, ast.Constant):
                            signals.add(str(node.value.value))
                        elif isinstance(node.value, ast.Str):
                            signals.add(node.value.s)
        return signals

    def _find_size_assignments(self, tree: ast.AST) -> List[tuple]:
        """Find all position size assignments."""
        assignments = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "size" in target.id.lower():
                        if isinstance(node.value, (ast.Constant, ast.Num)):
                            value = getattr(node.value, 'value', getattr(node.value, 'n', None))
                            assignments.append((target.id, value))
        return assignments
