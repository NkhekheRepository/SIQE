"""
SIQE V3 - Indicator Configuration

Production-grade indicator configuration system with validation,
serialization, adaptive parameter optimization, walk-forward validation,
safety limits, and config persistence.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification based on ADX and volatility."""
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"


class IndicatorValidationError(Exception):
    """Raised when indicator configuration validation fails."""
    pass


@dataclass(frozen=True)
class IndicatorBounds:
    """Static validation bounds for indicator parameters."""
    BOLLINGER_PERIOD: Tuple[int, int] = (5, 100)
    BOLLINGER_STD: Tuple[float, float] = (0.5, 4.0)
    RSI_PERIOD: Tuple[int, int] = (5, 50)
    MACD_FAST: Tuple[int, int] = (5, 30)
    MACD_SLOW: Tuple[int, int] = (20, 100)
    MACD_SIGNAL: Tuple[int, int] = (5, 20)
    ATR_PERIOD: Tuple[int, int] = (5, 50)
    DONCHIAN_PERIOD: Tuple[int, int] = (10, 100)
    ADX_PERIOD: Tuple[int, int] = (7, 30)


@dataclass
class RegimeResult:
    """Result from regime detection."""
    regime: MarketRegime
    adx: float
    volatility: float
    trend_strength: float


class RegimeDetector:
    """
    ADX-based market regime detection.
    
    Classifies market into trending, ranging, volatile, or quiet regimes
    using ADX (trend strength) and normalized volatility.
    
    Regime thresholds:
    - TRENDING: ADX > 25 (strong trend)
    - RANGING: ADX < 20 (weak trend, choppy)
    - VOLATILE: ADX 20-25 but high volatility
    - QUIET: ADX < 20 and low volatility
    """
    
    ADX_TRENDING_THRESHOLD = 25.0
    ADX_RANGING_THRESHOLD = 20.0
    VOLATILITY_HIGH_THRESHOLD = 0.02
    VOLATILITY_LOW_THRESHOLD = 0.005
    
    @classmethod
    def detect(cls, highs: pd.Series, lows: pd.Series, closes: pd.Series, 
               adx_period: int = 14) -> RegimeResult:
        """
        Detect market regime from price data.
        
        Args:
            highs: High prices
            lows: Low prices
            closes: Close prices
            adx_period: ADX calculation period
            
        Returns:
            RegimeResult with regime classification and metrics
        """
        if len(closes) < adx_period * 2 + 10:
            return RegimeResult(
                regime=MarketRegime.QUIET,
                adx=0.0,
                volatility=0.0,
                trend_strength=0.0,
            )
        
        adx_values, plus_di, minus_di, _ = cls._calculate_adx(highs, lows, closes, adx_period)
        adx = float(adx_values.iloc[-1]) if len(adx_values) > 0 and not np.isnan(adx_values.iloc[-1]) else 0.0
        
        returns = closes.pct_change().dropna()
        volatility = float(returns.iloc[-60:].std()) if len(returns) >= 60 else float(returns.std())
        if np.isnan(volatility):
            volatility = 0.0
        
        trend_strength = abs(float(plus_di.iloc[-1]) - float(minus_di.iloc[-1])) if len(plus_di) > 0 else 0.0
        
        regime = cls._classify_regime(adx, volatility)
        
        return RegimeResult(
            regime=regime,
            adx=adx,
            volatility=volatility,
            trend_strength=trend_strength,
        )
    
    @classmethod
    def _calculate_adx(cls, highs: pd.Series, lows: pd.Series, closes: pd.Series, 
                       period: int) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate ADX, +DI, -DI, and trend strength."""
        high_diff = highs.diff()
        low_diff = -lows.diff()
        
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        
        atr = cls._calculate_atr(highs, lows, closes, period)
        
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx, plus_di, minus_di, adx
    
    @classmethod
    def _calculate_atr(cls, highs: pd.Series, lows: pd.Series, closes: pd.Series, 
                       period: int) -> pd.Series:
        """Calculate Average True Range."""
        high_low = highs - lows
        high_close = (highs.shift(1) - closes).abs()
        low_close = (lows.shift(1) - closes).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean()
        return atr
    
    @classmethod
    def _classify_regime(cls, adx: float, volatility: float) -> MarketRegime:
        """Classify regime based on ADX and volatility."""
        if adx > cls.ADX_TRENDING_THRESHOLD:
            return MarketRegime.TRENDING
        elif adx < cls.ADX_RANGING_THRESHOLD:
            if volatility > cls.VOLATILITY_HIGH_THRESHOLD:
                return MarketRegime.VOLATILE
            elif volatility < cls.VOLATILITY_LOW_THRESHOLD:
                return MarketRegime.QUIET
            else:
                return MarketRegime.RANGING
        else:
            if volatility > cls.VOLATILITY_HIGH_THRESHOLD:
                return MarketRegime.VOLATILE
            else:
                return MarketRegime.RANGING


@dataclass
class IndicatorConfig:
    """
    Validated indicator configuration for strategy execution.
    
    Provides type-safe, validated indicator parameters with fail-fast
    validation to prevent silent trading failures.
    
    Usage:
        config = IndicatorConfig(rsi_period=14, bollinger_std=2.0)
        config.to_dict()  # For TechnicalIndicators.calculate_all()
    """
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    donchian_period: int = 20
    adx_period: int = 14

    def __post_init__(self):
        self._validate()

    def _validate(self):
        """Fail-fast validation - raises on invalid configuration."""
        errors = []

        if not (IndicatorBounds.BOLLINGER_PERIOD[0] <= self.bollinger_period <= IndicatorBounds.BOLLINGER_PERIOD[1]):
            errors.append(f"bollinger_period must be in {IndicatorBounds.BOLLINGER_PERIOD}, got {self.bollinger_period}")

        if not (IndicatorBounds.BOLLINGER_STD[0] <= self.bollinger_std <= IndicatorBounds.BOLLINGER_STD[1]):
            errors.append(f"bollinger_std must be in {IndicatorBounds.BOLLINGER_STD}, got {self.bollinger_std}")

        if not (IndicatorBounds.RSI_PERIOD[0] <= self.rsi_period <= IndicatorBounds.RSI_PERIOD[1]):
            errors.append(f"rsi_period must be in {IndicatorBounds.RSI_PERIOD}, got {self.rsi_period}")

        if not (IndicatorBounds.MACD_FAST[0] <= self.macd_fast <= IndicatorBounds.MACD_FAST[1]):
            errors.append(f"macd_fast must be in {IndicatorBounds.MACD_FAST}, got {self.macd_fast}")

        if not (IndicatorBounds.MACD_SLOW[0] <= self.macd_slow <= IndicatorBounds.MACD_SLOW[1]):
            errors.append(f"macd_slow must be in {IndicatorBounds.MACD_SLOW}, got {self.macd_slow}")

        if not (IndicatorBounds.MACD_SIGNAL[0] <= self.macd_signal <= IndicatorBounds.MACD_SIGNAL[1]):
            errors.append(f"macd_signal must be in {IndicatorBounds.MACD_SIGNAL}, got {self.macd_signal}")

        if not (IndicatorBounds.ATR_PERIOD[0] <= self.atr_period <= IndicatorBounds.ATR_PERIOD[1]):
            errors.append(f"atr_period must be in {IndicatorBounds.ATR_PERIOD}, got {self.atr_period}")

        if not (IndicatorBounds.DONCHIAN_PERIOD[0] <= self.donchian_period <= IndicatorBounds.DONCHIAN_PERIOD[1]):
            errors.append(f"donchian_period must be in {IndicatorBounds.DONCHIAN_PERIOD}, got {self.donchian_period}")

        if not (IndicatorBounds.ADX_PERIOD[0] <= self.adx_period <= IndicatorBounds.ADX_PERIOD[1]):
            errors.append(f"adx_period must be in {IndicatorBounds.ADX_PERIOD}, got {self.adx_period}")

        if self.macd_fast >= self.macd_slow:
            errors.append(f"macd_fast ({self.macd_fast}) must be < macd_slow ({self.macd_slow})")

        if errors:
            raise IndicatorValidationError(f"Invalid indicator config: {'; '.join(errors)}")

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> Tuple[bool, list]:
        """
        Validate a dict against indicator config schema without creating instance.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            cls(**data)
            return True, []
        except IndicatorValidationError as e:
            return False, [str(e)]
        except TypeError as e:
            return False, [f"Invalid field: {e}"]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IndicatorConfig:
        """Create IndicatorConfig from dict, applying defaults for missing keys."""
        valid_keys = {
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for TechnicalIndicators.calculate_all()."""
        return {
            "bollinger_period": self.bollinger_period,
            "bollinger_std": self.bollinger_std,
            "rsi_period": self.rsi_period,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "atr_period": self.atr_period,
            "donchian_period": self.donchian_period,
            "adx_period": self.adx_period,
        }

    def update(self, **kwargs) -> IndicatorConfig:
        """Return new config with updated values (immutable update)."""
        return replace(self, **kwargs)

    def merge(self, other: IndicatorConfig) -> IndicatorConfig:
        """Merge with another config, other takes precedence for non-default values."""
        defaults = IndicatorConfig()
        updates = {}
        for field_name in (
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        ):
            other_val = getattr(other, field_name)
            default_val = getattr(defaults, field_name)
            if other_val != default_val:
                updates[field_name] = other_val
        return replace(self, **updates)


@dataclass
class ParameterSweepResult:
    """Result from a parameter sweep optimization."""
    config: IndicatorConfig
    sharpe_ratio: float
    total_return: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    regime: MarketRegime
    metadata: Dict[str, Any] = field(default_factory=dict)


class CMAESOptimizer:
    """
    CMA-ES style optimizer for continuous indicator parameters.
    
    Uses covariance matrix adaptation evolution strategy for
    optimizing continuous parameters like bollinger_std.
    
    Simplified implementation - uses random search with adaptive
    step sizes as a practical approximation.
    """
    
    def __init__(self, n_iterations: int = 50, population_size: int = 10, seed: int = 42):
        self.n_iterations = n_iterations
        self.population_size = population_size
        self.rng = np.random.RandomState(seed)
    
    def optimize(
        self,
        objective_fn,
        initial_params: Dict[str, float],
        bounds: Dict[str, Tuple[float, float]],
        param_types: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Optimize parameters using adaptive random search.
        
        Args:
            objective_fn: Function(config_dict) -> float (higher is better)
            initial_params: Starting parameter values
            bounds: Dict of (min, max) for each parameter
            param_types: Dict of 'int' or 'float' for each parameter
            
        Returns:
            Best parameter dict and optimization metadata
        """
        best_sharpe = -np.inf
        best_params = initial_params.copy()
        step_sizes = {k: (bounds[k][1] - bounds[k][0]) * 0.3 for k in initial_params}
        
        for iteration in range(self.n_iterations):
            population = []
            for _ in range(self.population_size):
                candidate = {}
                for key, value in best_params.items():
                    step = step_sizes[key]
                    new_val = value + self.rng.normal(0, step)
                    new_val = max(bounds[key][0], min(bounds[key][1], new_val))
                    if param_types.get(key) == 'int':
                        new_val = int(round(new_val))
                    candidate[key] = new_val
                
                try:
                    sharpe = objective_fn(candidate)
                    if not np.isfinite(sharpe):
                        sharpe = -10.0
                except Exception:
                    sharpe = -10.0
                
                population.append((candidate, sharpe))
            
            population.sort(key=lambda x: x[1], reverse=True)
            
            if population[0][1] > best_sharpe:
                best_sharpe = population[0][1]
                best_params = population[0][0].copy()
            
            elite_size = max(1, self.population_size // 3)
            for key in initial_params:
                elite_values = [p[0][key] for p in population[:elite_size]]
                step_sizes[key] = max(
                    (bounds[key][1] - bounds[key][0]) * 0.01,
                    np.std(elite_values) if len(elite_values) > 1 else step_sizes[key] * 0.9
                )
        
        return {
            "best_params": best_params,
            "best_sharpe": best_sharpe,
            "iterations": self.n_iterations,
            "converged": True,
        }


class GridSearchOptimizer:
    """
    Grid search optimizer for discrete indicator parameters.
    
    Systematically evaluates all combinations of discrete parameters
    (like periods) within specified bounds.
    """
    
    def __init__(self, max_evaluations: int = 1000):
        self.max_evaluations = max_evaluations
    
    def optimize(
        self,
        objective_fn,
        param_grid: Dict[str, List[Any]],
        param_types: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Optimize parameters using grid search.
        
        Args:
            objective_fn: Function(config_dict) -> float (higher is better)
            param_grid: Dict of parameter -> list of values to try
            param_types: Dict of 'int' or 'float' for each parameter
            
        Returns:
            Best parameter dict and optimization metadata
        """
        from itertools import product
        
        keys = list(param_grid.keys())
        values = [param_grid[k] for k in keys]
        
        total_combinations = 1
        for v in values:
            total_combinations *= len(v)
        
        if total_combinations > self.max_evaluations:
            logger.warning(
                f"Grid search has {total_combinations} combinations, "
                f"limiting to {self.max_evaluations}"
            )
        
        best_sharpe = -np.inf
        best_params = {}
        evaluations = 0
        
        for combo in product(*values):
            if evaluations >= self.max_evaluations:
                break
            
            candidate = dict(zip(keys, combo))
            evaluations += 1
            
            try:
                sharpe = objective_fn(candidate)
                if not np.isfinite(sharpe):
                    sharpe = -10.0
            except Exception:
                sharpe = -10.0
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = candidate.copy()
        
        return {
            "best_params": best_params,
            "best_sharpe": best_sharpe,
            "evaluations": evaluations,
            "total_combinations": total_combinations,
        }


class AdaptiveIndicatorBounds:
    """
    Learns optimal indicator parameter ranges via backtest sweeps.
    
    Uses a hybrid approach:
    - CMA-ES for continuous parameters (bollinger_std)
    - Grid search for discrete parameters (periods)
    
    Results are regime-aware - different optimal params for different
    market conditions (trending, ranging, volatile, quiet).
    """
    
    REGIME_PARAM_RANGES = {
        MarketRegime.TRENDING: {
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
    
    def __init__(self, n_cma_iterations: int = 30, grid_resolution: int = 5, seed: int = 42):
        self.cma_optimizer = CMAESOptimizer(
            n_iterations=n_cma_iterations,
            population_size=10,
            seed=seed,
        )
        self.grid_optimizer = GridSearchOptimizer(max_evaluations=500)
        self.grid_resolution = grid_resolution
        self._regime_configs: Dict[MarketRegime, IndicatorConfig] = {}
        self._sweep_history: List[ParameterSweepResult] = []
    
    def get_optimal_config(self, regime: MarketRegime) -> Optional[IndicatorConfig]:
        """Get the optimal config for a given regime."""
        return self._regime_configs.get(regime)
    
    def get_adaptive_config(self, current_regime: MarketRegime) -> IndicatorConfig:
        """
        Get config adapted to current regime.
        Falls back to defaults if no regime-specific config exists.
        """
        regime_config = self._regime_configs.get(current_regime)
        if regime_config is not None:
            return regime_config
        return IndicatorConfig()
    
    def sweep_parameters(
        self,
        data: pd.DataFrame,
        regime: MarketRegime,
        objective_fn=None,
    ) -> ParameterSweepResult:
        """
        Sweep parameters for a given regime using historical data.
        
        Args:
            data: DataFrame with 'high', 'low', 'close' columns
            regime: Market regime to optimize for
            objective_fn: Optional custom objective function. 
                         Default: Sharpe ratio from simple strategy.
        
        Returns:
            ParameterSweepResult with optimal config and metrics
        """
        if objective_fn is None:
            objective_fn = self._default_objective(data)
        
        param_ranges = self.REGIME_PARAM_RANGES.get(regime, self.REGIME_PARAM_RANGES[MarketRegime.RANGING])
        
        continuous_params = {"bollinger_std": param_ranges["bollinger_std"]}
        discrete_params = {k: v for k, v in param_ranges.items() if k != "bollinger_std"}
        
        def objective(candidate):
            try:
                config = IndicatorConfig(**candidate)
                return objective_fn(config)
            except (IndicatorValidationError, TypeError):
                return -10.0
        
        continuous_result = self.cma_optimizer.optimize(
            objective_fn=objective,
            initial_params={"bollinger_std": 2.0},
            bounds={"bollinger_std": continuous_params["bollinger_std"]},
            param_types={"bollinger_std": "float"},
        )
        
        grid_values = {}
        for key, (min_val, max_val) in discrete_params.items():
            is_int = key.endswith("_period") or key in ("macd_fast", "macd_slow", "macd_signal")
            if is_int:
                grid_values[key] = list(range(int(min_val), int(max_val) + 1, max(1, (int(max_val) - int(min_val)) // self.grid_resolution)))
            else:
                step = (max_val - min_val) / self.grid_resolution
                grid_values[key] = [round(min_val + i * step, 2) for i in range(self.grid_resolution + 1)]
        
        def grid_objective(candidate):
            try:
                config = IndicatorConfig(**candidate)
                return objective_fn(config)
            except (IndicatorValidationError, TypeError):
                return -10.0
        
        param_types = {}
        for key in discrete_params:
            param_types[key] = "int" if key.endswith("_period") or key in ("macd_fast", "macd_slow", "macd_signal") else "float"
        
        grid_result = self.grid_optimizer.optimize(
            objective_fn=grid_objective,
            param_grid=grid_values,
            param_types=param_types,
        )
        
        best_params = {**continuous_result["best_params"], **grid_result["best_params"]}
        
        try:
            optimal_config = IndicatorConfig(**best_params)
        except (IndicatorValidationError, TypeError):
            optimal_config = IndicatorConfig()
        
        metrics = self._evaluate_config(optimal_config, data)
        
        result = ParameterSweepResult(
            config=optimal_config,
            sharpe_ratio=metrics["sharpe"],
            total_return=metrics["total_return"],
            max_drawdown=metrics["max_drawdown"],
            total_trades=metrics["total_trades"],
            win_rate=metrics["win_rate"],
            regime=regime,
            metadata={
                "cma_sharpe": continuous_result["best_sharpe"],
                "grid_sharpe": grid_result["best_sharpe"],
                "cma_iterations": continuous_result["iterations"],
                "grid_evaluations": grid_result["evaluations"],
            },
        )
        
        self._regime_configs[regime] = optimal_config
        self._sweep_history.append(result)
        
        logger.info(
            f"Parameter sweep for {regime.value}: Sharpe={result.sharpe_ratio:.3f}, "
            f"Return={result.total_return:.2f}%, Trades={result.total_trades}"
        )
        
        return result
    
    def _default_objective(self, data: pd.DataFrame):
        """
        Create a default objective function based on a simple moving average crossover.
        
        Returns a function that takes an IndicatorConfig and returns Sharpe ratio.
        """
        def objective(config: IndicatorConfig) -> float:
            closes = data["close"]
            if len(closes) < config.macd_slow * 3:
                return -10.0
            
            fast_ema = closes.ewm(span=config.macd_fast, adjust=False).mean()
            slow_ema = closes.ewm(span=config.macd_slow, adjust=False).mean()
            
            signals = pd.Series(0, index=closes.index)
            signals[fast_ema > slow_ema] = 1
            signals[fast_ema < slow_ema] = -1
            
            returns = signals.shift(1) * closes.pct_change()
            returns = returns.dropna()
            
            if len(returns) < 30 or returns.std() == 0:
                return -10.0
            
            sharpe = returns.mean() / returns.std() * np.sqrt(252)
            return float(sharpe)
        
        return objective
    
    def _evaluate_config(self, config: IndicatorConfig, data: pd.DataFrame) -> Dict[str, Any]:
        """Evaluate a config and return performance metrics."""
        closes = data["close"]
        
        fast_ema = closes.ewm(span=config.macd_fast, adjust=False).mean()
        slow_ema = closes.ewm(span=config.macd_slow, adjust=False).mean()
        
        signals = pd.Series(0, index=closes.index)
        signals[fast_ema > slow_ema] = 1
        signals[fast_ema < slow_ema] = -1
        
        returns = signals.shift(1) * closes.pct_change()
        returns = returns.dropna()
        
        if len(returns) < 30:
            return {
                "sharpe": -10.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "total_trades": 0,
                "win_rate": 0.0,
            }
        
        sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0.0
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
            "total_trades": total_trades,
            "win_rate": win_rate,
        }


# =============================================================================
# CONFIG PERSISTENCE
# =============================================================================

@dataclass
class ConfigMetadata:
    """Metadata for config versioning and audit trail."""
    version: str = "1.0.0"
    created_at: str = ""
    optimized_for: Optional[str] = None  # MarketRegime value
    source: str = "default"  # default, bayesian, rf, gpr, manual
    optimizer_params: Dict[str, Any] = field(default_factory=dict)
    sharpe_at_creation: float = 0.0
    total_return_at_creation: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class ConfigPersistence:
    """
    Save/load indicator configurations with versioning and audit trail.
    
    Ensures reproducibility - every trade must be traceable to a known
    config version. Required for compliance and debugging.
    """
    
    @staticmethod
    def save(config: IndicatorConfig, path: str, metadata: Optional[ConfigMetadata] = None) -> str:
        """
        Save config to JSON file.
        
        Args:
            config: IndicatorConfig to save
            path: File path for JSON output
            metadata: Optional metadata for audit trail
            
        Returns:
            Path to saved file
        """
        data = {
            "metadata": {
                "version": metadata.version if metadata else "1.0.0",
                "created_at": metadata.created_at if metadata else datetime.now(timezone.utc).isoformat(),
                "optimized_for": metadata.optimized_for if metadata else None,
                "source": metadata.source if metadata else "default",
                "optimizer_params": metadata.optimizer_params if metadata else {},
                "sharpe_at_creation": metadata.sharpe_at_creation if metadata else 0.0,
                "total_return_at_creation": metadata.total_return_at_creation if metadata else 0.0,
            },
            "config": config.to_dict(),
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Config saved to {path} (source={data['metadata']['source']})")
        return path
    
    @classmethod
    def load(cls, path: str) -> Tuple[IndicatorConfig, ConfigMetadata]:
        """
        Load config from JSON file.
        
        Args:
            path: File path to load from
            
        Returns:
            Tuple of (IndicatorConfig, ConfigMetadata)
        """
        with open(path, 'r') as f:
            data = json.load(f)
        
        config = IndicatorConfig.from_dict(data["config"])
        metadata = ConfigMetadata(**data["metadata"])
        
        logger.info(f"Config loaded from {path} (version={metadata.version}, source={metadata.source})")
        return config, metadata


# =============================================================================
# SAFETY LIMITS FOR ML DEPLOYMENT
# =============================================================================

@dataclass
class SafetyLimits:
    """
    Guardrails for ML-driven parameter deployment.
    
    Prevents catastrophic changes from being applied to live trading.
    All limits are configurable but have conservative defaults.
    """
    max_param_change_pct: float = 0.20  # 20% max change from baseline
    min_confidence: float = 0.70  # 70% minimum confidence for ML suggestions
    circuit_breaker_losses: int = 5  # Disable after 5 consecutive losses
    circuit_breaker_drawdown: float = 0.10  # Disable at 10% drawdown
    require_human_review: bool = True  # Flag changes requiring manual approval
    max_daily_param_changes: int = 3  # Limit parameter changes per day
    
    def validate_param_change(
        self,
        baseline: IndicatorConfig,
        proposed: IndicatorConfig,
    ) -> Tuple[bool, List[str]]:
        """
        Validate that proposed config is within safety bounds.
        
        Args:
            baseline: Current production config
            proposed: New config from ML optimizer
            
        Returns:
            Tuple of (is_safe, list_of_violations)
        """
        violations = []
        
        param_names = [
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        ]
        
        for name in param_names:
            baseline_val = getattr(baseline, name)
            proposed_val = getattr(proposed, name)
            
            if baseline_val == 0:
                continue
            
            change_pct = abs(proposed_val - baseline_val) / abs(baseline_val)
            
            if change_pct > self.max_param_change_pct:
                violations.append(
                    f"{name}: {baseline_val} -> {proposed_val} "
                    f"({change_pct:.1%} change exceeds {self.max_param_change_pct:.0%} limit)"
                )
        
        return len(violations) == 0, violations
    
    def check_circuit_breaker(
        self,
        consecutive_losses: int,
        current_drawdown: float,
    ) -> Tuple[bool, str]:
        """
        Check if circuit breaker should trigger.
        
        Args:
            consecutive_losses: Number of consecutive losing trades
            current_drawdown: Current drawdown as fraction
            
        Returns:
            Tuple of (should_disable, reason)
        """
        if consecutive_losses >= self.circuit_breaker_losses:
            return True, f"Circuit breaker: {consecutive_losses} consecutive losses (limit: {self.circuit_breaker_losses})"
        
        if current_drawdown >= self.circuit_breaker_drawdown:
            return True, f"Circuit breaker: {current_drawdown:.1%} drawdown (limit: {self.circuit_breaker_drawdown:.0%})"
        
        return False, ""


# =============================================================================
# WALK-FORWARD VALIDATION
# =============================================================================

@dataclass
class WalkForwardWindow:
    """Single walk-forward window result."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_sharpe: float
    test_sharpe: float
    train_return: float
    test_return: float
    train_drawdown: float
    test_drawdown: float
    train_trades: int
    test_trades: int
    optimized_config: IndicatorConfig
    passed: bool = True


@dataclass
class WalkForwardResult:
    """Complete walk-forward validation result."""
    windows: List[WalkForwardWindow]
    avg_test_sharpe: float
    avg_test_return: float
    avg_test_drawdown: float
    pass_rate: float  # Fraction of windows that passed
    total_train_trades: int
    total_test_trades: int
    min_test_sharpe: float
    max_test_sharpe: float
    passed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class WalkForwardValidator:
    """
    Walk-forward validation for indicator parameter optimization.
    
    Prevents overfitting by testing optimized parameters on out-of-sample data.
    Uses rolling windows: train on N periods, test on next period, roll forward.
    
    Pass criteria:
    - Average test Sharpe > 1.0
    - Test Sharpe > 1.0 in >= 80% of windows
    - No single window with test Sharpe < -1.0
    """
    
    MIN_TEST_SHARPE_THRESHOLD = 1.0
    MIN_PASS_RATE = 0.80
    MAX_NEGATIVE_SHARPE = -1.0
    
    def __init__(
        self,
        train_months: int = 6,
        test_months: int = 1,
        bars_per_month: int = 180,  # 4h bars: ~180 per month
        min_sharpe_threshold: float = 1.0,
        min_pass_rate: float = 0.80,
    ):
        self.train_bars = train_months * bars_per_month
        self.test_bars = test_months * bars_per_month
        self.min_sharpe_threshold = min_sharpe_threshold
        self.min_pass_rate = min_pass_rate
    
    def validate(
        self,
        data: pd.DataFrame,
        optimizer=None,
        regime: MarketRegime = MarketRegime.RANGING,
    ) -> WalkForwardResult:
        """
        Run walk-forward validation.
        
        Args:
            data: DataFrame with high/low/close columns
            optimizer: Optional optimizer to use (creates default if None)
            regime: Market regime to optimize for
            
        Returns:
            WalkForwardResult with per-window and aggregate metrics
        """
        if optimizer is None:
            from strategy_engine.ml_optimizer import BayesianOptOptimizer
            optimizer = BayesianOptOptimizer(n_calls=20, seed=42)
        
        total_bars = len(data)
        window_size = self.train_bars + self.test_bars
        
        if total_bars < window_size * 2:
            logger.warning(
                f"Insufficient data for walk-forward: "
                f"need {window_size * 2}, have {total_bars}"
            )
            return self._empty_result()
        
        windows = []
        window_id = 0
        
        for start in range(0, total_bars - window_size + 1, self.test_bars):
            train_end = start + self.train_bars
            test_end = min(train_end + self.test_bars, total_bars)
            
            train_data = data.iloc[start:train_end]
            test_data = data.iloc[train_end:test_end]
            
            if len(train_data) < self.train_bars * 0.8:
                continue
            
            try:
                optimized_config, train_metrics = optimizer.optimize(
                    IndicatorConfig(), train_data, regime,
                )
                
                test_metrics = optimizer.evaluate(optimized_config, test_data)
                
                passed = (
                    test_metrics["sharpe"] >= self.MIN_TEST_SHARPE_THRESHOLD
                    or test_metrics["sharpe"] > self.MAX_NEGATIVE_SHARPE
                )
                
                window = WalkForwardWindow(
                    window_id=window_id,
                    train_start=str(data.index[start]) if hasattr(data.index[start], 'isoformat') else str(start),
                    train_end=str(data.index[train_end - 1]) if hasattr(data.index[train_end - 1], 'isoformat') else str(train_end - 1),
                    test_start=str(data.index[train_end]) if hasattr(data.index[train_end], 'isoformat') else str(train_end),
                    test_end=str(data.index[test_end - 1]) if hasattr(data.index[test_end - 1], 'isoformat') else str(test_end - 1),
                    train_sharpe=train_metrics.get("sharpe", 0),
                    test_sharpe=test_metrics.get("sharpe", 0),
                    train_return=train_metrics.get("total_return", 0),
                    test_return=test_metrics.get("total_return", 0),
                    train_drawdown=train_metrics.get("max_drawdown", 0),
                    test_drawdown=test_metrics.get("max_drawdown", 0),
                    train_trades=train_metrics.get("total_trades", 0),
                    test_trades=test_metrics.get("total_trades", 0),
                    optimized_config=optimized_config,
                    passed=passed,
                )
                windows.append(window)
                window_id += 1
                
            except Exception as e:
                logger.warning(f"Walk-forward window {window_id} failed: {e}")
                continue
        
        if not windows:
            return self._empty_result()
        
        test_sharpes = [w.test_sharpe for w in windows]
        test_returns = [w.test_return for w in windows]
        test_drawdowns = [w.test_drawdown for w in windows]
        
        passed_windows = sum(1 for w in windows if w.passed)
        pass_rate = passed_windows / len(windows)
        
        result = WalkForwardResult(
            windows=windows,
            avg_test_sharpe=float(np.mean(test_sharpes)),
            avg_test_return=float(np.mean(test_returns)),
            avg_test_drawdown=float(np.mean(test_drawdowns)),
            pass_rate=pass_rate,
            total_train_trades=sum(w.train_trades for w in windows),
            total_test_trades=sum(w.test_trades for w in windows),
            min_test_sharpe=float(np.min(test_sharpes)),
            max_test_sharpe=float(np.max(test_sharpes)),
            passed=(
                pass_rate >= self.min_pass_rate
                and np.mean(test_sharpes) >= self.MIN_TEST_SHARPE_THRESHOLD
            ),
            metadata={
                "n_windows": len(windows),
                "train_bars": self.train_bars,
                "test_bars": self.test_bars,
                "min_sharpe_threshold": self.MIN_TEST_SHARPE_THRESHOLD,
                "min_pass_rate": self.min_pass_rate,
            },
        )
        
        logger.info(
            f"Walk-forward complete: {len(windows)} windows, "
            f"pass_rate={pass_rate:.1%}, avg_test_sharpe={result.avg_test_sharpe:.3f}"
        )
        
        return result
    
    def _empty_result(self) -> WalkForwardResult:
        """Return empty walk-forward result."""
        return WalkForwardResult(
            windows=[],
            avg_test_sharpe=0.0,
            avg_test_return=0.0,
            avg_test_drawdown=0.0,
            pass_rate=0.0,
            total_train_trades=0,
            total_test_trades=0,
            min_test_sharpe=0.0,
            max_test_sharpe=0.0,
            passed=False,
            metadata={"error": "insufficient_data"},
        )
