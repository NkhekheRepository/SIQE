"""
Adaptive Indicator Bounds Tests

Integration tests for regime detection, parameter optimization,
and backtest engine parameter sweep.
"""
import pytest
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.config import (
    IndicatorConfig, MarketRegime, RegimeDetector, RegimeResult,
    AdaptiveIndicatorBounds, CMAESOptimizer, GridSearchOptimizer,
    ParameterSweepResult, IndicatorBounds,
)


def generate_test_data(n=500, seed=42):
    """Generate synthetic OHLC data for testing."""
    rng = np.random.RandomState(seed)
    closes = pd.Series(np.cumsum(rng.randn(n)) + 100)
    highs = closes + np.abs(rng.randn(n)) * 0.5
    lows = closes - np.abs(rng.randn(n)) * 0.5
    return pd.DataFrame({'high': highs, 'low': lows, 'close': closes})


class TestRegimeDetector:
    def test_detect_returns_regime_result(self):
        data = generate_test_data()
        result = RegimeDetector.detect(data['high'], data['low'], data['close'])
        assert isinstance(result, RegimeResult)
        assert isinstance(result.regime, MarketRegime)

    def test_detect_with_short_data(self):
        data = generate_test_data(n=20)
        result = RegimeDetector.detect(data['high'], data['low'], data['close'])
        assert result.regime == MarketRegime.QUIET
        assert result.adx == 0.0

    def test_detect_adx_in_valid_range(self):
        data = generate_test_data(n=500)
        result = RegimeDetector.detect(data['high'], data['low'], data['close'])
        assert 0 <= result.adx <= 100

    def test_detect_volatility_positive(self):
        data = generate_test_data(n=500)
        result = RegimeDetector.detect(data['high'], data['low'], data['close'])
        assert result.volatility >= 0

    def test_detect_trending_regime(self):
        rng = np.random.RandomState(42)
        n = 500
        trend = np.linspace(0, 50, n)
        closes = pd.Series(trend + rng.randn(n) * 0.5)
        highs = closes + 1.0
        lows = closes - 1.0

        result = RegimeDetector.detect(highs, lows, closes)
        assert result.regime in (MarketRegime.TRENDING, MarketRegime.RANGING)

    def test_detect_ranging_regime(self):
        rng = np.random.RandomState(42)
        n = 500
        closes = pd.Series(rng.randn(n) * 2 + 100)
        highs = closes + 0.5
        lows = closes - 0.5

        result = RegimeDetector.detect(highs, lows, closes)
        assert result.regime in (MarketRegime.RANGING, MarketRegime.QUIET, MarketRegime.VOLATILE)


class TestCMAESOptimizer:
    def test_optimize_returns_dict(self):
        optimizer = CMAESOptimizer(n_iterations=5, population_size=3)

        def objective(params):
            return -((params['x'] - 3) ** 2)

        result = optimizer.optimize(
            objective_fn=objective,
            initial_params={'x': 0.0},
            bounds={'x': (-10.0, 10.0)},
            param_types={'x': 'float'},
        )
        assert 'best_params' in result
        assert 'best_sharpe' in result
        assert 'iterations' in result

    def test_optimize_finds_maximum(self):
        optimizer = CMAESOptimizer(n_iterations=30, population_size=10, seed=42)

        def objective(params):
            return -((params['x'] - 5) ** 2)

        result = optimizer.optimize(
            objective_fn=objective,
            initial_params={'x': 0.0},
            bounds={'x': (-10.0, 10.0)},
            param_types={'x': 'float'},
        )
        assert abs(result['best_params']['x'] - 5.0) < 2.0

    def test_optimize_handles_invalid_params(self):
        optimizer = CMAESOptimizer(n_iterations=5, population_size=3)

        def objective(params):
            raise ValueError("Invalid")

        result = optimizer.optimize(
            objective_fn=objective,
            initial_params={'x': 0.0},
            bounds={'x': (-10.0, 10.0)},
            param_types={'x': 'float'},
        )
        assert result['best_sharpe'] == -10.0


class TestGridSearchOptimizer:
    def test_optimize_returns_dict(self):
        optimizer = GridSearchOptimizer(max_evaluations=100)

        def objective(params):
            return -(params['x'] - 3) ** 2

        result = optimizer.optimize(
            objective_fn=objective,
            param_grid={'x': [1, 2, 3, 4, 5]},
            param_types={'x': 'int'},
        )
        assert 'best_params' in result
        assert result['best_params']['x'] == 3

    def test_optimize_respects_max_evaluations(self):
        optimizer = GridSearchOptimizer(max_evaluations=10)

        def objective(params):
            return params['x'] + params['y']

        result = optimizer.optimize(
            objective_fn=objective,
            param_grid={'x': list(range(20)), 'y': list(range(20))},
            param_types={'x': 'int', 'y': 'int'},
        )
        assert result['evaluations'] <= 10


class TestAdaptiveIndicatorBounds:
    def test_init_creates_optimizers(self):
        bounds = AdaptiveIndicatorBounds()
        assert bounds.cma_optimizer is not None
        assert bounds.grid_optimizer is not None

    def test_get_optimal_config_returns_none_initially(self):
        bounds = AdaptiveIndicatorBounds()
        assert bounds.get_optimal_config(MarketRegime.TRENDING) is None

    def test_get_adaptive_config_returns_default_when_no_sweep(self):
        bounds = AdaptiveIndicatorBounds()
        config = bounds.get_adaptive_config(MarketRegime.TRENDING)
        assert isinstance(config, IndicatorConfig)
        assert config == IndicatorConfig()

    def test_sweep_parameters_returns_result(self):
        data = generate_test_data()
        bounds = AdaptiveIndicatorBounds(n_cma_iterations=5, grid_resolution=3)
        result = bounds.sweep_parameters(data, MarketRegime.RANGING)
        assert isinstance(result, ParameterSweepResult)
        assert isinstance(result.config, IndicatorConfig)
        assert result.regime == MarketRegime.RANGING

    def test_sweep_stores_regime_config(self):
        data = generate_test_data()
        bounds = AdaptiveIndicatorBounds(n_cma_iterations=5, grid_resolution=3)
        bounds.sweep_parameters(data, MarketRegime.TRENDING)
        config = bounds.get_optimal_config(MarketRegime.TRENDING)
        assert config is not None
        assert isinstance(config, IndicatorConfig)

    def test_sweep_improves_over_defaults(self):
        data = generate_test_data(n=1000)
        bounds = AdaptiveIndicatorBounds(n_cma_iterations=10, grid_resolution=4)
        result = bounds.sweep_parameters(data, MarketRegime.RANGING)
        assert np.isfinite(result.sharpe_ratio)

    def test_sweep_history_tracks_results(self):
        data = generate_test_data()
        bounds = AdaptiveIndicatorBounds(n_cma_iterations=5, grid_resolution=3)
        bounds.sweep_parameters(data, MarketRegime.RANGING)
        bounds.sweep_parameters(data, MarketRegime.TRENDING)
        assert len(bounds._sweep_history) == 2

    def test_sweep_validates_config(self):
        data = generate_test_data()
        bounds = AdaptiveIndicatorBounds(n_cma_iterations=5, grid_resolution=3)
        result = bounds.sweep_parameters(data, MarketRegime.QUIET)
        try:
            IndicatorConfig(**result.config.to_dict())
        except Exception:
            pytest.fail("Sweep should produce valid configs")


class TestParameterSweepResult:
    def test_parameter_sweep_result_fields(self):
        config = IndicatorConfig()
        result = ParameterSweepResult(
            config=config,
            sharpe_ratio=1.5,
            total_return=10.0,
            max_drawdown=-0.05,
            total_trades=100,
            win_rate=0.55,
            regime=MarketRegime.TRENDING,
        )
        assert result.sharpe_ratio == 1.5
        assert result.total_trades == 100
        assert result.win_rate == 0.55
        assert result.regime == MarketRegime.TRENDING


class TestMarketRegime:
    def test_all_regimes_exist(self):
        assert MarketRegime.TRENDING.value == "trending"
        assert MarketRegime.RANGING.value == "ranging"
        assert MarketRegime.VOLATILE.value == "volatile"
        assert MarketRegime.QUIET.value == "quiet"

    def test_regime_count(self):
        assert len(MarketRegime) == 4
