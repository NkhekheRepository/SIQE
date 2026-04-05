"""
SIQE V3 - Stress Testing Engine

Historical scenario testing and Monte Carlo simulation
for validating risk controls under adverse conditions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """Historical stress scenario definition."""
    name: str
    description: str
    returns: pd.Series
    max_drawdown: float
    volatility: float
    worst_day: float


@dataclass
class StressResult:
    """Result of stress testing a scenario."""
    scenario_name: str
    survived: bool
    max_drawdown: float
    final_return: float
    var_breaches: int
    dd_gate_triggered: bool
    recovery_time_bars: Optional[int]
    warnings: List[str] = field(default_factory=list)


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation."""
    n_simulations: int
    mean_return: float
    median_return: float
    p5_return: float
    p95_return: float
    worst_return: float
    best_return: float
    prob_loss: float
    prob_ruin: float
    var_95: float
    var_99: float
    confidence: float


class HistoricalStressTester:
    """
    Tests strategy against historical stress scenarios.
    """
    
    def __init__(self, max_drawdown_limit: float = 0.20):
        self.max_drawdown_limit = max_drawdown_limit
    
    def create_crypto_crash_2022(self, base_returns: pd.Series) -> StressScenario:
        """Simulate 2022 crypto crash conditions."""
        crash_returns = base_returns.copy()
        crash_returns = crash_returns * 2.5
        crash_returns.iloc[:20] = crash_returns.iloc[:20] - 0.03
        
        cumsum = (1 + crash_returns).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        max_dd = float(dd.min())
        
        return StressScenario(
            name="crypto_crash_2022",
            description="Simulated 2022 crypto crash: LUNA, FTX, 3AC collapse",
            returns=crash_returns,
            max_drawdown=max_dd,
            volatility=float(crash_returns.std() * np.sqrt(252)),
            worst_day=float(crash_returns.min()),
        )
    
    def create_flash_crash(self, base_returns: pd.Series) -> StressScenario:
        """Simulate flash crash with sudden large drop."""
        flash_returns = base_returns.copy()
        flash_returns.iloc[len(flash_returns) // 2] = -0.15
        flash_returns.iloc[len(flash_returns) // 2 + 1] = 0.08
        
        cumsum = (1 + flash_returns).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        max_dd = float(dd.min())
        
        return StressScenario(
            name="flash_crash",
            description="Flash crash: 15% single-bar drop with partial recovery",
            returns=flash_returns,
            max_drawdown=max_dd,
            volatility=float(flash_returns.std() * np.sqrt(252)),
            worst_day=float(flash_returns.min()),
        )
    
    def create_high_volatility_regime(self, base_returns: pd.Series) -> StressScenario:
        """Simulate sustained high volatility regime."""
        vol_returns = base_returns.copy()
        vol_returns = vol_returns * 3.0
        
        cumsum = (1 + vol_returns).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        max_dd = float(dd.min())
        
        return StressScenario(
            name="high_vol_regime",
            description="Sustained high volatility: 3x normal volatility",
            returns=vol_returns,
            max_drawdown=max_dd,
            volatility=float(vol_returns.std() * np.sqrt(252)),
            worst_day=float(vol_returns.min()),
        )
    
    def test_scenario(
        self,
        scenario: StressScenario,
        portfolio_value: float = 100000.0,
    ) -> StressResult:
        """
        Test a stress scenario against risk controls.
        
        Args:
            scenario: Stress scenario to test
            portfolio_value: Portfolio value
            
        Returns:
            StressResult with outcome
        """
        warnings = []
        
        cumsum = (1 + scenario.returns).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        max_dd = float(dd.min())
        final_return = float((cumsum.iloc[-1] - 1) * 100)
        
        survived = max_dd > -self.max_drawdown_limit
        
        if not survived:
            warnings.append(
                f"Max drawdown {max_dd:.1%} exceeds limit {self.max_drawdown_limit:.0%}"
            )
        
        var_95 = float(np.percentile(scenario.returns, 5))
        var_breaches = int((scenario.returns < var_95).sum())
        
        dd_gate_triggered = max_dd < -0.10
        
        recovery_bars = None
        if max_dd < 0:
            dd_idx = dd.values.argmin()
            post_dd = cumsum.iloc[dd_idx:]
            pre_dd_level = cumsum.iloc[dd_idx - 1] if dd_idx > 0 else 1.0
            recovered = post_dd[post_dd >= pre_dd_level]
            if len(recovered) > 0:
                recovery_bars = len(recovered)
        
        return StressResult(
            scenario_name=scenario.name,
            survived=survived,
            max_drawdown=max_dd,
            final_return=final_return,
            var_breaches=var_breaches,
            dd_gate_triggered=dd_gate_triggered,
            recovery_time_bars=recovery_bars,
            warnings=warnings,
        )


class MonteCarloSimulator:
    """
    Monte Carlo simulation for strategy validation.
    
    Simulates thousands of possible future paths based on
    historical return distribution.
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.RandomState(seed)
    
    def simulate(
        self,
        returns: pd.Series,
        n_simulations: int = 10000,
        horizon_bars: int = 252,
        prob_ruin_threshold: float = 0.50,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation.
        
        Args:
            returns: Historical returns to bootstrap from
            n_simulations: Number of simulation paths
            horizon_bars: Number of bars per simulation
            prob_ruin_threshold: Portfolio value threshold for "ruin"
            
        Returns:
            MonteCarloResult with simulation statistics
        """
        if len(returns) < 30:
            return MonteCarloResult(
                n_simulations=0,
                mean_return=0.0,
                median_return=0.0,
                p5_return=0.0,
                p95_return=0.0,
                worst_return=0.0,
                best_return=0.0,
                prob_loss=0.0,
                prob_ruin=0.0,
                var_95=0.0,
                var_99=0.0,
                confidence=0.0,
            )
        
        final_returns = np.zeros(n_simulations)
        
        for i in range(n_simulations):
            sim_returns = self.rng.choice(returns, size=horizon_bars)
            final_returns[i] = float(np.prod(1 + sim_returns) - 1)
        
        sorted_returns = np.sort(final_returns)
        
        mean_ret = float(np.mean(final_returns))
        median_ret = float(np.median(final_returns))
        p5 = float(np.percentile(final_returns, 5))
        p95 = float(np.percentile(final_returns, 95))
        worst = float(np.min(final_returns))
        best = float(np.max(final_returns))
        prob_loss = float(np.mean(final_returns < 0))
        prob_ruin = float(np.mean(final_returns < -prob_ruin_threshold))
        
        var_95 = abs(float(np.percentile(final_returns, 5)))
        var_99 = abs(float(np.percentile(final_returns, 1)))
        
        confidence = max(0.0, 1.0 - prob_ruin * 2)
        
        return MonteCarloResult(
            n_simulations=n_simulations,
            mean_return=mean_ret,
            median_return=median_ret,
            p5_return=p5,
            p95_return=p95,
            worst_return=worst,
            best_return=best,
            prob_loss=prob_loss,
            prob_ruin=prob_ruin,
            var_95=var_95,
            var_99=var_99,
            confidence=confidence,
        )
