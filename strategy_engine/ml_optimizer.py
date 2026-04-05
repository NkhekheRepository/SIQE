"""
SIQE V3 - ML-Driven Indicator Parameter Optimization

Provides ML-based optimization for indicator parameters using:
- Feature engineering pipeline for standardized inputs
- Bayesian optimization (skopt) for efficient parameter search
- Random Forest regression for robust feature importance
- Gaussian Process Regression for uncertainty quantification

All implementations use sklearn ecosystem - no exotic dependencies.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.preprocessing import StandardScaler
from skopt import gp_minimize
from skopt.space import Real, Integer

from strategy_engine.config import (
    IndicatorConfig, MarketRegime, RegimeDetector, IndicatorBounds,
    DirectionalBias, DirectionalBiasDetector,
)

logger = logging.getLogger(__name__)


class FeatureEngineeringPipeline:
    """
    Extracts ML-ready features from price data and indicators.
    
    Features are normalized and standardized for model consumption.
    """
    
    def extract_features(
        self,
        price_data: pd.DataFrame,
        regime: Optional[MarketRegime] = None,
    ) -> pd.DataFrame:
        """
        Extract features from price data.
        
        Args:
            price_data: DataFrame with 'high', 'low', 'close' (and optionally 'volume')
            regime: Pre-computed market regime
            
        Returns:
            DataFrame with normalized features
        """
        closes = price_data["close"]
        highs = price_data["high"]
        lows = price_data["low"]
        
        features = pd.DataFrame(index=closes.index)
        
        # Regime features
        adx_result = RegimeDetector.detect(highs, lows, closes)
        features["adx"] = adx_result.adx
        features["volatility"] = adx_result.volatility
        features["trend_strength"] = adx_result.trend_strength
        
        # Momentum features
        returns = closes.pct_change()
        features["price_momentum_5"] = closes.pct_change(5)
        features["price_momentum_20"] = closes.pct_change(20)
        features["rsi_14"] = self._compute_rsi(closes, 14)
        
        # MACD features
        ema_fast = closes.ewm(span=12, adjust=False).mean()
        ema_slow = closes.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        features["macd_histogram"] = (macd_line - signal_line)
        
        # Volatility features
        atr = self._compute_atr(highs, lows, closes, 14)
        features["atr_ratio"] = atr / closes
        features["bollinger_width"] = self._compute_bollinger_width(closes)
        
        # Volume features (if available)
        if "volume" in price_data.columns:
            vol = price_data["volume"]
            features["volume_ma_ratio"] = vol / vol.rolling(20).mean()
        
        # Regime encoding
        if regime is not None:
            features["regime_trending"] = 1.0 if regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN) else 0.0
            features["regime_ranging"] = 1.0 if regime == MarketRegime.RANGING else 0.0
            features["regime_volatile"] = 1.0 if regime == MarketRegime.VOLATILE else 0.0
            features["regime_quiet"] = 1.0 if regime == MarketRegime.QUIET else 0.0
        
        features = features.dropna()
        return features
    
    def normalize_features(self, features: pd.DataFrame) -> Tuple[pd.DataFrame, StandardScaler]:
        """Z-score normalize features for model input."""
        scaler = StandardScaler()
        normalized = pd.DataFrame(
            scaler.fit_transform(features),
            columns=features.columns,
            index=features.index,
        )
        return normalized, scaler
    
    def _compute_rsi(self, closes: pd.Series, period: int = 14) -> pd.Series:
        """Compute RSI."""
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _compute_atr(self, highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> pd.Series:
        """Compute ATR."""
        high_low = highs - lows
        high_close = (highs.shift(1) - closes).abs()
        low_close = (lows.shift(1) - closes).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(period).mean()
    
    def _compute_bollinger_width(self, closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
        """Compute Bollinger Band width as percentage of price."""
        middle = closes.rolling(period).mean()
        std = closes.rolling(period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return (upper - lower) / middle


class IndicatorOptimizer(ABC):
    """
    Abstract base class for ML-driven indicator parameter optimization.
    
    Subclasses implement specific optimization algorithms (Bayesian,
    Random Forest, Gaussian Process) while maintaining a consistent
    interface for integration with the adaptive system.
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        self._feature_pipeline = FeatureEngineeringPipeline()
    
    @abstractmethod
    def optimize(
        self,
        config: IndicatorConfig,
        market_data: pd.DataFrame,
        regime: MarketRegime,
    ) -> Tuple[IndicatorConfig, Dict[str, float]]:
        """
        Optimize indicator parameters using ML.
        
        Args:
            config: Current indicator configuration
            market_data: Price data with high/low/close columns
            regime: Market regime to optimize for
            
        Returns:
            Tuple of (optimized config, performance metrics)
        """
        pass
    
    @abstractmethod
    def suggest_params(self, regime: MarketRegime) -> Dict[str, Any]:
        """
        Suggest parameters for a given regime.
        
        Args:
            regime: Market regime
            
        Returns:
            Dict of parameter name -> suggested value
        """
        pass
    
    def evaluate(
        self,
        config: IndicatorConfig,
        data: pd.DataFrame,
        bias: Optional[DirectionalBias] = None,
    ) -> Dict[str, float]:
        """
        Evaluate a configuration's performance.
        
        Uses a simple MACD crossover strategy as the evaluation proxy.
        
        Args:
            config: Indicator configuration to evaluate
            data: Price data with close column
            bias: Optional directional bias for asymmetric evaluation
            
        Returns:
            Dict with sharpe, total_return, max_drawdown, win_rate, total_trades
        """
        closes = data["close"]
        
        if len(closes) < config.macd_slow * 3:
            return {
                "sharpe": -10.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
            }
        
        fast_ema = closes.ewm(span=config.macd_fast, adjust=False).mean()
        slow_ema = closes.ewm(span=config.macd_slow, adjust=False).mean()
        
        signals = pd.Series(0, index=closes.index)
        signals[fast_ema > slow_ema] = 1
        signals[fast_ema < slow_ema] = -1
        
        returns = signals.shift(1) * closes.pct_change()
        
        returns = signals.shift(1) * closes.pct_change()
        returns = returns.dropna()
        
        if len(returns) < 30 or returns.std() == 0:
            return {
                "sharpe": -10.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
            }
        
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


class BayesianOptOptimizer(IndicatorOptimizer):
    """
    Bayesian optimization for indicator parameters using skopt.
    
    Uses Gaussian Process-based Bayesian optimization to efficiently
    search the parameter space. Industry standard for hyperparameter
    tuning in quant finance.
    """
    
    def __init__(self, n_calls: int = 50, seed: int = 42):
        super().__init__(seed=seed)
        self.n_calls = n_calls
        self._best_params: Dict[MarketRegime, Dict[str, Any]] = {}
    
    def optimize(
        self,
        config: IndicatorConfig,
        market_data: pd.DataFrame,
        regime: MarketRegime,
        bias: Optional[DirectionalBias] = None,
    ) -> Tuple[IndicatorConfig, Dict[str, float]]:
        """Optimize using Bayesian optimization."""
        param_ranges = self._get_param_ranges(regime, bias)
        
        space = [
            Integer(param_ranges["bollinger_period"][0], param_ranges["bollinger_period"][1], name="bollinger_period"),
            Real(param_ranges["bollinger_std"][0], param_ranges["bollinger_std"][1], name="bollinger_std"),
            Integer(param_ranges["rsi_period"][0], param_ranges["rsi_period"][1], name="rsi_period"),
            Integer(param_ranges["macd_fast"][0], param_ranges["macd_fast"][1], name="macd_fast"),
            Integer(param_ranges["macd_slow"][0], param_ranges["macd_slow"][1], name="macd_slow"),
            Integer(param_ranges["macd_signal"][0], param_ranges["macd_signal"][1], name="macd_signal"),
            Integer(param_ranges["atr_period"][0], param_ranges["atr_period"][1], name="atr_period"),
            Integer(param_ranges["donchian_period"][0], param_ranges["donchian_period"][1], name="donchian_period"),
            Integer(param_ranges["adx_period"][0], param_ranges["adx_period"][1], name="adx_period"),
        ]
        
        def objective(params):
            candidate = {
                "bollinger_period": params[0],
                "bollinger_std": params[1],
                "rsi_period": params[2],
                "macd_fast": params[3],
                "macd_slow": params[4],
                "macd_signal": params[5],
                "atr_period": params[6],
                "donchian_period": params[7],
                "adx_period": params[8],
            }
            try:
                cfg = IndicatorConfig(**candidate)
                metrics = self.evaluate(cfg, market_data, bias=bias)
                return -metrics["sharpe"]
            except Exception:
                return 10.0
        
        result = gp_minimize(
            objective,
            space,
            n_calls=self.n_calls,
            random_state=self.seed,
            n_initial_points=10,
            verbose=False,
        )
        
        best_params = {
            "bollinger_period": int(result.x[0]),
            "bollinger_std": float(result.x[1]),
            "rsi_period": int(result.x[2]),
            "macd_fast": int(result.x[3]),
            "macd_slow": int(result.x[4]),
            "macd_signal": int(result.x[5]),
            "atr_period": int(result.x[6]),
            "donchian_period": int(result.x[7]),
            "adx_period": int(result.x[8]),
        }
        
        try:
            optimized_config = IndicatorConfig(**best_params)
        except Exception:
            optimized_config = config
        
        metrics = self.evaluate(optimized_config, market_data)
        self._best_params[regime] = best_params
        
        logger.info(
            f"Bayesian optimization for {regime.value}: "
            f"Sharpe={metrics['sharpe']:.3f}, Trades={metrics['total_trades']}"
        )
        
        return optimized_config, metrics
    
    def suggest_params(self, regime: MarketRegime) -> Dict[str, Any]:
        """Suggest parameters based on previous optimization."""
        if regime in self._best_params:
            return self._best_params[regime]
        return IndicatorConfig().to_dict()
    
    def _get_param_ranges(self, regime: MarketRegime, bias: Optional[DirectionalBias] = None) -> Dict[str, Tuple]:
        """Get parameter ranges for a regime with optional bias adjustment."""
        ranges = {
            MarketRegime.TRENDING_UP: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.TRENDING_DOWN: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.RANGING: {
                "bollinger_period": (10, 40),
                "bollinger_std": (1.0, 2.5),
                "rsi_period": (5, 20),
                "macd_fast": (5, 15),
                "macd_slow": (20, 40),
                "macd_signal": (5, 12),
                "atr_period": (5, 20),
                "donchian_period": (10, 40),
                "adx_period": (7, 14),
            },
            MarketRegime.VOLATILE: {
                "bollinger_period": (15, 60),
                "bollinger_std": (2.0, 4.0),
                "rsi_period": (10, 30),
                "macd_fast": (10, 25),
                "macd_slow": (25, 80),
                "macd_signal": (7, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 50),
                "adx_period": (10, 20),
            },
            MarketRegime.QUIET: {
                "bollinger_period": (5, 30),
                "bollinger_std": (0.5, 2.0),
                "rsi_period": (5, 15),
                "macd_fast": (5, 12),
                "macd_slow": (20, 30),
                "macd_signal": (5, 10),
                "atr_period": (5, 15),
                "donchian_period": (10, 30),
                "adx_period": (7, 14),
            },
        }
        
        base_ranges = ranges.get(regime, ranges[MarketRegime.RANGING])
        
        if bias == DirectionalBias.BEAR:
            bear_ranges = base_ranges.copy()
            bear_ranges["bollinger_std"] = (1.5, 4.0)
            bear_ranges["atr_period"] = (5, 25)
            bear_ranges["donchian_period"] = (10, 50)
            return bear_ranges
        
        return base_ranges


class RandomForestTuner(IndicatorOptimizer):
    """
    Random Forest regression for indicator parameter tuning.
    
    Trains a Random Forest model to predict Sharpe ratio from
    parameter combinations, then selects the best parameters.
    Robust to noise and provides feature importance.
    """
    
    def __init__(self, n_estimators: int = 100, n_samples: int = 200, seed: int = 42):
        super().__init__(seed=seed)
        self.n_estimators = n_estimators
        self.n_samples = n_samples
        self.rng = np.random.RandomState(seed)
        self._best_params: Dict[MarketRegime, Dict[str, Any]] = {}
        self._feature_importance: Optional[Dict[str, float]] = None
    
    def optimize(
        self,
        config: IndicatorConfig,
        market_data: pd.DataFrame,
        regime: MarketRegime,
        bias: Optional[DirectionalBias] = None,
    ) -> Tuple[IndicatorConfig, Dict[str, float]]:
        """Optimize using Random Forest regression."""
        param_ranges = self._get_param_ranges(regime, bias)
        
        X, y = self._generate_training_data(param_ranges, market_data, bias)
        
        if len(X) < 10:
            return config, self.evaluate(config, market_data, bias=bias)
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        rf = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.seed,
            max_depth=10,
            min_samples_split=5,
        )
        rf.fit(X_scaled, y)
        
        self._feature_importance = dict(zip(
            ["bollinger_period", "bollinger_std", "rsi_period",
             "macd_fast", "macd_slow", "macd_signal",
             "atr_period", "donchian_period", "adx_period"],
            rf.feature_importances_.tolist(),
        ))
        
        best_idx = np.argmax(y)
        best_params = {
            "bollinger_period": int(X[best_idx, 0]),
            "bollinger_std": float(X[best_idx, 1]),
            "rsi_period": int(X[best_idx, 2]),
            "macd_fast": int(X[best_idx, 3]),
            "macd_slow": int(X[best_idx, 4]),
            "macd_signal": int(X[best_idx, 5]),
            "atr_period": int(X[best_idx, 6]),
            "donchian_period": int(X[best_idx, 7]),
            "adx_period": int(X[best_idx, 8]),
        }
        
        try:
            optimized_config = IndicatorConfig(**best_params)
        except Exception:
            optimized_config = config
        
        metrics = self.evaluate(optimized_config, market_data, bias=bias)
        self._best_params[regime] = best_params
        
        logger.info(
            f"RandomForest tuning for {regime.value}: "
            f"Sharpe={metrics['sharpe']:.3f}, Trades={metrics['total_trades']}"
        )
        
        return optimized_config, metrics
    
    def suggest_params(self, regime: MarketRegime) -> Dict[str, Any]:
        """Suggest parameters based on previous tuning."""
        if regime in self._best_params:
            return self._best_params[regime]
        return IndicatorConfig().to_dict()
    
    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Get feature importance from the trained model."""
        return self._feature_importance
    
    def _generate_training_data(
        self,
        param_ranges: Dict[str, Tuple],
        market_data: pd.DataFrame,
        bias: Optional[DirectionalBias] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate random parameter combinations and evaluate them."""
        X = []
        y = []
        
        for _ in range(self.n_samples):
            candidate = {
                "bollinger_period": self.rng.randint(*param_ranges["bollinger_period"]),
                "bollinger_std": self.rng.uniform(*param_ranges["bollinger_std"]),
                "rsi_period": self.rng.randint(*param_ranges["rsi_period"]),
                "macd_fast": self.rng.randint(*param_ranges["macd_fast"]),
                "macd_slow": self.rng.randint(*param_ranges["macd_slow"]),
                "macd_signal": self.rng.randint(*param_ranges["macd_signal"]),
                "atr_period": self.rng.randint(*param_ranges["atr_period"]),
                "donchian_period": self.rng.randint(*param_ranges["donchian_period"]),
                "adx_period": self.rng.randint(*param_ranges["adx_period"]),
            }
            
            try:
                cfg = IndicatorConfig(**candidate)
                metrics = self.evaluate(cfg, market_data, bias=bias)
                X.append(list(candidate.values()))
                y.append(metrics["sharpe"])
            except Exception:
                continue
        
        return np.array(X), np.array(y)
    
    def _get_param_ranges(self, regime: MarketRegime, bias: Optional[DirectionalBias] = None) -> Dict[str, Tuple]:
        """Get parameter ranges for a regime with optional bias adjustment."""
        ranges = {
            MarketRegime.TRENDING_UP: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.TRENDING_DOWN: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.RANGING: {
                "bollinger_period": (10, 40),
                "bollinger_std": (1.0, 2.5),
                "rsi_period": (5, 20),
                "macd_fast": (5, 15),
                "macd_slow": (20, 40),
                "macd_signal": (5, 12),
                "atr_period": (5, 20),
                "donchian_period": (10, 40),
                "adx_period": (7, 14),
            },
            MarketRegime.VOLATILE: {
                "bollinger_period": (15, 60),
                "bollinger_std": (2.0, 4.0),
                "rsi_period": (10, 30),
                "macd_fast": (10, 25),
                "macd_slow": (25, 80),
                "macd_signal": (7, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 50),
                "adx_period": (10, 20),
            },
            MarketRegime.QUIET: {
                "bollinger_period": (5, 30),
                "bollinger_std": (0.5, 2.0),
                "rsi_period": (5, 15),
                "macd_fast": (5, 12),
                "macd_slow": (20, 30),
                "macd_signal": (5, 10),
                "atr_period": (5, 15),
                "donchian_period": (10, 30),
                "adx_period": (7, 14),
            },
        }
        
        base_ranges = ranges.get(regime, ranges[MarketRegime.RANGING])
        
        if bias == DirectionalBias.BEAR:
            bear_ranges = base_ranges.copy()
            bear_ranges["bollinger_std"] = (1.5, 4.0)
            bear_ranges["atr_period"] = (5, 25)
            bear_ranges["donchian_period"] = (10, 50)
            return bear_ranges
        
        return base_ranges


class GPROptimizer(IndicatorOptimizer):
    """
    Gaussian Process Regression for indicator parameter optimization.
    
    Uses GP to model the relationship between parameters and Sharpe ratio,
    providing uncertainty estimates for each prediction. Useful for
    understanding confidence in parameter recommendations.
    """
    
    def __init__(self, n_samples: int = 100, seed: int = 42):
        super().__init__(seed=seed)
        self.n_samples = n_samples
        self.rng = np.random.RandomState(seed)
        self._gp_model: Optional[GaussianProcessRegressor] = None
        self._scaler: Optional[StandardScaler] = None
        self._best_params: Dict[MarketRegime, Dict[str, Any]] = {}
    
    def optimize(
        self,
        config: IndicatorConfig,
        market_data: pd.DataFrame,
        regime: MarketRegime,
        bias: Optional[DirectionalBias] = None,
    ) -> Tuple[IndicatorConfig, Dict[str, float]]:
        """Optimize using Gaussian Process Regression."""
        param_ranges = self._get_param_ranges(regime, bias)
        
        X, y = self._generate_training_data(param_ranges, market_data, bias)
        
        if len(X) < 10:
            return config, self.evaluate(config, market_data, bias=bias)
        
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)
        
        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=0.1)
        
        self._gp_model = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=5,
            random_state=self.seed,
        )
        self._gp_model.fit(X_scaled, y)
        
        grid = self._generate_grid(param_ranges)
        grid_scaled = self._scaler.transform(grid)
        
        predictions = self._gp_model.predict(grid_scaled)
        best_idx = np.argmax(predictions)
        
        best_params = {
            "bollinger_period": int(grid[best_idx, 0]),
            "bollinger_std": float(grid[best_idx, 1]),
            "rsi_period": int(grid[best_idx, 2]),
            "macd_fast": int(grid[best_idx, 3]),
            "macd_slow": int(grid[best_idx, 4]),
            "macd_signal": int(grid[best_idx, 5]),
            "atr_period": int(grid[best_idx, 6]),
            "donchian_period": int(grid[best_idx, 7]),
            "adx_period": int(grid[best_idx, 8]),
        }
        
        try:
            optimized_config = IndicatorConfig(**best_params)
        except Exception:
            optimized_config = config
        
        metrics = self.evaluate(optimized_config, market_data)
        self._best_params[regime] = best_params
        
        logger.info(
            f"GPR optimization for {regime.value}: "
            f"Sharpe={metrics['sharpe']:.3f}, Trades={metrics['total_trades']}"
        )
        
        return optimized_config, metrics
    
    def suggest_params(self, regime: MarketRegime) -> Dict[str, Any]:
        """Suggest parameters based on previous optimization."""
        if regime in self._best_params:
            return self._best_params[regime]
        return IndicatorConfig().to_dict()
    
    def predict_sharpe(self, config: IndicatorConfig) -> Tuple[float, float]:
        """
        Predict Sharpe ratio and uncertainty for a config.
        
        Returns:
            Tuple of (predicted_sharpe, uncertainty_std)
        """
        if self._gp_model is None or self._scaler is None:
            return 0.0, float('inf')
        
        params = np.array([[
            config.bollinger_period, config.bollinger_std,
            config.rsi_period, config.macd_fast, config.macd_slow,
            config.macd_signal, config.atr_period,
            config.donchian_period, config.adx_period,
        ]])
        params_scaled = self._scaler.transform(params)
        
        mean, std = self._gp_model.predict(params_scaled, return_std=True)
        return float(mean[0]), float(std[0])
    
    def _generate_training_data(
        self,
        param_ranges: Dict[str, Tuple],
        market_data: pd.DataFrame,
        bias: Optional[DirectionalBias] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate random parameter combinations and evaluate them."""
        X = []
        y = []
        
        for _ in range(self.n_samples):
            candidate = {
                "bollinger_period": self.rng.randint(*param_ranges["bollinger_period"]),
                "bollinger_std": self.rng.uniform(*param_ranges["bollinger_std"]),
                "rsi_period": self.rng.randint(*param_ranges["rsi_period"]),
                "macd_fast": self.rng.randint(*param_ranges["macd_fast"]),
                "macd_slow": self.rng.randint(*param_ranges["macd_slow"]),
                "macd_signal": self.rng.randint(*param_ranges["macd_signal"]),
                "atr_period": self.rng.randint(*param_ranges["atr_period"]),
                "donchian_period": self.rng.randint(*param_ranges["donchian_period"]),
                "adx_period": self.rng.randint(*param_ranges["adx_period"]),
            }
            
            try:
                cfg = IndicatorConfig(**candidate)
                metrics = self.evaluate(cfg, market_data, bias=bias)
                X.append(list(candidate.values()))
                y.append(metrics["sharpe"])
            except Exception:
                continue
        
        return np.array(X), np.array(y)
    
    def _generate_grid(self, param_ranges: Dict[str, Tuple], resolution: int = 5) -> np.ndarray:
        """Generate a grid of parameter combinations for prediction."""
        from itertools import product
        
        keys = [
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        ]
        
        values = []
        for key in keys:
            min_val, max_val = param_ranges[key]
            if key in ("bollinger_std",):
                step = (max_val - min_val) / resolution
                values.append([round(min_val + i * step, 2) for i in range(resolution + 1)])
            else:
                step = max(1, (max_val - min_val) // resolution)
                values.append(list(range(int(min_val), int(max_val) + 1, step)))
        
        grid = []
        for combo in product(*values):
            grid.append(list(combo))
        
        return np.array(grid)
    
    def _get_param_ranges(self, regime: MarketRegime, bias: Optional[DirectionalBias] = None) -> Dict[str, Tuple]:
        """Get parameter ranges for a regime with optional bias adjustment."""
        ranges = {
            MarketRegime.TRENDING_UP: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.TRENDING_DOWN: {
                "bollinger_period": (10, 50),
                "bollinger_std": (1.5, 3.0),
                "rsi_period": (10, 30),
                "macd_fast": (8, 20),
                "macd_slow": (20, 60),
                "macd_signal": (5, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 60),
                "adx_period": (10, 20),
            },
            MarketRegime.RANGING: {
                "bollinger_period": (10, 40),
                "bollinger_std": (1.0, 2.5),
                "rsi_period": (5, 20),
                "macd_fast": (5, 15),
                "macd_slow": (20, 40),
                "macd_signal": (5, 12),
                "atr_period": (5, 20),
                "donchian_period": (10, 40),
                "adx_period": (7, 14),
            },
            MarketRegime.VOLATILE: {
                "bollinger_period": (15, 60),
                "bollinger_std": (2.0, 4.0),
                "rsi_period": (10, 30),
                "macd_fast": (10, 25),
                "macd_slow": (25, 80),
                "macd_signal": (7, 15),
                "atr_period": (10, 30),
                "donchian_period": (15, 50),
                "adx_period": (10, 20),
            },
            MarketRegime.QUIET: {
                "bollinger_period": (5, 30),
                "bollinger_std": (0.5, 2.0),
                "rsi_period": (5, 15),
                "macd_fast": (5, 12),
                "macd_slow": (20, 30),
                "macd_signal": (5, 10),
                "atr_period": (5, 15),
                "donchian_period": (10, 30),
                "adx_period": (7, 14),
            },
        }
        
        base_ranges = ranges.get(regime, ranges[MarketRegime.RANGING])
        
        if bias == DirectionalBias.BEAR:
            bear_ranges = base_ranges.copy()
            bear_ranges["bollinger_std"] = (1.5, 4.0)
            bear_ranges["atr_period"] = (5, 25)
            bear_ranges["donchian_period"] = (10, 50)
            return bear_ranges
        
        return base_ranges
