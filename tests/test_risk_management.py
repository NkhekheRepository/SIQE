"""
Tests for SIQE V3 Risk Management

Tests position sizing, risk manager, drawdown gates, VaR,
correlation checks, stress testing, and Monte Carlo simulation.
"""
import pytest
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.position_sizer import (
    KellySizer, RiskParitySizer, MaxLimitSizer, PositionSize,
)
from strategy_engine.risk_manager import (
    RiskManager, DrawdownGate, VaRCalculator, CorrelationChecker,
    RiskMetrics, RiskLevel,
)
from strategy_engine.stress_tester import (
    HistoricalStressTester, MonteCarloSimulator,
    StressScenario, StressResult, MonteCarloResult,
)


def generate_strategy_returns(n=100, win_rate=0.55, seed=42):
    """Generate realistic strategy returns."""
    rng = np.random.RandomState(seed)
    returns = np.zeros(n)
    for i in range(n):
        if rng.random() < win_rate:
            returns[i] = rng.uniform(0.001, 0.03)
        else:
            returns[i] = rng.uniform(-0.02, -0.001)
    return pd.Series(returns)


class TestKellySizer:
    def test_calculate_returns_position_size(self):
        sizer = KellySizer(kelly_fraction=0.25)
        returns = generate_strategy_returns()
        position = sizer.calculate(returns, portfolio_value=100000, price=50000)
        
        assert isinstance(position, PositionSize)
        assert position.method == "kelly"
        assert 0 <= position.fraction_of_portfolio <= 0.10
        assert position.dollar_amount > 0
        assert position.shares > 0
    
    def test_insufficient_trades_returns_zero(self):
        sizer = KellySizer(kelly_fraction=0.25, min_trades=30)
        returns = generate_strategy_returns(n=10)
        position = sizer.calculate(returns, portfolio_value=100000, price=50000)
        
        assert position.fraction_of_portfolio == 0.0
        assert len(position.warnings) > 0
    
    def test_all_winning_trades_handled(self):
        sizer = KellySizer(kelly_fraction=0.25)
        returns = pd.Series([0.01] * 50)
        position = sizer.calculate(returns, portfolio_value=100000, price=50000)
        
        assert position.fraction_of_portfolio == 0.0
        assert len(position.warnings) > 0
    
    def test_kelly_fraction_affects_size(self):
        returns = generate_strategy_returns()
        sizer_conservative = KellySizer(kelly_fraction=0.25)
        sizer_aggressive = KellySizer(kelly_fraction=0.50)
        
        pos_conservative = sizer_conservative.calculate(returns, price=50000)
        pos_aggressive = sizer_aggressive.calculate(returns, price=50000)
        
        assert pos_aggressive.fraction_of_portfolio >= pos_conservative.fraction_of_portfolio


class TestRiskParitySizer:
    def test_calculate_returns_position_size(self):
        sizer = RiskParitySizer(target_volatility=0.15)
        returns = generate_strategy_returns()
        position = sizer.calculate(returns, portfolio_value=100000, price=50000)
        
        assert isinstance(position, PositionSize)
        assert position.method == "risk_parity"
        assert position.fraction_of_portfolio > 0
    
    def test_high_volatility_reduces_size(self):
        sizer = RiskParitySizer(target_volatility=0.15)
        low_vol_returns = generate_strategy_returns() * 0.5
        high_vol_returns = generate_strategy_returns() * 2.0
        
        pos_low = sizer.calculate(low_vol_returns, price=50000)
        pos_high = sizer.calculate(high_vol_returns, price=50000)
        
        assert pos_low.fraction_of_portfolio >= pos_high.fraction_of_portfolio
    
    def test_insufficient_data_returns_zero(self):
        sizer = RiskParitySizer()
        returns = generate_strategy_returns(n=10)
        position = sizer.calculate(returns, price=50000)
        
        assert position.fraction_of_portfolio == 0.0


class TestMaxLimitSizer:
    def test_enforce_position_within_limits(self):
        sizer = MaxLimitSizer(max_position_pct=0.10)
        position = PositionSize(
            fraction_of_portfolio=0.05,
            dollar_amount=5000,
            shares=0.1,
            stop_loss=49000,
            take_profit=51000,
            risk_per_share=1000,
            method="kelly",
            confidence=0.8,
            warnings=[],
        )
        
        result, warnings = sizer.enforce(position, portfolio_value=100000)
        
        assert result.dollar_amount == 5000
        assert len(warnings) == 0
    
    def test_enforce_caps_oversized_position(self):
        sizer = MaxLimitSizer(max_position_pct=0.10)
        position = PositionSize(
            fraction_of_portfolio=0.20,
            dollar_amount=20000,
            shares=0.4,
            stop_loss=49000,
            take_profit=51000,
            risk_per_share=1000,
            method="kelly",
            confidence=0.8,
            warnings=[],
        )
        
        result, warnings = sizer.enforce(position, portfolio_value=100000)
        
        assert result.dollar_amount == 10000
        assert len(warnings) > 0
    
    def test_sector_concentration_limit(self):
        sizer = MaxLimitSizer(max_sector_pct=0.30)
        position = PositionSize(
            fraction_of_portfolio=0.15,
            dollar_amount=15000,
            shares=0.3,
            stop_loss=49000,
            take_profit=51000,
            risk_per_share=1000,
            method="kelly",
            confidence=0.8,
            warnings=[],
        )
        
        result, warnings = sizer.enforce(
            position, portfolio_value=100000, sector_exposure=20000
        )
        
        assert result.dollar_amount <= 10000


class TestDrawdownGate:
    def test_normal_state(self):
        gate = DrawdownGate()
        stage, action, level = gate.check(-0.02)
        
        assert stage == 0
        assert action == "normal"
        assert level == RiskLevel.GREEN
    
    def test_stage1_reduction(self):
        gate = DrawdownGate()
        stage, action, level = gate.check(-0.06)
        
        assert stage == 1
        assert action == "reduce_50"
        assert level == RiskLevel.YELLOW
    
    def test_stage2_stop_new(self):
        gate = DrawdownGate()
        stage, action, level = gate.check(-0.12)
        
        assert stage == 2
        assert action == "stop_new"
        assert level == RiskLevel.RED
    
    def test_stage3_close_all(self):
        gate = DrawdownGate()
        stage, action, level = gate.check(-0.16)
        
        assert stage == 3
        assert action == "close_all"
        assert level == RiskLevel.RED
    
    def test_adjustment_reduces_position(self):
        gate = DrawdownGate()
        gate.check(-0.06)
        
        position = PositionSize(
            fraction_of_portfolio=0.10,
            dollar_amount=10000,
            shares=0.2,
            stop_loss=49000,
            take_profit=51000,
            risk_per_share=1000,
            method="kelly",
            confidence=0.8,
            warnings=[],
        )
        
        adjusted = gate.apply_position_adjustment(position)
        
        assert adjusted.fraction_of_portfolio == 0.05
        assert adjusted.dollar_amount == 5000
    
    def test_stage2_blocks_all_positions(self):
        gate = DrawdownGate()
        gate.check(-0.12)
        
        position = PositionSize(
            fraction_of_portfolio=0.10,
            dollar_amount=10000,
            shares=0.2,
            stop_loss=49000,
            take_profit=51000,
            risk_per_share=1000,
            method="kelly",
            confidence=0.8,
            warnings=[],
        )
        
        adjusted = gate.apply_position_adjustment(position)
        
        assert adjusted.dollar_amount == 0.0


class TestVaRCalculator:
    def test_calculate_var(self):
        calc = VaRCalculator()
        returns = generate_strategy_returns()
        result = calc.calculate(returns, portfolio_value=100000)
        
        assert "var_95" in result
        assert "var_99" in result
        assert result["var_95"] > 0
        assert result["var_99"] >= result["var_95"]
    
    def test_insufficient_data_returns_zero(self):
        calc = VaRCalculator()
        returns = generate_strategy_returns(n=10)
        result = calc.calculate(returns)
        
        assert result["var_95"] == 0.0


class TestCorrelationChecker:
    def test_low_correlation_passes(self):
        checker = CorrelationChecker(max_correlation=0.70)
        rng = np.random.RandomState(42)
        
        new_returns = pd.Series(rng.randn(100) * 0.01)
        existing = {"pos1": pd.Series(rng.randn(100) * 0.01)}
        
        ok, warnings = checker.check(new_returns, existing)
        
        assert ok is True
    
    def test_high_correlation_fails(self):
        checker = CorrelationChecker(max_correlation=0.70)
        
        base = pd.Series(np.random.RandomState(42).randn(100) * 0.01)
        new_returns = base * 1.1
        existing = {"pos1": base}
        
        ok, warnings = checker.check(new_returns, existing)
        
        assert ok is False
        assert len(warnings) > 0


class TestRiskManager:
    def test_calculate_position_size(self):
        manager = RiskManager(portfolio_value=100000)
        returns = generate_strategy_returns()
        
        position = manager.calculate_position_size(returns, price=50000)
        
        assert isinstance(position, PositionSize)
        assert position.fraction_of_portfolio >= 0
    
    def test_drawdown_gate_blocks_positions(self):
        manager = RiskManager(portfolio_value=100000)
        returns = generate_strategy_returns()
        
        manager._returns_history = pd.Series([-0.12] * 10)
        
        position = manager.calculate_position_size(returns, price=50000)
        
        assert position.dollar_amount == 0.0
    
    def test_get_risk_metrics(self):
        manager = RiskManager(portfolio_value=100000)
        returns = generate_strategy_returns()
        
        metrics = manager.get_risk_metrics(returns)
        
        assert isinstance(metrics, RiskMetrics)
        assert metrics.var_95 > 0
        assert metrics.sharpe_ratio != 0
    
    def test_reset_clears_state(self):
        manager = RiskManager(portfolio_value=100000)
        returns = generate_strategy_returns()
        manager.calculate_position_size(returns, price=50000)
        
        manager.reset()
        
        assert len(manager._position_history) == 0
        assert len(manager._returns_history) == 0


class TestHistoricalStressTester:
    def test_create_crypto_crash_scenario(self):
        tester = HistoricalStressTester()
        base_returns = generate_strategy_returns()
        
        scenario = tester.create_crypto_crash_2022(base_returns)
        
        assert isinstance(scenario, StressScenario)
        assert scenario.name == "crypto_crash_2022"
        assert scenario.max_drawdown < 0
    
    def test_create_flash_crash_scenario(self):
        tester = HistoricalStressTester()
        base_returns = generate_strategy_returns()
        
        scenario = tester.create_flash_crash(base_returns)
        
        assert isinstance(scenario, StressScenario)
        assert scenario.worst_day <= -0.15
    
    def test_create_high_volatility_scenario(self):
        tester = HistoricalStressTester()
        base_returns = generate_strategy_returns()
        
        scenario = tester.create_high_volatility_regime(base_returns)
        
        assert isinstance(scenario, StressScenario)
        assert scenario.volatility > base_returns.std() * np.sqrt(252)
    
    def test_test_scenario_returns_result(self):
        tester = HistoricalStressTester()
        base_returns = generate_strategy_returns()
        scenario = tester.create_crypto_crash_2022(base_returns)
        
        result = tester.test_scenario(scenario)
        
        assert isinstance(result, StressResult)
        assert result.scenario_name == scenario.name
        assert result.max_drawdown < 0


class TestMonteCarloSimulator:
    def test_simulate_returns_result(self):
        simulator = MonteCarloSimulator(seed=42)
        returns = generate_strategy_returns()
        
        result = simulator.simulate(returns, n_simulations=1000)
        
        assert isinstance(result, MonteCarloResult)
        assert result.n_simulations == 1000
        assert result.mean_return != 0
        assert result.p5_return <= result.median_return
        assert result.median_return <= result.p95_return
    
    def test_prob_loss_is_valid(self):
        simulator = MonteCarloSimulator(seed=42)
        returns = generate_strategy_returns()
        
        result = simulator.simulate(returns, n_simulations=1000)
        
        assert 0 <= result.prob_loss <= 1.0
    
    def test_prob_ruin_is_valid(self):
        simulator = MonteCarloSimulator(seed=42)
        returns = generate_strategy_returns()
        
        result = simulator.simulate(returns, n_simulations=1000)
        
        assert 0 <= result.prob_ruin <= 1.0
    
    def test_insufficient_data_returns_empty(self):
        simulator = MonteCarloSimulator(seed=42)
        returns = generate_strategy_returns(n=10)
        
        result = simulator.simulate(returns, n_simulations=100)
        
        assert result.n_simulations == 0
        assert result.confidence == 0.0
