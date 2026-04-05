"""
SIQE V3 - Risk-Integrated Validation Pipeline

Runs walk-forward validation with risk management controls:
- Position sizing (Kelly + Risk Parity)
- Drawdown gates
- VaR limits
- Stress testing
- Monte Carlo simulation

Generates production readiness report with risk-adjusted metrics.
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
    WalkForwardResult, SafetyLimits,
)
from strategy_engine.ml_optimizer import BayesianOptOptimizer
from strategy_engine.data_loader import load_parquet_data, validate_ohlc_data
from strategy_engine.position_sizer import KellySizer, RiskParitySizer, MaxLimitSizer
from strategy_engine.risk_manager import RiskManager, DrawdownGate, RiskLevel
from strategy_engine.stress_tester import HistoricalStressTester, MonteCarloSimulator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "binance_futures" / "parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


class RiskIntegratedValidator:
    """Orchestrates validation with risk management controls."""

    def __init__(self, portfolio_value: float = 100000.0, seed: int = 42):
        self.portfolio_value = portfolio_value
        self.seed = seed
        self.results: Dict[str, Any] = {}
        self.risk_manager = RiskManager(
            portfolio_value=portfolio_value,
            kelly_fraction=0.25,
            target_volatility=0.15,
            max_var_pct=0.05,
        )

    def run_risk_backtest(self, df: pd.DataFrame, label: str) -> Dict[str, Any]:
        """Run backtest with risk controls applied."""
        logger.info(f"Running risk backtest on {label}: {len(df)} rows")
        
        closes = df["close"]
        returns = closes.pct_change().dropna()
        
        risk_manager = RiskManager(
            portfolio_value=self.portfolio_value,
            kelly_fraction=0.25,
            target_volatility=0.15,
            max_var_pct=0.05,
        )
        
        position_history = []
        daily_returns = []
        portfolio_values = [self.portfolio_value]
        
        window_size = 720
        for i in range(window_size, len(returns), 24):
            train_returns = returns.iloc[max(0, i-window_size):i]
            
            if len(train_returns) < 100:
                continue
            
            position = risk_manager.calculate_position_size(
                train_returns,
                price=float(closes.iloc[i]),
            )
            
            position_history.append({
                "idx": i,
                "fraction": position.fraction_of_portfolio,
                "dollar_amount": position.dollar_amount,
                "method": position.method,
                "warnings": len(position.warnings),
            })
            
            next_return = returns.iloc[i] if i < len(returns) else 0
            position_return = next_return * position.fraction_of_portfolio
            daily_returns.append(position_return)
            
            new_value = portfolio_values[-1] * (1 + position_return)
            portfolio_values.append(new_value)
            risk_manager.update_returns(pd.Series([position_return]))
        
        if not daily_returns:
            return {"error": "no positions taken"}
        
        daily_returns_series = pd.Series(daily_returns)
        portfolio_series = pd.Series(portfolio_values)
        
        total_return = (portfolio_values[-1] / portfolio_values[0] - 1) * 100
        sharpe = float(daily_returns_series.mean() / daily_returns_series.std() * np.sqrt(252)) if daily_returns_series.std() > 0 else 0
        max_dd = float((portfolio_series / portfolio_series.cummax() - 1).min())
        
        risk_metrics = risk_manager.get_risk_metrics(daily_returns_series)
        
        self.results[f"risk_backtest_{label}"] = {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "n_positions": len(position_history),
            "avg_position_size": np.mean([p["fraction"] for p in position_history]) if position_history else 0,
            "risk_level": risk_metrics.risk_level.value,
            "var_95": risk_metrics.var_95,
            "var_99": risk_metrics.var_99,
            "win_rate": risk_metrics.win_rate,
            "sample_positions": position_history[:5],
        }
        
        return self.results[f"risk_backtest_{label}"]

    def run_stress_tests(self, df: pd.DataFrame, label: str) -> Dict[str, Any]:
        """Run stress tests on strategy."""
        logger.info(f"Running stress tests on {label}")
        
        closes = df["close"]
        base_returns = closes.pct_change().dropna()
        
        tester = HistoricalStressTester(max_drawdown_limit=0.20)
        
        scenarios = [
            tester.create_crypto_crash_2022(base_returns),
            tester.create_flash_crash(base_returns),
            tester.create_high_volatility_regime(base_returns),
        ]
        
        stress_results = []
        all_survived = True
        for scenario in scenarios:
            result = tester.test_scenario(scenario, self.portfolio_value)
            stress_results.append({
                "scenario": result.scenario_name,
                "survived": result.survived,
                "max_drawdown": result.max_drawdown,
                "final_return": result.final_return,
                "dd_gate_triggered": result.dd_gate_triggered,
                "warnings": result.warnings,
            })
            if not result.survived:
                all_survived = False
        
        self.results[f"stress_tests_{label}"] = {
            "all_survived": all_survived,
            "scenarios_tested": len(scenarios),
            "scenarios_passed": sum(1 for r in stress_results if r["survived"]),
            "results": stress_results,
        }
        
        return self.results[f"stress_tests_{label}"]

    def run_monte_carlo(self, df: pd.DataFrame, label: str, n_simulations: int = 5000) -> Dict[str, Any]:
        """Run Monte Carlo simulation."""
        logger.info(f"Running Monte Carlo on {label}: {n_simulations} simulations")
        
        closes = df["close"]
        returns = closes.pct_change().dropna()
        
        simulator = MonteCarloSimulator(seed=self.seed)
        result = simulator.simulate(
            returns,
            n_simulations=n_simulations,
            horizon_bars=252,
        )
        
        self.results[f"monte_carlo_{label}"] = {
            "n_simulations": result.n_simulations,
            "mean_return": result.mean_return,
            "median_return": result.median_return,
            "p5_return": result.p5_return,
            "p95_return": result.p95_return,
            "worst_return": result.worst_return,
            "best_return": result.best_return,
            "prob_loss": result.prob_loss,
            "prob_ruin": result.prob_ruin,
            "var_95": result.var_95,
            "var_99": result.var_99,
            "confidence": result.confidence,
        }
        
        return self.results[f"monte_carlo_{label}"]

    def determine_readiness(self) -> str:
        """Determine production readiness with risk controls."""
        score = 0
        max_score = 12

        risk_bt = self.results.get("risk_backtest_15m")
        if risk_bt:
            if risk_bt.get("sharpe_ratio", 0) > 0.1:
                score += 2
            if risk_bt.get("max_drawdown", 0) > -0.15:
                score += 2
            if risk_bt.get("risk_level") == "green":
                score += 1

        stress = self.results.get("stress_tests_15m")
        if stress:
            if stress.get("all_survived"):
                score += 2
            elif stress.get("scenarios_passed", 0) >= 2:
                score += 1

        mc = self.results.get("monte_carlo_15m")
        if mc:
            if mc.get("prob_ruin", 1.0) < 0.10:
                score += 2
            if mc.get("confidence", 0) > 0.5:
                score += 1
            if mc.get("p5_return", -1.0) > -0.20:
                score += 1

        wf = self.results.get("walk_forward_15m")
        if wf:
            if wf.get("pass_rate", 0) >= 0.80:
                score += 1

        safety = self.results.get("safety_limits")
        if safety:
            if safety.get("violation_rate", 1.0) < 0.50:
                score += 1

        if score >= 10:
            return "GREEN"
        elif score >= 6:
            return "YELLOW"
        else:
            return "RED"


def generate_report(validator: RiskIntegratedValidator) -> str:
    """Generate markdown production readiness report with risk metrics."""
    readiness = validator.determine_readiness()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    color_map = {
        "GREEN": "✅ GREEN - Ready for production",
        "YELLOW": "⚠️ YELLOW - Needs attention before production",
        "RED": "❌ RED - Not ready for production",
    }

    report = f"""# SIQE Production Readiness Report (Risk-Integrated)

**Generated:** {datetime.now(timezone.utc).isoformat()}
**Status:** {color_map[readiness]}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Status | **{readiness}** |
| Risk-Adjusted Sharpe | {validator.results.get('risk_backtest_15m', {}).get('sharpe_ratio', 0):.3f} |
| Risk-Adjusted Max DD | {validator.results.get('risk_backtest_15m', {}).get('max_drawdown', 0):.2%} |
| Stress Tests Passed | {validator.results.get('stress_tests_15m', {}).get('scenarios_passed', 0)}/{validator.results.get('stress_tests_15m', {}).get('scenarios_tested', 0)} |
| Monte Carlo Confidence | {validator.results.get('monte_carlo_15m', {}).get('confidence', 0):.0%} |
| Prob of Ruin | {validator.results.get('monte_carlo_15m', {}).get('prob_ruin', 0):.2%} |

---

## 1. Risk-Adjusted Backtest (15m)

"""

    rb = validator.results.get("risk_backtest_15m", {})
    if rb:
        report += f"""| Metric | Value |
|--------|-------|
| **Total Return** | {rb.get('total_return', 0):.2f}% |
| **Sharpe Ratio** | {rb.get('sharpe_ratio', 0):.3f} |
| **Max Drawdown** | {rb.get('max_drawdown', 0):.2%} |
| **Positions Taken** | {rb.get('n_positions', 0)} |
| **Avg Position Size** | {rb.get('avg_position_size', 0):.2%} |
| **Risk Level** | {rb.get('risk_level', 'N/A')} |
| **VaR 95%** | ${rb.get('var_95', 0):.0f} |
| **VaR 99%** | ${rb.get('var_99', 0):.0f} |
| **Win Rate** | {rb.get('win_rate', 0):.2%} |
"""

    report += "\n---\n\n## 2. Stress Test Results\n\n"

    stress = validator.results.get("stress_tests_15m", {})
    if stress:
        report += f"""**All Survived:** {stress.get('all_survived')}
**Scenarios Passed:** {stress.get('scenarios_passed')}/{stress.get('scenarios_tested')}

| Scenario | Survived | Max DD | Final Return | DD Gate |
|----------|----------|--------|--------------|---------|
"""
        for r in stress.get("results", []):
            report += f"| {r['scenario']} | {'✅' if r['survived'] else '❌'} | {r['max_drawdown']:.2%} | {r['final_return']:.2f}% | {'✅' if r['dd_gate_triggered'] else 'No'} |\n"

    report += "\n---\n\n## 3. Monte Carlo Simulation\n\n"

    mc = validator.results.get("monte_carlo_15m", {})
    if mc:
        report += f"""| Metric | Value |
|--------|-------|
| **Simulations** | {mc.get('n_simulations', 0):,} |
| **Mean Return** | {mc.get('mean_return', 0):.2%} |
| **Median Return** | {mc.get('median_return', 0):.2%} |
| **5th Percentile** | {mc.get('p5_return', 0):.2%} |
| **95th Percentile** | {mc.get('p95_return', 0):.2%} |
| **Worst Case** | {mc.get('worst_return', 0):.2%} |
| **Best Case** | {mc.get('best_return', 0):.2%} |
| **Prob of Loss** | {mc.get('prob_loss', 0):.2%} |
| **Prob of Ruin** | {mc.get('prob_ruin', 0):.2%} |
| **Confidence** | {mc.get('confidence', 0):.0%} |
"""

    report += """
---

## 4. Risk Controls Assessment

### Position Sizing
- **Method**: Kelly Criterion (25% fractional) + Risk Parity average
- **Max Position**: 10% of portfolio
- **Sector Limit**: 30% of portfolio
- **VaR Limit**: 5% of portfolio (95% confidence)

### Drawdown Gates
- **Stage 1** (5% DD): Reduce positions by 50%
- **Stage 2** (10% DD): Stop new positions
- **Stage 3** (15% DD): Close all positions

### Correlation Limits
- **Max Correlation**: 0.70 between positions
- **Action**: Reduce position by 50% if exceeded

---

## 5. Recommendations

"""

    if readiness == "GREEN":
        report += """### ✅ Ready for Production

- Risk controls are effective at limiting drawdowns
- Stress tests pass under adverse conditions
- Monte Carlo shows acceptable risk of ruin
- Position sizing is conservative and well-controlled

**Next Steps:**
1. Deploy with paper trading first (2-4 weeks)
2. Monitor risk metrics daily
3. Review position sizing weekly
4. Gradually increase allocation as confidence builds
"""
    elif readiness == "YELLOW":
        report += """### ⚠️ Needs Attention Before Production

- Risk controls are functional but strategy needs improvement
- Some stress scenarios may require adjustment
- Monte Carlo shows moderate risk levels

**Recommended Actions:**
1. Paper trade for 4-8 weeks minimum
2. Collect more historical data (12+ months)
3. Improve strategy alpha before increasing allocation
4. Set up real-time risk monitoring dashboard
"""
    else:
        report += """### ❌ Not Ready for Production

- Risk controls cannot compensate for weak strategy
- Stress tests show unacceptable drawdowns
- Monte Carlo shows high probability of ruin

**Required Actions:**
1. Redesign strategy for better alpha generation
2. Add more uncorrelated strategies
3. Collect significantly more data
4. Consider alternative approaches
"""

    report += f"""
---

## 6. Configuration Snapshot

**Portfolio Value:** ${validator.portfolio_value:,.0f}
**Kelly Fraction:** 25%
**Target Volatility:** 15%
**Max VaR:** 5%

**Report saved to:** `reports/production_readiness_risk_{timestamp}.md`
"""

    return report


def main():
    """Run full risk-integrated validation pipeline."""
    logger.info("=" * 60)
    logger.info("SIQE V3 - Risk-Integrated Validation Pipeline")
    logger.info("=" * 60)

    validator = RiskIntegratedValidator(portfolio_value=100000.0, seed=42)

    logger.info("\n--- Phase 1: Load Data ---")
    df_15m = load_parquet_data(str(DATA_DIR / "btcusdt_15m.parquet"))
    is_valid, dq_report = validate_ohlc_data(df_15m)
    logger.info(f"Data loaded: {len(df_15m)} rows, valid={is_valid}")

    logger.info("\n--- Phase 2: Walk-Forward (for reference) ---")
    wf_validator = WalkForwardValidator(
        train_months=3, test_months=1, bars_per_month=720,
        min_sharpe_threshold=0.5, min_pass_rate=0.70,
    )
    optimizer = BayesianOptOptimizer(n_calls=15, seed=42)
    wf_result = wf_validator.validate(df_15m, optimizer=optimizer, regime=MarketRegime.RANGING)
    
    validator.results["walk_forward_15m"] = {
        "passed": wf_result.passed,
        "n_windows": len(wf_result.windows),
        "avg_test_sharpe": wf_result.avg_test_sharpe,
        "pass_rate": wf_result.pass_rate,
    }
    logger.info(f"Walk-forward: passed={wf_result.passed}, avg_sharpe={wf_result.avg_test_sharpe:.3f}")

    safety = SafetyLimits()
    violations_count = 0
    for window in wf_result.windows:
        safe, _ = safety.validate_param_change(IndicatorConfig(), window.optimized_config)
        if not safe:
            violations_count += 1
    
    validator.results["safety_limits"] = {
        "total_windows": len(wf_result.windows),
        "windows_with_violations": violations_count,
        "violation_rate": violations_count / len(wf_result.windows) if wf_result.windows else 0,
    }

    logger.info("\n--- Phase 3: Risk-Adjusted Backtest ---")
    risk_result = validator.run_risk_backtest(df_15m, "15m")
    logger.info(f"Risk backtest: sharpe={risk_result.get('sharpe_ratio', 0):.3f}, max_dd={risk_result.get('max_drawdown', 0):.2%}")

    logger.info("\n--- Phase 4: Stress Testing ---")
    stress_result = validator.run_stress_tests(df_15m, "15m")
    logger.info(f"Stress tests: {stress_result.get('scenarios_passed', 0)}/{stress_result.get('scenarios_tested', 0)} passed")

    logger.info("\n--- Phase 5: Monte Carlo Simulation ---")
    mc_result = validator.run_monte_carlo(df_15m, "15m", n_simulations=5000)
    logger.info(f"Monte Carlo: prob_loss={mc_result.get('prob_loss', 0):.2%}, prob_ruin={mc_result.get('prob_ruin', 0):.2%}")

    logger.info("\n--- Phase 6: Generate Report ---")
    report = generate_report(validator)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"production_readiness_risk_{timestamp}.md"
    report_path.write_text(report)

    results_path = REPORTS_DIR / f"risk_validation_results_{timestamp}.json"
    results_path.write_text(json.dumps(validator.results, indent=2, default=str))

    logger.info(f"\nReport saved to: {report_path}")
    logger.info(f"Results saved to: {results_path}")
    logger.info(f"\nOverall Status: {validator.determine_readiness()}")

    print("\n" + "=" * 60)
    print(f"PRODUCTION READINESS (RISK-INTEGRATED): {validator.determine_readiness()}")
    print("=" * 60)

    return validator


if __name__ == "__main__":
    main()
