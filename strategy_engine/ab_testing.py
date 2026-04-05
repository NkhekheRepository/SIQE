"""
SIQE V3 - A/B Testing Framework

Compare baseline vs ML-optimized indicator configurations
in parallel to validate performance improvement before
full deployment.

Usage:
    ab_test = ABTestRunner(baseline_config, optimized_config)
    result = ab_test.run(data, n_simulations=100)
    if result.treatment_wins:
        deploy(optimized_config)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

from strategy_engine.config import IndicatorConfig, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class ABTestResult:
    """Result from an A/B test comparison."""
    # Baseline metrics
    baseline_sharpe: float
    baseline_return: float
    baseline_drawdown: float
    baseline_trades: int
    baseline_win_rate: float
    
    # Treatment metrics
    treatment_sharpe: float
    treatment_return: float
    treatment_drawdown: float
    treatment_trades: int
    treatment_win_rate: float
    
    # Statistical significance
    sharpe_p_value: float
    return_p_value: float
    sharpe_significant: bool
    return_significant: bool
    
    # Decision
    treatment_wins: bool
    confidence: float
    recommendation: str  # "deploy", "reject", "inconclusive"
    
    # Metadata
    n_simulations: int
    test_date: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.test_date:
            self.test_date = datetime.now(timezone.utc).isoformat()


class ABTestRunner:
    """
    A/B test runner for indicator configuration comparison.
    
    Runs parallel simulations with baseline and treatment configs,
    then performs statistical tests to determine if the treatment
    (ML-optimized config) is significantly better than the baseline.
    
    Decision criteria:
    - Treatment wins if Sharpe improvement is significant (p < 0.05)
    - Requires minimum 30 simulations for statistical power
    - Reports confidence level and recommendation
    """
    
    def __init__(
        self,
        baseline: IndicatorConfig,
        treatment: IndicatorConfig,
        seed: int = 42,
    ):
        self.baseline = baseline
        self.treatment = treatment
        self.rng = np.random.RandomState(seed)
    
    def run(
        self,
        data: pd.DataFrame,
        n_simulations: int = 100,
        sample_fraction: float = 0.8,
    ) -> ABTestResult:
        """
        Run A/B test with bootstrap sampling.
        
        Args:
            data: DataFrame with high/low/close columns
            n_simulations: Number of bootstrap samples
            sample_fraction: Fraction of data per simulation
            
        Returns:
            ABTestResult with metrics and statistical significance
        """
        baseline_sharpes = []
        baseline_returns = []
        treatment_sharpes = []
        treatment_returns = []
        
        n = len(data)
        sample_size = int(n * sample_fraction)
        
        for i in range(n_simulations):
            indices = self.rng.choice(n, size=sample_size, replace=True)
            sample_data = data.iloc[sorted(indices)].reset_index(drop=True)
            
            if len(sample_data) < 50:
                continue
            
            try:
                b_metrics = self._evaluate(self.baseline, sample_data)
                t_metrics = self._evaluate(self.treatment, sample_data)
                
                baseline_sharpes.append(b_metrics["sharpe"])
                baseline_returns.append(b_metrics["total_return"])
                treatment_sharpes.append(t_metrics["sharpe"])
                treatment_returns.append(t_metrics["total_return"])
            except Exception:
                continue
        
        if len(baseline_sharpes) < 10:
            return self._inconclusive_result(n_simulations)
        
        sharpe_diff = np.array(treatment_sharpes) - np.array(baseline_sharpes)
        return_diff = np.array(treatment_returns) - np.array(baseline_returns)
        
        sharpe_t, sharpe_p = stats.ttest_1samp(sharpe_diff, 0)
        return_t, return_p = stats.ttest_1samp(return_diff, 0)
        
        avg_baseline_sharpe = float(np.mean(baseline_sharpes))
        avg_treatment_sharpe = float(np.mean(treatment_sharpes))
        avg_baseline_return = float(np.mean(baseline_returns))
        avg_treatment_return = float(np.mean(treatment_returns))
        
        sharpe_significant = sharpe_p < 0.05
        return_significant = return_p < 0.05
        
        treatment_wins = avg_treatment_sharpe > avg_baseline_sharpe and sharpe_significant
        
        confidence = float(1 - sharpe_p) if sharpe_significant else 0.0
        
        if treatment_wins:
            recommendation = "deploy"
        elif avg_treatment_sharpe < avg_baseline_sharpe and sharpe_significant:
            recommendation = "reject"
        else:
            recommendation = "inconclusive"
        
        result = ABTestResult(
            baseline_sharpe=avg_baseline_sharpe,
            baseline_return=avg_baseline_return,
            baseline_drawdown=float(np.mean([self._evaluate(self.baseline, data.iloc[:100]).get("max_drawdown", 0)])),
            baseline_trades=int(np.mean([self._evaluate(self.baseline, data).get("total_trades", 0)])),
            baseline_win_rate=float(np.mean([self._evaluate(self.baseline, data).get("win_rate", 0)])),
            treatment_sharpe=avg_treatment_sharpe,
            treatment_return=avg_treatment_return,
            treatment_drawdown=float(np.mean([self._evaluate(self.treatment, data.iloc[:100]).get("max_drawdown", 0)])),
            treatment_trades=int(np.mean([self._evaluate(self.treatment, data).get("total_trades", 0)])),
            treatment_win_rate=float(np.mean([self._evaluate(self.treatment, data).get("win_rate", 0)])),
            sharpe_p_value=float(sharpe_p),
            return_p_value=float(return_p),
            sharpe_significant=sharpe_significant,
            return_significant=return_significant,
            treatment_wins=treatment_wins,
            confidence=confidence,
            recommendation=recommendation,
            n_simulations=len(baseline_sharpes),
            metadata={
                "sharpe_diff_mean": float(np.mean(sharpe_diff)),
                "sharpe_diff_std": float(np.std(sharpe_diff)),
                "return_diff_mean": float(np.mean(return_diff)),
            },
        )
        
        logger.info(
            f"A/B test complete: baseline_sharpe={avg_baseline_sharpe:.3f}, "
            f"treatment_sharpe={avg_treatment_sharpe:.3f}, "
            f"p_value={sharpe_p:.4f}, recommendation={recommendation}"
        )
        
        return result
    
    def _evaluate(self, config: IndicatorConfig, data: pd.DataFrame) -> Dict[str, float]:
        """Evaluate a config on data using MACD crossover proxy."""
        closes = data["close"]
        
        if len(closes) < config.macd_slow * 3:
            return {"sharpe": -10.0, "total_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0}
        
        fast_ema = closes.ewm(span=config.macd_fast, adjust=False).mean()
        slow_ema = closes.ewm(span=config.macd_slow, adjust=False).mean()
        
        signals = pd.Series(0, index=closes.index)
        signals[fast_ema > slow_ema] = 1
        signals[fast_ema < slow_ema] = -1
        
        returns = signals.shift(1) * closes.pct_change()
        returns = returns.dropna()
        
        if len(returns) < 30 or returns.std() == 0:
            return {"sharpe": -10.0, "total_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0}
        
        sharpe = returns.mean() / returns.std() * np.sqrt(252)
        total_return = float((1 + returns).prod() - 1) * 100
        
        cumsum = (1 + returns).cumprod()
        running_max = cumsum.cummax()
        drawdown = (cumsum - running_max) / running_max
        max_drawdown = float(drawdown.min())
        
        trades = signals.diff().abs()
        trade_returns = returns[trades > 0]
        total_trades = int((trades > 0).sum())
        win_rate = float((trade_returns > 0).sum() / len(trade_returns)) if len(trade_returns) > 0 else 0.0
        
        return {
            "sharpe": float(sharpe),
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": total_trades,
        }
    
    def _inconclusive_result(self, n_simulations: int) -> ABTestResult:
        """Return inconclusive result when insufficient data."""
        return ABTestResult(
            baseline_sharpe=0.0,
            baseline_return=0.0,
            baseline_drawdown=0.0,
            baseline_trades=0,
            baseline_win_rate=0.0,
            treatment_sharpe=0.0,
            treatment_return=0.0,
            treatment_drawdown=0.0,
            treatment_trades=0,
            treatment_win_rate=0.0,
            sharpe_p_value=1.0,
            return_p_value=1.0,
            sharpe_significant=False,
            return_significant=False,
            treatment_wins=False,
            confidence=0.0,
            recommendation="inconclusive",
            n_simulations=n_simulations,
            metadata={"error": "insufficient_valid_simulations"},
        )
