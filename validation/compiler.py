"""
SIQE Validation Compiler - Pipeline Orchestrator
Strict 8-stage pipeline:
  AST Validation -> Formal Verification -> Symbolic Execution -> Property Testing
  -> Docker Sandbox -> Runtime Validation -> Determinism Check -> Concurrency Test
Failure at any stage = immediate FAIL (no partial success).
"""

import sys
import os
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ast_validator import ASTValidator, ASTValidationResult
from formal_validator import FormalValidator, FormalVerificationResult
from symbolic_executor import SymbolicExecutor, SymbolicExecutionResult
from property_tests import PropertyTester, PropertyTestResult
from docker_sandbox import DockerSandbox, DockerSandboxResult
from runtime_validator import RuntimeValidator, RuntimeValidationResult
from determinism_engine import DeterminismEngine, DeterminismResult
from concurrency_test import ConcurrencyTester, ConcurrencyTestResult
from schema_validator import SchemaValidator, SchemaValidationResult
from event_bus_validator import EventBusValidator, EventBusValidationResult
from api_contract_validator import APIContractValidator, APIContractResult


@dataclass
class StageResult:
    name: str
    passed: bool
    duration_ms: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompilationResult:
    passed: bool
    stages: List[StageResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    total_ms: float = 0.0
    verdict: str = "FAIL"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "passed": self.passed,
            "total_duration_ms": self.total_duration_ms,
            "stages": [
                {
                    "name": s.name,
                    "passed": s.passed,
                    "duration_ms": s.duration_ms,
                    "errors": s.errors,
                    "warnings": s.warnings,
                    "details": s.details,
                }
                for s in self.stages
            ],
        }


class ValidationCompiler:
    """Orchestrates the 8-stage validation pipeline."""

    def __init__(self, source_path: Optional[str] = None, source: Optional[str] = None):
        if source:
            self.source = source
        elif source_path:
            with open(source_path, 'r') as f:
                self.source = f.read()
        else:
            raise ValueError("Either source or source_path must be provided")

    def compile(self) -> CompilationResult:
        """Run the full validation pipeline. Strict order, fail-fast."""
        start = time.monotonic()
        stages = []

        pipeline = [
            ("AST Validation", self._stage_ast),
            ("Formal Verification", self._stage_formal),
            ("Symbolic Execution", self._stage_symbolic),
            ("Property Testing", self._stage_properties),
            ("Schema Validation", self._stage_schema),
            ("Event Bus Validation", self._stage_event_bus),
            ("API Contract Validation", self._stage_api_contract),
            ("Docker Sandbox", self._stage_docker),
            ("Runtime Validation", self._stage_runtime),
            ("Determinism Check", self._stage_determinism),
            ("Concurrency Test", self._stage_concurrency),
        ]

        for stage_name, stage_fn in pipeline:
            print(f"[STAGE] {stage_name}...")
            result = stage_fn()
            stages.append(result)

            status = "PASS" if result.passed else "FAIL"
            print(f"  -> {status} ({result.duration_ms:.0f}ms)")

            if result.errors:
                for err in result.errors[:5]:
                    print(f"     ERROR: {err}")
                if len(result.errors) > 5:
                    print(f"     ... and {len(result.errors) - 5} more errors")

            if result.warnings:
                for warn in result.warnings[:3]:
                    print(f"     WARN:  {warn}")

            if not result.passed:
                total_ms = (time.monotonic() - start) * 1000
                return CompilationResult(
                    passed=False,
                    stages=stages,
                    total_duration_ms=total_ms,
                    verdict="FAIL",
                )

        total_ms = (time.monotonic() - start) * 1000
        return CompilationResult(
            passed=True,
            stages=stages,
            total_duration_ms=total_ms,
            verdict="PASS",
        )

    def _stage_ast(self) -> StageResult:
        start = time.monotonic()
        validator = ASTValidator()
        result = validator.validate(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="AST Validation",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
        )

    def _stage_formal(self) -> StageResult:
        start = time.monotonic()
        validator = FormalValidator()
        result = validator.verify(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Formal Verification",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={"proofs": result.proofs},
        )

    def _stage_symbolic(self) -> StageResult:
        start = time.monotonic()
        executor = SymbolicExecutor()
        result = executor.execute(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Symbolic Execution",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={
                "branches_explored": result.branches_explored,
                "unsafe_paths": result.unsafe_paths,
            },
        )

    def _stage_properties(self) -> StageResult:
        start = time.monotonic()
        tester = PropertyTester()
        result = tester.test(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Property Testing",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
            },
        )

    def _stage_schema(self) -> StageResult:
        start = time.monotonic()
        validator = SchemaValidator()
        result = validator.validate(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Schema Validation",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={"schemas_found": result.schemas_found},
        )

    def _stage_event_bus(self) -> StageResult:
        start = time.monotonic()
        validator = EventBusValidator()
        result = validator.validate(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Event Bus Validation",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={"patterns_found": result.patterns_found},
        )

    def _stage_api_contract(self) -> StageResult:
        start = time.monotonic()
        validator = APIContractValidator()
        result = validator.validate(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="API Contract Validation",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={"endpoints_found": result.endpoints_found},
        )

    def _stage_docker(self) -> StageResult:
        start = time.monotonic()
        sandbox = DockerSandbox()
        result = sandbox.execute(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Docker Sandbox",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            details={
                "exit_code": result.exit_code,
                "timeout": result.timeout,
                "execution_time_ms": result.execution_time_ms,
            },
        )

    def _stage_runtime(self) -> StageResult:
        start = time.monotonic()
        validator = RuntimeValidator()
        result = validator.validate(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Runtime Validation",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={"run_count": result.run_count},
        )

    def _stage_determinism(self) -> StageResult:
        start = time.monotonic()
        engine = DeterminismEngine()
        result = engine.check(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Determinism Check",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={
                "run_count": result.run_count,
                "unique_hashes": result.unique_hashes,
                "hashes": result.hashes,
            },
        )

    def _stage_concurrency(self) -> StageResult:
        start = time.monotonic()
        tester = ConcurrencyTester()
        result = tester.test(self.source)
        duration_ms = (time.monotonic() - start) * 1000
        return StageResult(
            name="Concurrency Test",
            passed=result.passed,
            duration_ms=duration_ms,
            errors=result.errors,
            warnings=result.warnings,
            details={
                "total_runs": result.total_runs,
                "passed_runs": result.passed_runs,
                "failed_runs": result.failed_runs,
                "execution_time_ms": result.execution_time_ms,
            },
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python compiler.py <source_file.py>")
        print("       python compiler.py --stdin")
        sys.exit(1)

    if sys.argv[1] == "--stdin":
        source = sys.stdin.read()
        compiler = ValidationCompiler(source=source)
    else:
        source_path = sys.argv[1]
        if not os.path.exists(source_path):
            print(f"Error: File not found: {source_path}")
            sys.exit(1)
        compiler = ValidationCompiler(source_path=source_path)

    result = compiler.compile()

    print(f"\n{'='*60}")
    print(f"VERDICT: {result.verdict}")
    print(f"Total time: {result.total_duration_ms:.0f}ms")
    print(f"Stages passed: {sum(1 for s in result.stages if s.passed)}/{len(result.stages)}")
    print(f"{'='*60}")

    if not result.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
