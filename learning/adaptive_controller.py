"""
SIQE V3 - Adaptive Controller

Dynamic position sizing and parameter adjustment based on market conditions,
performance history, and regime detection.

Supports ML-driven parameter optimization via pluggable IndicatorOptimizer
implementations (Bayesian, Random Forest, Gaussian Process).
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from strategy_engine.config import IndicatorConfig, MarketRegime, RegimeDetector
from strategy_engine.ml_optimizer import (
    IndicatorOptimizer,
    BayesianOptOptimizer,
    RandomForestTuner,
    GPROptimizer,
)

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive system."""
    # Position sizing
    position_min: float = 0.001  # BTC
    position_max: float = 0.08   # BTC
    base_risk_pct: float = 0.02  # 2% per trade
    
    # Stop loss ATR bounds
    stop_loss_min_atr: float = 0.75
    stop_loss_max_atr: float = 2.5
    stop_loss_default_atr: float = 1.0
    
    # Take profit ATR bounds
    take_profit_min_atr: float = 1.5
    take_profit_max_atr: float = 5.0
    take_profit_default_atr: float = 2.0
    
    # Trailing stop
    trailing_min_atr: float = 0.5
    trailing_max_atr: float = 2.0
    trailing_activate_r: float = 1.0  # R-multiple to activate trailing
    
    # Adaptation parameters
    win_rate_good: float = 0.6
    win_rate_poor: float = 0.4
    sharpe_good: float = 1.5
    sharpe_poor: float = 0.0
    
    # Risk adjustments
    vol_scalar_max: float = 2.0  # Max volatility multiplier
    confidence_scalar_exp: float = 0.5  # Diminishing returns exponent
    
    # ML optimizer settings
    ml_optimizer_enabled: bool = False
    ml_optimizer_type: str = "bayesian"  # bayesian, random_forest, gpr
    ml_optimizer_calls: int = 50  # For Bayesian optimization
    ml_optimizer_samples: int = 100  # For RF and GPR


class AdaptiveController:
    """
    Adaptive controller for dynamic position sizing and parameter adjustment.
    
    Features:
    - Volatility-adjusted position sizing
    - Win rate-based stop loss adaptation
    - Sharpe ratio-based take profit adjustment
    - Regime-aware parameter tuning
    - ML-driven indicator parameter optimization (optional)
    """
    
    def __init__(self, config: Optional[AdaptiveConfig] = None):
        self.config = config or AdaptiveConfig()
        
        # State tracking
        self._recent_returns: list = []
        self._equity_curve: list = []
        self._max_equity = 0.0
        self._current_drawdown = 0.0
        
        # Parameter history for rollback
        self._param_history: list = []
        self._max_history = 10
        
        # ML optimizer
        self._ml_optimizer: Optional[IndicatorOptimizer] = None
        self._price_history: Dict[str, Any] = {}
    
    def set_price_history(self, data: Dict[str, Any]) -> None:
        """Set price history for ML optimization."""
        self._price_history = data
    
    def _get_ml_optimizer(self) -> IndicatorOptimizer:
        """Get or create the ML optimizer based on config."""
        if self._ml_optimizer is not None:
            return self._ml_optimizer
        
        optimizer_type = self.config.ml_optimizer_type.lower()
        
        if optimizer_type == "bayesian":
            self._ml_optimizer = BayesianOptOptimizer(
                n_calls=self.config.ml_optimizer_calls,
                seed=42,
            )
        elif optimizer_type == "random_forest":
            self._ml_optimizer = RandomForestTuner(
                n_estimators=100,
                n_samples=self.config.ml_optimizer_samples,
                seed=42,
            )
        elif optimizer_type == "gpr":
            self._ml_optimizer = GPROptimizer(
                n_samples=self.config.ml_optimizer_samples,
                seed=42,
            )
        else:
            logger.warning(f"Unknown ML optimizer type: {optimizer_type}, using Bayesian")
            self._ml_optimizer = BayesianOptOptimizer(
                n_calls=self.config.ml_optimizer_calls,
                seed=42,
            )
        
        return self._ml_optimizer
    
    def optimize_indicator_params(
        self,
        current_config: IndicatorConfig,
        price_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[IndicatorConfig, Dict[str, float]]:
        """
        Optimize indicator parameters using ML.
        
        Args:
            current_config: Current indicator configuration
            price_data: Optional price data override (uses internal history if None)
            
        Returns:
            Tuple of (optimized config, performance metrics)
        """
        if not self.config.ml_optimizer_enabled:
            logger.debug("ML optimizer disabled, returning current config")
            return current_config, {}
        
        data = price_data if price_data is not None else self._price_history
        if data is None or (hasattr(data, 'empty') and data.empty) or "close" not in data:
            logger.warning("No price data available for ML optimization")
            return current_config, {}
        
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                df = data
            else:
                df = pd.DataFrame(data)
            
            highs = pd.Series(df["high"].values)
            lows = pd.Series(df["low"].values)
            closes = pd.Series(df["close"].values)
            
            regime_result = RegimeDetector.detect(
                highs, lows, closes,
                adx_period=current_config.adx_period,
            )
            
            optimizer = self._get_ml_optimizer()
            optimized_config, metrics = optimizer.optimize(
                current_config, df, regime_result.regime,
            )
            
            self.record_parameter_change(
                "indicator_config",
                current_config.to_dict(),
                optimized_config.to_dict(),
            )
            
            logger.info(
                f"ML optimization complete: regime={regime_result.regime.value}, "
                f"sharpe={metrics.get('sharpe', 0):.3f}"
            )
            
            return optimized_config, metrics
            
        except Exception as e:
            logger.error(f"ML optimization failed: {e}")
            return current_config, {}
    
    def update_equity(self, equity: float) -> None:
        """Update equity curve for drawdown tracking."""
        self._equity_curve.append(equity)
        
        if equity > self._max_equity:
            self._max_equity = equity
        
        if self._max_equity > 0:
            self._current_drawdown = (self._max_equity - equity) / self._max_equity
    
    def update_return(self, return_pct: float) -> None:
        """Add a return to the rolling history."""
        self._recent_returns.append(return_pct)
        if len(self._recent_returns) > 100:
            self._recent_returns.pop(0)
    
    def calculate_win_rate(self) -> float:
        """Calculate rolling win rate."""
        if not self._recent_returns:
            return 0.5  # Default 50%
        
        wins = sum(1 for r in self._recent_returns if r > 0)
        return wins / len(self._recent_returns)
    
    def calculate_sharpe(self, risk_free: float = 0.0) -> float:
        """Calculate rolling Sharpe ratio."""
        if len(self._recent_returns) < 5:
            return 0.0
        
        returns = np.array(self._recent_returns)
        excess_returns = returns - risk_free
        
        mean_return = np.mean(excess_returns)
        std_return = np.std(excess_returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualize
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe
    
    def calculate_position_size(
        self,
        confidence: float,  # 0.0-1.0 from signal strength
        volatility: float,   # ATR / price (normalized)
        price: float,
        regime: str = "MIXED"
    ) -> float:
        """
        Calculate adaptive position size.
        
        Args:
            confidence: Signal confidence (0.0-1.0)
            volatility: Normalized volatility (ATR/price)
            price: Current price
            regime: Market regime (TRENDING, RANGING, VOLATILE, MIXED)
            
        Returns:
            Position size in BTC
        """
        # Volatility scalar - reduce size in high vol
        vol_scalar = min(self.config.vol_scalar_max, 1.0 / (1.0 + volatility * 20))
        
        # Confidence scalar - diminishing returns
        conf_scalar = confidence ** self.config.confidence_scalar_exp
        
        # Win rate adjustment
        win_rate = self.calculate_win_rate()
        if win_rate > self.config.win_rate_good:
            risk_scalar = 1.25  # Increase on hot streak
        elif win_rate < self.config.win_rate_poor:
            risk_scalar = 0.75  # Decrease on cold streak
        else:
            risk_scalar = 1.0
        
        # Regime adjustment
        regime_multipliers = {
            "TRENDING": 1.1,
            "RANGING": 0.9,
            "VOLATILE": 0.7,
            "MIXED": 1.0,
        }
        regime_scalar = regime_multipliers.get(regime.upper(), 1.0)
        
        # Calculate base position
        base_size = self.config.base_risk_pct * self._max_equity if self._max_equity > 0 else 10000
        
        # Position in terms of notional / price
        position_value = base_size * vol_scalar * conf_scalar * risk_scalar * regime_scalar
        
        # Convert to BTC
        position_btc = position_value / price if price > 0 else 0
        
        # Clamp to bounds
        return max(self.config.position_min, min(self.config.position_max, position_btc))
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        win_rate: Optional[float] = None,
        regime: str = "MIXED"
    ) -> float:
        """
        Calculate adaptive stop loss distance.
        
        Args:
            entry_price: Entry price
            atr: Average True Range
            win_rate: Rolling win rate
            regime: Market regime
            
        Returns:
            Stop loss distance from entry (in price units)
        """
        if win_rate is None:
            win_rate = self.calculate_win_rate()
        
        # Regime-based multiplier
        if regime.upper() == "VOLATILE":
            regime_mult = 2.0
        elif regime.upper() == "TRENDING":
            regime_mult = 1.25
        elif regime.upper() == "RANGING":
            regime_mult = 1.0
        else:
            regime_mult = 1.0
        
        # Win rate multiplier
        if win_rate > self.config.win_rate_good:
            win_mult = 0.75  # Tighter on hot streak
        elif win_rate < self.config.win_rate_poor:
            win_mult = 1.5  # Wider on cold streak
        else:
            win_mult = 1.0
        
        # Calculate stop distance
        mult = self.config.stop_loss_default_atr * regime_mult * win_mult
        mult = max(self.config.stop_loss_min_atr, min(self.config.stop_loss_max_atr, mult))
        
        return atr * mult
    
    def calculate_take_profit(
        self,
        entry_price: float,
        atr: float,
        sharpe: Optional[float] = None,
        regime: str = "MIXED"
    ) -> float:
        """
        Calculate adaptive take profit distance.
        
        Args:
            entry_price: Entry price
            atr: Average True Range
            sharpe: Rolling Sharpe ratio
            regime: Market regime
            
        Returns:
            Take profit distance from entry (in price units)
        """
        if sharpe is None:
            sharpe = self.calculate_sharpe()
        
        # Sharpe-based multiplier
        if sharpe > self.config.sharpe_good:
            sharpe_mult = 1.5  # Let winners run
        elif sharpe > self.config.sharpe_poor:
            sharpe_mult = 1.0  # Normal
        else:
            sharpe_mult = 0.75  # Take profit faster
        
        # Regime multiplier
        if regime.upper() == "TRENDING":
            regime_mult = 1.25  # Extend in trends
        elif regime.upper() == "VOLATILE":
            regime_mult = 0.8  # Reduce in volatile
        else:
            regime_mult = 1.0
        
        # Calculate TP distance
        mult = self.config.take_profit_default_atr * sharpe_mult * regime_mult
        mult = max(self.config.take_profit_min_atr, min(self.config.take_profit_max_atr, mult))
        
        return atr * mult
    
    def calculate_trailing_stop(
        self,
        atr: float,
        current_r: float  # Current unrealized P&L in R-multiple
    ) -> float:
        """
        Calculate trailing stop level.
        
        Args:
            atr: Average True Range
            current_r: Current unrealized P&L in R-multiple
            
        Returns:
            Trailing stop level (ATR multiplier) or 0 if not active
        """
        if current_r < self.config.trailing_activate_r:
            return 0.0  # Not yet active
        
        # Trail tighter as profit increases
        if current_r > 3.0:
            mult = self.config.trailing_min_atr
        elif current_r > 2.0:
            mult = self.config.trailing_min_atr * 1.25
        elif current_r > 1.5:
            mult = self.config.trailing_min_atr * 1.5
        else:
            mult = self.config.trailing_min_atr * 2.0
        
        return max(self.config.trailing_min_atr, min(self.config.trailing_max_atr, mult))
    
    def should_reduce_position(self) -> Tuple[bool, str]:
        """
        Check if position size should be reduced based on conditions.
        
        Returns:
            Tuple of (should_reduce, reason)
        """
        # Check drawdown
        if self._current_drawdown > 0.10:
            return True, f"High drawdown: {self._current_drawdown:.1%}"
        
        # Check Sharpe
        sharpe = self.calculate_sharpe()
        if sharpe < -0.5:
            return True, f"Negative Sharpe: {sharpe:.2f}"
        
        # Check consistency
        win_rate = self.calculate_win_rate()
        if win_rate < 0.3 and len(self._recent_returns) > 20:
            return True, f"Low win rate: {win_rate:.1%}"
        
        return False, ""
    
    def get_adaptation_summary(self) -> Dict[str, Any]:
        """Get current adaptation state summary."""
        return {
            "win_rate": self.calculate_win_rate(),
            "sharpe_ratio": self.calculate_sharpe(),
            "current_drawdown": self._current_drawdown,
            "max_equity": self._max_equity,
            "recent_trades": len(self._recent_returns),
            "param_history_size": len(self._param_history),
        }
    
    def record_parameter_change(
        self,
        parameter: str,
        old_value: Any,
        new_value: Any
    ) -> None:
        """Record parameter change for potential rollback."""
        self._param_history.append({
            "parameter": parameter,
            "old_value": old_value,
            "new_value": new_value,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        if len(self._param_history) > self._max_history:
            self._param_history.pop(0)
    
    def rollback_last_change(self) -> Optional[Dict[str, Any]]:
        """Rollback last parameter change."""
        if not self._param_history:
            return None
        
        change = self._param_history.pop()
        return {
            "parameter": change["parameter"],
            "rolled_back_to": change["old_value"],
        }


def create_adaptive_controller(config_dict: Optional[Dict[str, Any]] = None) -> AdaptiveController:
    """Factory function to create AdaptiveController from config."""
    if config_dict is None:
        return AdaptiveController()
    
    config = AdaptiveConfig(
        position_min=config_dict.get("position_min", 0.001),
        position_max=config_dict.get("position_max", 0.08),
        base_risk_pct=config_dict.get("base_risk_pct", 0.02),
        stop_loss_min_atr=config_dict.get("stop_loss_min_atr", 0.75),
        stop_loss_max_atr=config_dict.get("stop_loss_max_atr", 2.5),
        stop_loss_default_atr=config_dict.get("stop_loss_default_atr", 1.0),
        take_profit_min_atr=config_dict.get("take_profit_min_atr", 1.5),
        take_profit_max_atr=config_dict.get("take_profit_max_atr", 5.0),
        take_profit_default_atr=config_dict.get("take_profit_default_atr", 2.0),
        trailing_min_atr=config_dict.get("trailing_min_atr", 0.5),
        trailing_max_atr=config_dict.get("trailing_max_atr", 2.0),
        trailing_activate_r=config_dict.get("trailing_activate_r", 1.0),
        win_rate_good=config_dict.get("win_rate_good", 0.6),
        win_rate_poor=config_dict.get("win_rate_poor", 0.4),
        sharpe_good=config_dict.get("sharpe_good", 1.5),
        sharpe_poor=config_dict.get("sharpe_poor", 0.0),
    )
    
    return AdaptiveController(config)
