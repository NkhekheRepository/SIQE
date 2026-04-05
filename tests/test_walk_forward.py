"""
Walk-Forward, Safety Limits, Config Persistence, and A/B Testing Tests

Tests for production-grade validation and deployment infrastructure.
"""
import pytest
import sys
import os
import tempfile
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.config import (
    IndicatorConfig, ConfigPersistence, ConfigMetadata,
    SafetyLimits, WalkForwardValidator, WalkForwardResult,
    WalkForwardWindow, MarketRegime,
)
from strategy_engine.ab_testing import ABTestRunner, ABTestResult


def generate_test_data(n=500, seed=42):
    """Generate synthetic OHLC data for testing."""
    rng = np.random.RandomState(seed)
    closes = pd.Series(np.cumsum(rng.randn(n)) + 100)
    highs = closes + np.abs(rng.randn(n)) * 0.5
    lows = closes - np.abs(rng.randn(n)) * 0.5
    return pd.DataFrame({'high': highs, 'low': lows, 'close': closes})


class TestConfigPersistence:
    def test_save_and_load(self):
        config = IndicatorConfig(rsi_period=21, bollinger_std=2.5)
        metadata = ConfigMetadata(source='bayesian', optimized_for='trending')
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        
        try:
            ConfigPersistence.save(config, path, metadata)
            loaded, loaded_meta = ConfigPersistence.load(path)
            
            assert loaded.rsi_period == 21
            assert loaded.bollinger_std == 2.5
            assert loaded_meta.source == 'bayesian'
            assert loaded_meta.optimized_for == 'trending'
        finally:
            os.unlink(path)
    
    def test_save_creates_valid_json(self):
        config = IndicatorConfig()
        metadata = ConfigMetadata(source='manual')
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        
        try:
            ConfigPersistence.save(config, path, metadata)
            with open(path, 'r') as f:
                data = json.load(f)
            
            assert 'metadata' in data
            assert 'config' in data
            assert data['metadata']['source'] == 'manual'
        finally:
            os.unlink(path)
    
    def test_load_without_metadata(self):
        config = IndicatorConfig(macd_fast=10)
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        
        try:
            ConfigPersistence.save(config, path)
            loaded, loaded_meta = ConfigPersistence.load(path)
            
            assert loaded.macd_fast == 10
            assert loaded_meta.version == '1.0.0'
        finally:
            os.unlink(path)


class TestSafetyLimits:
    def test_default_limits(self):
        limits = SafetyLimits()
        assert limits.max_param_change_pct == 0.20
        assert limits.min_confidence == 0.70
        assert limits.circuit_breaker_losses == 5
        assert limits.circuit_breaker_drawdown == 0.10
    
    def test_validate_small_change_passes(self):
        limits = SafetyLimits()
        baseline = IndicatorConfig()
        proposed = IndicatorConfig(bollinger_std=2.1)
        
        safe, violations = limits.validate_param_change(baseline, proposed)
        assert safe is True
        assert len(violations) == 0
    
    def test_validate_large_change_fails(self):
        limits = SafetyLimits()
        baseline = IndicatorConfig()
        proposed = IndicatorConfig(rsi_period=50)
        
        safe, violations = limits.validate_param_change(baseline, proposed)
        assert safe is False
        assert len(violations) > 0
        assert 'rsi_period' in violations[0]
    
    def test_validate_multiple_violations(self):
        limits = SafetyLimits()
        baseline = IndicatorConfig()
        proposed = IndicatorConfig(rsi_period=50, macd_fast=8, macd_slow=50, macd_signal=18)
        
        safe, violations = limits.validate_param_change(baseline, proposed)
        assert safe is False
        assert len(violations) >= 2
    
    def test_circuit_breaker_consecutive_losses(self):
        limits = SafetyLimits()
        triggered, reason = limits.check_circuit_breaker(6, 0.05)
        assert triggered is True
        assert 'consecutive losses' in reason
    
    def test_circuit_breaker_drawdown(self):
        limits = SafetyLimits()
        triggered, reason = limits.check_circuit_breaker(2, 0.15)
        assert triggered is True
        assert 'drawdown' in reason
    
    def test_circuit_breaker_not_triggered(self):
        limits = SafetyLimits()
        triggered, reason = limits.check_circuit_breaker(2, 0.05)
        assert triggered is False
        assert reason == ''
    
    def test_custom_limits(self):
        limits = SafetyLimits(max_param_change_pct=0.10, circuit_breaker_losses=3)
        baseline = IndicatorConfig()
        proposed = IndicatorConfig(rsi_period=16)
        
        safe, violations = limits.validate_param_change(baseline, proposed)
        assert safe is False


class TestWalkForwardValidator:
    def test_validate_returns_result(self):
        data = generate_test_data(n=300)
        validator = WalkForwardValidator(train_months=1, test_months=1, bars_per_month=60)
        result = validator.validate(data, regime=MarketRegime.RANGING)
        assert isinstance(result, WalkForwardResult)
    
    def test_validate_has_windows(self):
        data = generate_test_data(n=300)
        validator = WalkForwardValidator(train_months=1, test_months=1, bars_per_month=60)
        result = validator.validate(data, regime=MarketRegime.RANGING)
        assert len(result.windows) > 0
    
    def test_window_has_required_fields(self):
        data = generate_test_data(n=300)
        validator = WalkForwardValidator(train_months=1, test_months=1, bars_per_month=60)
        result = validator.validate(data, regime=MarketRegime.RANGING)
        
        window = result.windows[0]
        assert isinstance(window, WalkForwardWindow)
        assert hasattr(window, 'train_sharpe')
        assert hasattr(window, 'test_sharpe')
        assert hasattr(window, 'optimized_config')
        assert isinstance(window.optimized_config, IndicatorConfig)
    
    def test_insufficient_data_returns_empty_result(self):
        data = generate_test_data(n=50)
        validator = WalkForwardValidator(train_months=6, test_months=1, bars_per_month=60)
        result = validator.validate(data, regime=MarketRegime.RANGING)
        assert result.passed is False
        assert len(result.windows) == 0
    
    def test_result_has_metadata(self):
        data = generate_test_data(n=300)
        validator = WalkForwardValidator(train_months=1, test_months=1, bars_per_month=60)
        result = validator.validate(data, regime=MarketRegime.RANGING)
        assert 'n_windows' in result.metadata
        assert 'train_bars' in result.metadata
        assert 'test_bars' in result.metadata


class TestABTestRunner:
    def test_run_returns_result(self):
        data = generate_test_data()
        baseline = IndicatorConfig()
        treatment = IndicatorConfig(macd_fast=10, macd_slow=30)
        
        runner = ABTestRunner(baseline, treatment, seed=42)
        result = runner.run(data, n_simulations=30)
        assert isinstance(result, ABTestResult)
    
    def test_result_has_required_fields(self):
        data = generate_test_data()
        baseline = IndicatorConfig()
        treatment = IndicatorConfig()
        
        runner = ABTestRunner(baseline, treatment, seed=42)
        result = runner.run(data, n_simulations=30)
        
        assert hasattr(result, 'baseline_sharpe')
        assert hasattr(result, 'treatment_sharpe')
        assert hasattr(result, 'sharpe_p_value')
        assert hasattr(result, 'treatment_wins')
        assert hasattr(result, 'recommendation')
    
    def test_same_config_inconclusive(self):
        data = generate_test_data()
        config = IndicatorConfig()
        
        runner = ABTestRunner(config, config, seed=42)
        result = runner.run(data, n_simulations=50)
        
        assert result.recommendation == 'inconclusive'
        assert result.treatment_wins is False
    
    def test_result_has_test_date(self):
        data = generate_test_data()
        baseline = IndicatorConfig()
        treatment = IndicatorConfig()
        
        runner = ABTestRunner(baseline, treatment, seed=42)
        result = runner.run(data, n_simulations=30)
        
        assert result.test_date != ''
    
    def test_insufficient_data_returns_inconclusive(self):
        data = generate_test_data(n=30)
        baseline = IndicatorConfig()
        treatment = IndicatorConfig()
        
        runner = ABTestRunner(baseline, treatment, seed=42)
        result = runner.run(data, n_simulations=10)
        
        assert result.recommendation == 'inconclusive'
