"""
ML Optimizer Tests

Tests for ML-driven indicator parameter optimization including:
- Feature engineering pipeline
- Bayesian optimization
- Random Forest tuning
- Gaussian Process optimization
- Integration with AdaptiveController
"""
import pytest
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.config import IndicatorConfig, MarketRegime
from strategy_engine.ml_optimizer import (
    FeatureEngineeringPipeline,
    IndicatorOptimizer,
    BayesianOptOptimizer,
    RandomForestTuner,
    GPROptimizer,
)
from learning.adaptive_controller import AdaptiveController, AdaptiveConfig


def generate_test_data(n=300, seed=42):
    """Generate synthetic OHLC data for testing."""
    rng = np.random.RandomState(seed)
    closes = pd.Series(np.cumsum(rng.randn(n)) + 100)
    highs = closes + np.abs(rng.randn(n)) * 0.5
    lows = closes - np.abs(rng.randn(n)) * 0.5
    return pd.DataFrame({'high': highs, 'low': lows, 'close': closes})


class TestFeatureEngineeringPipeline:
    def test_extract_features_returns_dataframe(self):
        data = generate_test_data()
        pipeline = FeatureEngineeringPipeline()
        features = pipeline.extract_features(data)
        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0

    def test_extract_features_contains_expected_columns(self):
        data = generate_test_data()
        pipeline = FeatureEngineeringPipeline()
        features = pipeline.extract_features(data)
        expected_cols = {'adx', 'volatility', 'trend_strength', 'rsi_14', 'macd_histogram'}
        assert expected_cols.issubset(set(features.columns))

    def test_extract_features_with_regime(self):
        data = generate_test_data()
        pipeline = FeatureEngineeringPipeline()
        features = pipeline.extract_features(data, regime=MarketRegime.TRENDING)
        assert 'regime_trending' in features.columns
        assert 'regime_ranging' in features.columns

    def test_normalize_features_returns_scaled_data(self):
        data = generate_test_data()
        pipeline = FeatureEngineeringPipeline()
        features = pipeline.extract_features(data)
        normalized, scaler = pipeline.normalize_features(features)
        assert isinstance(normalized, pd.DataFrame)
        assert normalized.shape == features.shape

    def test_normalize_features_zero_mean_unit_var(self):
        data = generate_test_data(n=500)
        pipeline = FeatureEngineeringPipeline()
        features = pipeline.extract_features(data)
        normalized, scaler = pipeline.normalize_features(features)
        assert abs(normalized.mean().mean()) < 0.01


class TestBayesianOptOptimizer:
    def test_optimize_returns_config_and_metrics(self):
        data = generate_test_data()
        optimizer = BayesianOptOptimizer(n_calls=10)
        config, metrics = optimizer.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        assert isinstance(config, IndicatorConfig)
        assert isinstance(metrics, dict)
        assert 'sharpe' in metrics

    def test_suggest_params_returns_dict(self):
        data = generate_test_data()
        optimizer = BayesianOptOptimizer(n_calls=10)
        optimizer.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        params = optimizer.suggest_params(MarketRegime.RANGING)
        assert isinstance(params, dict)
        assert 'bollinger_period' in params

    def test_suggest_params_returns_default_before_optimize(self):
        optimizer = BayesianOptOptimizer()
        params = optimizer.suggest_params(MarketRegime.QUIET)
        assert isinstance(params, dict)

    def test_evaluate_returns_metrics(self):
        optimizer = BayesianOptOptimizer()
        data = generate_test_data()
        metrics = optimizer.evaluate(IndicatorConfig(), data)
        assert 'sharpe' in metrics
        assert 'total_return' in metrics
        assert 'max_drawdown' in metrics
        assert 'win_rate' in metrics
        assert 'total_trades' in metrics


class TestRandomForestTuner:
    def test_optimize_returns_config_and_metrics(self):
        data = generate_test_data()
        tuner = RandomForestTuner(n_estimators=30, n_samples=30)
        config, metrics = tuner.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        assert isinstance(config, IndicatorConfig)
        assert isinstance(metrics, dict)

    def test_feature_importance_available_after_optimize(self):
        data = generate_test_data()
        tuner = RandomForestTuner(n_estimators=30, n_samples=30)
        tuner.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        importance = tuner.get_feature_importance()
        assert importance is not None
        assert isinstance(importance, dict)
        assert 'macd_slow' in importance

    def test_suggest_params_returns_dict(self):
        data = generate_test_data()
        tuner = RandomForestTuner(n_estimators=30, n_samples=30)
        tuner.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        params = tuner.suggest_params(MarketRegime.RANGING)
        assert isinstance(params, dict)

    def test_feature_importance_none_before_optimize(self):
        tuner = RandomForestTuner()
        assert tuner.get_feature_importance() is None


class TestGPROptimizer:
    def test_optimize_returns_config_and_metrics(self):
        data = generate_test_data()
        optimizer = GPROptimizer(n_samples=30)
        config, metrics = optimizer.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        assert isinstance(config, IndicatorConfig)
        assert isinstance(metrics, dict)

    def test_predict_sharpe_returns_tuple(self):
        data = generate_test_data()
        optimizer = GPROptimizer(n_samples=30)
        optimizer.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        predicted_sharpe, uncertainty = optimizer.predict_sharpe(IndicatorConfig())
        assert isinstance(predicted_sharpe, float)
        assert isinstance(uncertainty, float)

    def test_predict_sharpe_returns_inf_before_fit(self):
        optimizer = GPROptimizer()
        predicted_sharpe, uncertainty = optimizer.predict_sharpe(IndicatorConfig())
        assert uncertainty == float('inf')

    def test_suggest_params_returns_dict(self):
        data = generate_test_data()
        optimizer = GPROptimizer(n_samples=30)
        optimizer.optimize(IndicatorConfig(), data, MarketRegime.RANGING)
        params = optimizer.suggest_params(MarketRegime.RANGING)
        assert isinstance(params, dict)


class TestMLIntegrationWithAdaptiveController:
    def test_optimize_disabled_returns_current_config(self):
        controller = AdaptiveController()
        config = IndicatorConfig()
        result, metrics = controller.optimize_indicator_params(config)
        assert result == config
        assert metrics == {}

    def test_optimize_with_ml_enabled(self):
        data = generate_test_data()
        ml_config = AdaptiveConfig(
            ml_optimizer_enabled=True,
            ml_optimizer_type='random_forest',
            ml_optimizer_samples=30,
        )
        controller = AdaptiveController(ml_config)
        controller.set_price_history(data)
        result, metrics = controller.optimize_indicator_params(IndicatorConfig())
        assert isinstance(result, IndicatorConfig)
        assert 'sharpe' in metrics

    def test_optimize_without_price_data_returns_current(self):
        ml_config = AdaptiveConfig(ml_optimizer_enabled=True)
        controller = AdaptiveController(ml_config)
        config = IndicatorConfig()
        result, metrics = controller.optimize_indicator_params(config)
        assert result == config

    def test_optimize_with_override_data(self):
        data = generate_test_data()
        ml_config = AdaptiveConfig(
            ml_optimizer_enabled=True,
            ml_optimizer_type='bayesian',
            ml_optimizer_calls=10,
        )
        controller = AdaptiveController(ml_config)
        result, metrics = controller.optimize_indicator_params(IndicatorConfig(), price_data=data)
        assert isinstance(result, IndicatorConfig)
        assert 'sharpe' in metrics
