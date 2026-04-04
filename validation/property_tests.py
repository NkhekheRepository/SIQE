"""
Stage 4: Property Tests (Hypothesis)
Real property-based testing with @given strategies:
- generate() always returns list[str] with signal in {long, short, none}
- batch_score() always returns list[dict] with size >= 0
- select() never crashes on any valid scored input
- Full pipeline (generate -> batch_score -> select -> execute) never crashes
- Idempotency: running generate() twice produces same result (determinism)
"""

import tempfile
import importlib.util
import sys
import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Any, Callable

try:
    from hypothesis import given, settings, seed, Verbosity, reproduce_failure
    from hypothesis import strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


@dataclass
class PropertyTestResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


VALID_SIGNALS = ("long", "short", "none")
VALID_SIGNALS_SET = set(VALID_SIGNALS)

SIGNAL_STRATEGY = st.lists(st.sampled_from(VALID_SIGNALS), max_size=200)
SIGNAL_STRATEGY_EDGE_CASES = st.one_of(
    st.just([]),
    st.just(["long"]),
    st.just(["short"]),
    st.just(["none"]),
    st.lists(st.sampled_from(VALID_SIGNALS), min_size=50, max_size=50),
    SIGNAL_STRATEGY,
)


class PropertyTester:
    """Runs Hypothesis property tests against AI-generated code."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self._temp_files: List[str] = []

    def test(self, source: str) -> PropertyTestResult:
        """Run all property tests using real Hypothesis strategies."""
        if not HAS_HYPOTHESIS:
            return PropertyTestResult(
                passed=False,
                errors=["hypothesis not installed. Run: pip install hypothesis"],
            )

        self.errors = []
        self.warnings = []
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self._temp_files = []

        module = self._load_module(source)
        if module is None:
            self._cleanup()
            return PropertyTestResult(
                passed=False,
                errors=["Failed to load module from source"],
            )

        if not hasattr(module, 'SIQEKernel'):
            self.errors.append("SIQEKernel class not found")
            self.tests_failed += 1
            self.tests_run += 1
            self._cleanup()
            return PropertyTestResult(
                passed=False,
                errors=self.errors,
                warnings=self.warnings,
                tests_run=self.tests_run,
                tests_passed=self.tests_passed,
                tests_failed=self.tests_failed,
            )

        self._test_generate_returns_list(module)
        self._test_signals_always_valid(module)
        self._test_sizes_always_non_negative(module)
        self._test_select_never_crashes(module)
        self._test_full_pipeline_never_crashes(module)
        self._test_generate_is_deterministic(module)
        self._test_edge_case_inputs(module)

        self._cleanup()

        return PropertyTestResult(
            passed=self.tests_failed == 0 and len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
            tests_run=self.tests_run,
            tests_passed=self.tests_passed,
            tests_failed=self.tests_failed,
        )

    def _cleanup(self):
        """Clean up temp files and module cache."""
        for f in self._temp_files:
            try:
                os.unlink(f)
            except OSError:
                pass
        self._temp_files = []
        sys.modules.pop("test_module", None)

    def _load_module(self, source: str):
        """Dynamically load a module from source string."""
        try:
            fd, path = tempfile.mkstemp(suffix='.py', prefix='siqe_test_')
            self._temp_files.append(path)
            with os.fdopen(fd, 'w') as f:
                f.write(source)

            spec = importlib.util.spec_from_file_location("test_module", path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules["test_module"] = module
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            self.errors.append(f"Module load error: {e}")
            return None

    def _run_async(self, coro):
        """Run an async coroutine synchronously."""
        return asyncio.run(coro)

    def _make_kernel(self, module):
        """Create a fresh SIQEKernel instance."""
        return module.SIQEKernel()

    def _test_generate_returns_list(self, module) -> None:
        """Hypothesis: generate() always returns a list, regardless of prior state."""
        self.tests_run += 1
        test_name = "generate_returns_list"

        @seed(42)
        @settings(max_examples=50, verbosity=Verbosity.quiet)
        @given(st.integers(min_value=0, max_value=1000))
        def test_property(_):
            kernel = self._make_kernel(module)
            result = self._run_async(kernel.generate())
            assert isinstance(result, list), f"Expected list, got {type(result).__name__}"

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_signals_always_valid(self, module) -> None:
        """Hypothesis: every signal in generate() output is in {long, short, none}."""
        self.tests_run += 1
        test_name = "signals_always_valid"

        @seed(42)
        @settings(max_examples=100, verbosity=Verbosity.quiet)
        @given(SIGNAL_STRATEGY_EDGE_CASES)
        def test_property(_signals):
            kernel = self._make_kernel(module)
            signals = self._run_async(kernel.generate())
            assert isinstance(signals, list), "generate() must return a list"
            for s in signals:
                assert isinstance(s, str), f"Signal must be str, got {type(s).__name__}: {s!r}"
                assert s in VALID_SIGNALS_SET, f"Invalid signal: {s!r}. Must be in {VALID_SIGNALS_SET}"

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_sizes_always_non_negative(self, module) -> None:
        """Hypothesis: batch_score() always returns items with size >= 0."""
        self.tests_run += 1
        test_name = "sizes_always_non_negative"

        @seed(42)
        @settings(max_examples=100, verbosity=Verbosity.quiet)
        @given(SIGNAL_STRATEGY)
        def test_property(signals):
            kernel = self._make_kernel(module)
            if not hasattr(kernel, 'batch_score'):
                return
            scored = self._run_async(kernel.batch_score(signals))
            assert isinstance(scored, list), "batch_score() must return a list"
            for item in scored:
                if isinstance(item, dict):
                    size = item.get('size', 0)
                    assert isinstance(size, (int, float)), f"size must be numeric, got {type(size).__name__}"
                    assert size >= 0, f"Negative size: {size}"

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_select_never_crashes(self, module) -> None:
        """Hypothesis: select() never crashes on any input shape."""
        self.tests_run += 1
        test_name = "select_never_crashes"

        scored_strategy = st.lists(
            st.fixed_dictionaries({
                "signal": st.sampled_from(VALID_SIGNALS),
                "score": st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
                "size": st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
            }),
            max_size=50,
        )

        @seed(42)
        @settings(max_examples=100, verbosity=Verbosity.quiet)
        @given(scored_strategy)
        def test_property(scored):
            kernel = self._make_kernel(module)
            if not hasattr(kernel, 'select'):
                return
            result = self._run_async(kernel.select(scored))

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_full_pipeline_never_crashes(self, module) -> None:
        """Hypothesis: full pipeline (generate -> batch_score -> select -> execute) never crashes."""
        self.tests_run += 1
        test_name = "full_pipeline_never_crashes"

        @seed(42)
        @settings(max_examples=50, verbosity=Verbosity.quiet)
        @given(st.integers(min_value=0, max_value=100))
        def test_property(_):
            kernel = self._make_kernel(module)
            signals = self._run_async(kernel.generate())
            assert isinstance(signals, list)

            if hasattr(kernel, 'batch_score') and signals:
                scored = self._run_async(kernel.batch_score(signals))
                assert isinstance(scored, list)

                if hasattr(kernel, 'select') and scored:
                    decision = self._run_async(kernel.select(scored))

                    if hasattr(kernel, 'execute'):
                        result = self._run_async(kernel.execute(decision))

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_generate_is_deterministic(self, module) -> None:
        """Hypothesis: generate() produces identical output across multiple calls."""
        self.tests_run += 1
        test_name = "generate_is_deterministic"

        @seed(42)
        @settings(max_examples=20, verbosity=Verbosity.quiet)
        @given(st.integers(min_value=0, max_value=100))
        def test_property(_):
            kernel = self._make_kernel(module)
            result1 = self._run_async(kernel.generate())
            result2 = self._run_async(kernel.generate())
            assert result1 == result2, f"generate() is non-deterministic: {result1!r} != {result2!r}"

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1

    def _test_edge_case_inputs(self, module) -> None:
        """Hypothesis: code handles pathological inputs gracefully."""
        self.tests_run += 1
        test_name = "edge_case_inputs"

        edge_cases = st.one_of(
            st.just([]),
            st.just(["long"] * 1000),
            st.just(["short"] * 1000),
            st.just(["none"] * 1000),
            st.lists(st.just("long"), min_size=1, max_size=1),
            st.lists(st.just("short"), min_size=1, max_size=1),
            st.lists(st.just("none"), min_size=1, max_size=1),
        )

        @seed(42)
        @settings(max_examples=50, verbosity=Verbosity.quiet)
        @given(edge_cases)
        def test_property(signals):
            kernel = self._make_kernel(module)
            if hasattr(kernel, 'batch_score') and signals:
                scored = self._run_async(kernel.batch_score(signals))
                if hasattr(kernel, 'select') and scored:
                    self._run_async(kernel.select(scored))
            if hasattr(kernel, 'select'):
                self._run_async(kernel.select([]))

        try:
            test_property()
            self.tests_passed += 1
        except Exception as e:
            self.errors.append(f"[{test_name}] {e}")
            self.tests_failed += 1
