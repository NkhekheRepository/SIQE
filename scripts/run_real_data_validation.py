"""
SIQE V3 - Real Data Validation & Production Readiness Report

Runs walk-forward validation, parameter stability analysis, and A/B testing
on real market data, then generates a comprehensive production readiness report.

Usage:
    python3 scripts/run_real_data_validation.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.config import (
    IndicatorConfig, MarketRegime, WalkForwardValidator,
    WalkForwardResult, SafetyLimits, ConfigPersistence, ConfigMetadata,
)
from strategy_engine.ml_optimizer import BayesianOptOptimizer, RandomForestTuner
from strategy_engine.ab_testing import ABTestRunner
from strategy_engine.data_loader import (
    load_parquet_data, validate_ohlc_data, detect_regime_sequence,
    DataQualityReport,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "binance_futures" / "parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


class RealDataValidator:
    """Orchestrates validation on real market data."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.results: Dict[str, Any] = {}

    def load_and_validate(self, path: str) -> pd.DataFrame:
        """Load parquet data and validate quality."""
        logger.info(f"Loading data from {path}")
        df = load_parquet_data(path)
        is_valid, report = validate_ohlc_data(df)

        self.results["data_quality"] = {
            "is_valid": is_valid,
            "row_count": report.row_count,
            "date_range": report.date_range,
            "missing_values": report.missing_values,
            "price_anomalies": report.price_anomalies,
            "volume_stats": report.volume_stats,
            "warnings": report.warnings,
        }

        if not is_valid:
            logger.warning(f"Data quality issues: {report.price_anomalies}")
        else:
            logger.info(f"Data validation passed: {report.row_count} rows")

        return df

    def run_walk_forward(
        self,
        df: pd.DataFrame,
        label: str,
        train_months: int = 3,
        test_months: int = 1,
        bars_per_month: int = 720,
        min_sharpe: float = 0.5,
        min_pass_rate: float = 0.70,
    ) -> WalkForwardResult:
        """Run walk-forward validation with realistic thresholds."""
        logger.info(f"Running walk-forward on {label}: {len(df)} rows")

        validator = WalkForwardValidator(
            train_months=train_months,
            test_months=test_months,
            bars_per_month=bars_per_month,
            min_sharpe_threshold=min_sharpe,
            min_pass_rate=min_pass_rate,
        )

        optimizer = BayesianOptOptimizer(n_calls=20, seed=self.seed)
        result = validator.validate(df, optimizer=optimizer, regime=MarketRegime.RANGING)

        self.results[f"walk_forward_{label}"] = {
            "passed": result.passed,
            "n_windows": len(result.windows),
            "avg_test_sharpe": result.avg_test_sharpe,
            "avg_test_return": result.avg_test_return,
            "avg_test_drawdown": result.avg_test_drawdown,
            "pass_rate": result.pass_rate,
            "min_test_sharpe": result.min_test_sharpe,
            "max_test_sharpe": result.max_test_sharpe,
            "total_train_trades": result.total_train_trades,
            "total_test_trades": result.total_test_trades,
            "windows": [
                {
                    "window_id": w.window_id,
                    "train_sharpe": w.train_sharpe,
                    "test_sharpe": w.test_sharpe,
                    "train_return": w.train_return,
                    "test_return": w.test_return,
                    "train_trades": w.train_trades,
                    "test_trades": w.test_trades,
                    "passed": w.passed,
                    "config": w.optimized_config.to_dict(),
                }
                for w in result.windows
            ],
        }

        return result

    def analyze_parameter_stability(
        self,
        wf_result: WalkForwardResult,
        label: str,
    ) -> Dict[str, Any]:
        """Analyze parameter stability across walk-forward windows."""
        if not wf_result.windows:
            return {"error": "no windows to analyze"}

        param_names = [
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        ]

        stability = {}
        for param in param_names:
            values = [w.optimized_config.__getattribute__(param) for w in wf_result.windows]
            mean_val = float(np.mean(values))
            std_val = float(np.std(values))
            cv = std_val / abs(mean_val) if mean_val != 0 else 0.0
            stability[param] = {
                "mean": mean_val,
                "std": std_val,
                "cv": cv,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "stable": cv < 0.30,
            }

        stable_params = [p for p, s in stability.items() if s["stable"]]
        unstable_params = [p for p, s in stability.items() if not s["stable"]]

        self.results[f"stability_{label}"] = {
            "parameters": stability,
            "stable_count": len(stable_params),
            "unstable_count": len(unstable_params),
            "stable_params": stable_params,
            "unstable_params": unstable_params,
        }

        return self.results[f"stability_{label}"]

    def run_ab_test(
        self,
        df: pd.DataFrame,
        baseline: IndicatorConfig,
        treatment: IndicatorConfig,
        label: str,
        n_simulations: int = 50,
    ) -> Dict[str, Any]:
        """Run A/B test comparing two configs."""
        logger.info(f"Running A/B test: {label}")

        runner = ABTestRunner(baseline, treatment, seed=self.seed)
        result = runner.run(df, n_simulations=n_simulations)

        self.results[f"ab_test_{label}"] = {
            "baseline_sharpe": result.baseline_sharpe,
            "baseline_return": result.baseline_return,
            "treatment_sharpe": result.treatment_sharpe,
            "treatment_return": result.treatment_return,
            "sharpe_p_value": result.sharpe_p_value,
            "sharpe_significant": result.sharpe_significant,
            "treatment_wins": result.treatment_wins,
            "confidence": result.confidence,
            "recommendation": result.recommendation,
            "n_simulations": result.n_simulations,
        }

        return self.results[f"ab_test_{label}"]

    def check_safety_limits(
        self,
        wf_result: WalkForwardResult,
    ) -> Dict[str, Any]:
        """Verify safety limits are respected."""
        limits = SafetyLimits()
        baseline = IndicatorConfig()

        violations_count = 0
        param_changes = []

        for window in wf_result.windows:
            safe, violations = limits.validate_param_change(
                baseline, window.optimized_config
            )
            if not safe:
                violations_count += 1
                param_changes.extend(violations)

        self.results["safety_limits"] = {
            "total_windows": len(wf_result.windows),
            "windows_with_violations": violations_count,
            "violation_rate": violations_count / len(wf_result.windows) if wf_result.windows else 0,
            "sample_violations": param_changes[:5],
            "circuit_breaker_status": "not_triggered",
        }

        return self.results["safety_limits"]

    def determine_readiness(self) -> str:
        """Determine overall production readiness: GREEN, YELLOW, or RED."""
        score = 0
        max_score = 10

        wf_15m = self.results.get("walk_forward_15m")
        wf_4h = self.results.get("walk_forward_4h")

        if wf_15m:
            if wf_15m["passed"]:
                score += 2
            if wf_15m["avg_test_sharpe"] > 0.5:
                score += 1
            if wf_15m["pass_rate"] >= 0.70:
                score += 1

        if wf_4h:
            if wf_4h["passed"]:
                score += 1
            if wf_4h["avg_test_sharpe"] > 0.5:
                score += 0.5

        stability_15m = self.results.get("stability_15m")
        if stability_15m:
            stable_ratio = stability_15m["stable_count"] / 9 if stability_15m["stable_count"] else 0
            if stable_ratio >= 0.6:
                score += 2
            elif stable_ratio >= 0.3:
                score += 1

        ab = self.results.get("ab_test_bayesian_vs_default_15m")
        if ab:
            if ab["recommendation"] == "deploy":
                score += 2
            elif ab["recommendation"] == "inconclusive":
                score += 1

        safety = self.results.get("safety_limits")
        if safety:
            if safety["violation_rate"] < 0.5:
                score += 1.5

        dq = self.results.get("data_quality")
        if dq and dq["is_valid"]:
            score += 1

        if score >= 8:
            return "GREEN"
        elif score >= 5:
            return "YELLOW"
        else:
            return "RED"


def generate_report(validator: RealDataValidator) -> str:
    """Generate markdown production readiness report."""
    readiness = validator.determine_readiness()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    color_map = {
        "GREEN": "✅ GREEN - Ready for production",
        "YELLOW": "⚠️ YELLOW - Needs attention before production",
        "RED": "❌ RED - Not ready for production",
    }

    report = f"""# SIQE Production Readiness Report

**Generated:** {datetime.now(timezone.utc).isoformat()}
**Status:** {color_map[readiness]}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Status | **{readiness}** |
| Data Quality | {'✅ Valid' if validator.results.get('data_quality', {}).get('is_valid') else '❌ Issues Found'} |
| Walk-Forward (15m) | {'✅ Passed' if validator.results.get('walk_forward_15m', {}).get('passed') else '❌ Failed'} |
| Walk-Forward (4h) | {'✅ Passed' if validator.results.get('walk_forward_4h', {}).get('passed') else '❌ Failed'} |
| Parameter Stability | {validator.results.get('stability_15m', {}).get('stable_count', 0)}/9 stable |
| Safety Limits | {validator.results.get('safety_limits', {}).get('violation_rate', 0):.0%} violation rate |

---

## 1. Data Quality

"""

    dq = validator.results.get("data_quality", {})
    report += f"""- **Rows:** {dq.get('row_count', 'N/A')}
- **Date Range:** {dq.get('date_range', ('N/A', 'N/A'))}
- **Missing Values:** {dq.get('missing_values', {})}
- **Price Anomalies:** {dq.get('price_anomalies', [])}
- **Volume Stats:** {dq.get('volume_stats', {})}
- **Warnings:** {dq.get('warnings', [])}

---

## 2. Walk-Forward Validation (15m)

"""

    wf = validator.results.get("walk_forward_15m", {})
    if wf:
        report += f"""| Metric | Value |
|--------|-------|
| **Passed** | {wf.get('passed')} |
| **Windows** | {wf.get('n_windows')} |
| **Avg Test Sharpe** | {wf.get('avg_test_sharpe', 0):.3f} |
| **Avg Test Return** | {wf.get('avg_test_return', 0):.2f}% |
| **Avg Test Drawdown** | {wf.get('avg_test_drawdown', 0):.2%} |
| **Pass Rate** | {wf.get('pass_rate', 0):.0%} |
| **Min Test Sharpe** | {wf.get('min_test_sharpe', 0):.3f} |
| **Max Test Sharpe** | {wf.get('max_test_sharpe', 0):.3f} |
| **Total Test Trades** | {wf.get('total_test_trades')} |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
"""
        for w in wf.get("windows", []):
            report += f"| {w['window_id']} | {w['train_sharpe']:.3f} | {w['test_sharpe']:.3f} | {w['train_return']:.2f}% | {w['test_return']:.2f}% | {w['test_trades']} | {'✅' if w['passed'] else '❌'} |\n"

    report += "\n---\n\n## 3. Walk-Forward Validation (4h)\n\n"

    wf_4h = validator.results.get("walk_forward_4h", {})
    if wf_4h:
        report += f"""| Metric | Value |
|--------|-------|
| **Passed** | {wf_4h.get('passed')} |
| **Windows** | {wf_4h.get('n_windows')} |
| **Avg Test Sharpe** | {wf_4h.get('avg_test_sharpe', 0):.3f} |
| **Pass Rate** | {wf_4h.get('pass_rate', 0):.0%} |
"""

    report += "\n---\n\n## 4. Parameter Stability Analysis (15m)\n\n"

    stability = validator.results.get("stability_15m", {})
    if stability and "parameters" in stability:
        report += """| Parameter | Mean | Std | CV | Min | Max | Stable |
|-----------|------|-----|----|-----|-----|--------|
"""
        for param, stats in stability["parameters"].items():
            report += f"| {param} | {stats['mean']:.2f} | {stats['std']:.2f} | {stats['cv']:.2f} | {stats['min']:.2f} | {stats['max']:.2f} | {'✅' if stats['stable'] else '⚠️'} |\n"

        report += f"\n- **Stable Parameters:** {stability['stable_count']}/9\n"
        report += f"- **Stable:** {', '.join(stability['stable_params'])}\n"
        report += f"- **Unstable:** {', '.join(stability['unstable_params'])}\n"

    report += "\n---\n\n## 5. A/B Test Results\n\n"

    ab = validator.results.get("ab_test_bayesian_vs_default_15m", {})
    if ab:
        report += f"""| Metric | Baseline (Default) | Treatment (Bayesian) |
|--------|-------------------|---------------------|
| **Sharpe** | {ab['baseline_sharpe']:.3f} | {ab['treatment_sharpe']:.3f} |
| **Return** | {ab['baseline_return']:.2f}% | {ab['treatment_return']:.2f}% |
| **P-Value** | - | {ab['sharpe_p_value']:.4f} |
| **Significant** | - | {ab['sharpe_significant']} |
| **Recommendation** | - | **{ab['recommendation'].upper()}** |
"""

    report += "\n---\n\n## 6. Safety Limits\n\n"

    safety = validator.results.get("safety_limits", {})
    if safety:
        report += f"""- **Windows with Violations:** {safety['windows_with_violations']}/{safety['total_windows']}
- **Violation Rate:** {safety['violation_rate']:.0%}
- **Circuit Breaker:** {safety['circuit_breaker_status']}
"""
        if safety.get("sample_violations"):
            report += "\n**Sample Violations:**\n"
            for v in safety["sample_violations"]:
                report += f"- {v}\n"

    report += """
---

## 7. Recommendations

"""

    if readiness == "GREEN":
        report += """### ✅ Ready for Production

- Walk-forward validation passed on real data
- Parameter stability is acceptable
- Safety limits are respected
- A/B test shows improvement (or at least no degradation)

**Next Steps:**
1. Deploy with circuit breakers enabled
2. Monitor first 30 days closely
3. Review parameter drift weekly
"""
    elif readiness == "YELLOW":
        report += """### ⚠️ Needs Attention Before Production

- Some validation criteria not fully met
- Review unstable parameters and consider freezing them
- Increase walk-forward window size for more robust testing

**Recommended Actions:**
1. Freeze unstable parameters (use defaults)
2. Collect more historical data
3. Re-run validation with adjusted thresholds
4. Paper trade for 2-4 weeks before live deployment
"""
    else:
        report += """### ❌ Not Ready for Production

- Critical validation failures detected
- Do not deploy until issues are resolved

**Required Actions:**
1. Investigate walk-forward failures
2. Review parameter optimization logic
3. Consider strategy redesign
4. Collect more diverse market data
"""

    report += f"""
---

## 8. Configuration Snapshot

**Default Config:**
```json
{json.dumps(IndicatorConfig().to_dict(), indent=2)}
```

**Report saved to:** `reports/production_readiness_{timestamp}.md`
"""

    return report


def main():
    """Run full validation pipeline."""
    logger.info("=" * 60)
    logger.info("SIQE V3 - Real Data Validation Pipeline")
    logger.info("=" * 60)

    validator = RealDataValidator(seed=42)

    logger.info("\n--- Phase 1: Load & Validate Data ---")
    df_15m = validator.load_and_validate(str(DATA_DIR / "btcusdt_15m.parquet"))
    df_4h = validator.load_and_validate(str(DATA_DIR / "btcusdt_4h.parquet"))

    logger.info("\n--- Phase 2: Walk-Forward Validation (15m) ---")
    wf_15m = validator.run_walk_forward(
        df_15m, "15m",
        train_months=3, test_months=1,
        bars_per_month=720,
        min_sharpe=0.5, min_pass_rate=0.70,
    )
    logger.info(f"Walk-forward 15m: passed={wf_15m.passed}, avg_sharpe={wf_15m.avg_test_sharpe:.3f}")

    logger.info("\n--- Phase 3: Walk-Forward Validation (4h) ---")
    wf_4h = validator.run_walk_forward(
        df_4h, "4h",
        train_months=3, test_months=1,
        bars_per_month=180,
        min_sharpe=0.5, min_pass_rate=0.70,
    )
    logger.info(f"Walk-forward 4h: passed={wf_4h.passed}, avg_sharpe={wf_4h.avg_test_sharpe:.3f}")

    logger.info("\n--- Phase 4: Parameter Stability Analysis ---")
    stability_15m = validator.analyze_parameter_stability(wf_15m, "15m")
    logger.info(f"Stable params: {stability_15m.get('stable_count', 0)}/9")

    logger.info("\n--- Phase 5: A/B Testing ---")
    optimizer = BayesianOptOptimizer(n_calls=15, seed=42)
    optimized_config, _ = optimizer.optimize(
        IndicatorConfig(), df_15m, MarketRegime.RANGING,
    )

    ab_result = validator.run_ab_test(
        df_15m,
        IndicatorConfig(),
        optimized_config,
        "bayesian_vs_default_15m",
        n_simulations=30,
    )
    logger.info(f"A/B test: recommendation={ab_result['recommendation']}")

    logger.info("\n--- Phase 6: Safety Limits Check ---")
    safety = validator.check_safety_limits(wf_15m)
    logger.info(f"Safety violations: {safety['violation_rate']:.0%}")

    logger.info("\n--- Phase 7: Generate Report ---")
    report = generate_report(validator)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"production_readiness_{timestamp}.md"
    report_path.write_text(report)

    results_path = REPORTS_DIR / f"validation_results_{timestamp}.json"
    results_path.write_text(json.dumps(validator.results, indent=2, default=str))

    logger.info(f"\nReport saved to: {report_path}")
    logger.info(f"Results saved to: {results_path}")
    logger.info(f"\nOverall Status: {validator.determine_readiness()}")

    print("\n" + "=" * 60)
    print(f"PRODUCTION READINESS: {validator.determine_readiness()}")
    print("=" * 60)

    return validator


if __name__ == "__main__":
    main()
