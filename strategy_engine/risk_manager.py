"""
SIQE V3 - Portfolio Risk Manager

Production-grade risk management with:
- VaR-based position limits
- Drawdown gates (3-stage)
- Correlation-based exposure limits
- Confidence-based sizing modulation

All risk controls are enforced before any position is opened.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

from strategy_engine.position_sizer import PositionSize, KellySizer, RiskParitySizer, MaxLimitSizer

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class RiskMetrics:
    """Current portfolio risk metrics."""
    current_drawdown: float
    var_95: float
    var_99: float
    sharpe_ratio: float
    volatility: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    risk_level: RiskLevel
    warnings: List[str] = field(default_factory=list)


@dataclass
class DrawdownGate:
    """Three-stage drawdown gate system."""
    stage1_threshold: float = 0.05
    stage2_threshold: float = 0.10
    stage3_threshold: float = 0.15
    
    stage1_action: str = "reduce_50"
    stage2_action: str = "stop_new"
    stage3_action: str = "close_all"
    
    current_drawdown: float = 0.0
    current_stage: int = 0
    
    def check(self, drawdown: float) -> Tuple[int, str, RiskLevel]:
        """
        Check drawdown gate status.
        
        Returns:
            Tuple of (stage, action, risk_level)
        """
        self.current_drawdown = abs(drawdown)
        
        if self.current_drawdown >= self.stage3_threshold:
            self.current_stage = 3
            return 3, self.stage3_action, RiskLevel.RED
        
        if self.current_drawdown >= self.stage2_threshold:
            self.current_stage = 2
            return 2, self.stage2_action, RiskLevel.RED
        
        if self.current_drawdown >= self.stage1_threshold:
            self.current_stage = 1
            return 1, self.stage1_action, RiskLevel.YELLOW
        
        self.current_stage = 0
        return 0, "normal", RiskLevel.GREEN
    
    def apply_position_adjustment(self, position: PositionSize) -> PositionSize:
        """Apply position size adjustment based on drawdown stage."""
        if self.current_stage == 0:
            return position
        
        if self.current_stage == 1:
            return PositionSize(
                fraction_of_portfolio=position.fraction_of_portfolio * 0.5,
                dollar_amount=position.dollar_amount * 0.5,
                shares=position.shares * 0.5,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method=f"{position.method}_dd_gate_1",
                confidence=position.confidence * 0.5,
                warnings=position.warnings + ["Drawdown stage 1: reduced 50%"],
            )
        
        if self.current_stage == 2:
            return PositionSize(
                fraction_of_portfolio=0.0,
                dollar_amount=0.0,
                shares=0.0,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method="dd_gate_2",
                confidence=0.0,
                warnings=position.warnings + ["Drawdown stage 2: no new positions"],
            )
        
        return PositionSize(
            fraction_of_portfolio=0.0,
            dollar_amount=0.0,
            shares=0.0,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            risk_per_share=position.risk_per_share,
            method="dd_gate_3",
            confidence=0.0,
            warnings=position.warnings + ["Drawdown stage 3: close all positions"],
        )


class VaRCalculator:
    """
    Value at Risk calculator.
    
    Uses historical simulation method for VaR estimation.
    """
    
    def __init__(self, confidence_levels: Tuple[float, ...] = (0.95, 0.99)):
        self.confidence_levels = confidence_levels
    
    def calculate(
        self,
        returns: pd.Series,
        portfolio_value: float = 100000.0,
    ) -> Dict[str, float]:
        """
        Calculate VaR at multiple confidence levels.
        
        Args:
            returns: Series of portfolio returns
            portfolio_value: Current portfolio value
            
        Returns:
            Dict mapping confidence level to VaR amount
        """
        if len(returns) < 30:
            return {f"var_{int(c*100)}": 0.0 for c in self.confidence_levels}
        
        result = {}
        for conf in self.confidence_levels:
            var_pct = float(np.percentile(returns, (1 - conf) * 100))
            var_amount = portfolio_value * abs(var_pct)
            result[f"var_{int(conf*100)}"] = var_amount
            result[f"var_{int(conf*100)}_pct"] = abs(var_pct)
        
        return result


class CorrelationChecker:
    """
    Correlation-based exposure checker.
    
    Prevents over-concentration in correlated positions.
    """
    
    def __init__(self, max_correlation: float = 0.70):
        self.max_correlation = max_correlation
    
    def check(
        self,
        new_returns: pd.Series,
        existing_returns: Dict[str, pd.Series],
    ) -> Tuple[bool, List[str]]:
        """
        Check if new position is too correlated with existing positions.
        
        Args:
            new_returns: Returns of proposed new position
            existing_returns: Dict of existing position returns
            
        Returns:
            Tuple of (is_acceptable, warnings)
        """
        warnings = []
        
        for name, existing in existing_returns.items():
            min_len = min(len(new_returns), len(existing))
            if min_len < 30:
                continue
            
            corr = float(new_returns.iloc[-min_len:].corr(existing.iloc[-min_len:]))
            
            if np.isnan(corr):
                continue
            
            if corr > self.max_correlation:
                warnings.append(
                    f"High correlation ({corr:.2f}) with {name} "
                    f"(limit: {self.max_correlation:.2f})"
                )
        
        return len(warnings) == 0, warnings


class RiskManager:
    """
    Central risk management engine.
    
    Coordinates position sizing, VaR limits, drawdown gates,
    and correlation checks to enforce production-grade risk controls.
    """
    
    def __init__(
        self,
        portfolio_value: float = 100000.0,
        kelly_fraction: float = 0.25,
        target_volatility: float = 0.15,
        max_var_pct: float = 0.05,
        dd_gate: Optional[DrawdownGate] = None,
        max_correlation: float = 0.70,
    ):
        self.portfolio_value = portfolio_value
        self.kelly_sizer = KellySizer(kelly_fraction=kelly_fraction)
        self.risk_parity_sizer = RiskParitySizer(target_volatility=target_volatility)
        self.limit_sizer = MaxLimitSizer()
        self.var_calculator = VaRCalculator()
        self.correlation_checker = CorrelationChecker(max_correlation=max_correlation)
        self.drawdown_gate = dd_gate or DrawdownGate()
        self.max_var_pct = max_var_pct
        self._position_history: List[PositionSize] = []
        self._returns_history: pd.Series = pd.Series(dtype=float)
    
    def calculate_position_size(
        self,
        strategy_returns: pd.Series,
        price: float = 1.0,
        sector_exposure: float = 0.0,
        existing_positions: Optional[Dict[str, pd.Series]] = None,
    ) -> PositionSize:
        """
        Calculate safe position size with all risk controls.
        
        Args:
            strategy_returns: Historical returns of strategy
            price: Current asset price
            sector_exposure: Current sector exposure
            existing_positions: Dict of existing position returns
            
        Returns:
            PositionSize with all risk controls applied
        """
        all_warnings = []
        
        gate_stage, gate_action, risk_level = self.drawdown_gate.check(
            self._current_drawdown()
        )
        
        if gate_stage >= 2:
            position = PositionSize(
                fraction_of_portfolio=0.0,
                dollar_amount=0.0,
                shares=0.0,
                stop_loss=price * 0.98,
                take_profit=price * 1.04,
                risk_per_share=price * 0.02,
                method="risk_gate",
                confidence=0.0,
                warnings=[f"Drawdown gate stage {gate_stage}: {gate_action}"],
            )
            return position
        
        kelly_position = self.kelly_sizer.calculate(
            strategy_returns, self.portfolio_value, price
        )
        risk_parity_position = self.risk_parity_sizer.calculate(
            strategy_returns, self.portfolio_value, price
        )
        
        if kelly_position.fraction_of_portfolio > 0 and risk_parity_position.fraction_of_portfolio > 0:
            avg_fraction = (kelly_position.fraction_of_portfolio + risk_parity_position.fraction_of_portfolio) / 2
            position = PositionSize(
                fraction_of_portfolio=avg_fraction,
                dollar_amount=self.portfolio_value * avg_fraction,
                shares=self.portfolio_value * avg_fraction / price,
                stop_loss=kelly_position.stop_loss,
                take_profit=kelly_position.take_profit,
                risk_per_share=kelly_position.risk_per_share,
                method="kelly_risk_parity_avg",
                confidence=min(kelly_position.confidence, risk_parity_position.confidence),
                warnings=kelly_position.warnings + risk_parity_position.warnings,
            )
        elif kelly_position.fraction_of_portfolio > 0:
            position = kelly_position
        else:
            position = risk_parity_position
        
        if gate_stage == 1:
            position = self.drawdown_gate.apply_position_adjustment(position)
        
        position, limit_warnings = self.limit_sizer.enforce(
            position, self.portfolio_value, sector_exposure
        )
        all_warnings.extend(limit_warnings)
        
        if existing_positions and len(strategy_returns) >= 30:
            ok, corr_warnings = self.correlation_checker.check(
                strategy_returns, existing_positions
            )
            all_warnings.extend(corr_warnings)
            if not ok:
                position = PositionSize(
                    fraction_of_portfolio=position.fraction_of_portfolio * 0.5,
                    dollar_amount=position.dollar_amount * 0.5,
                    shares=position.shares * 0.5,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    risk_per_share=position.risk_per_share,
                    method=f"{position.method}_corr_reduced",
                    confidence=position.confidence * 0.5,
                    warnings=position.warnings + corr_warnings,
                )
        
        var_results = self.var_calculator.calculate(strategy_returns, self.portfolio_value)
        var_95 = var_results.get("var_95", 0.0)
        max_var = self.portfolio_value * self.max_var_pct
        
        if var_95 > max_var:
            all_warnings.append(f"VaR 95% ${var_95:.0f} exceeds limit ${max_var:.0f}")
            reduction = max_var / var_95 if var_95 > 0 else 1.0
            position = PositionSize(
                fraction_of_portfolio=position.fraction_of_portfolio * reduction,
                dollar_amount=position.dollar_amount * reduction,
                shares=position.shares * reduction,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method=f"{position.method}_var_capped",
                confidence=position.confidence,
                warnings=position.warnings + all_warnings,
            )
        else:
            position = PositionSize(
                fraction_of_portfolio=position.fraction_of_portfolio,
                dollar_amount=position.dollar_amount,
                shares=position.shares,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method=position.method,
                confidence=position.confidence,
                warnings=position.warnings + all_warnings,
            )
        
        self._position_history.append(position)
        
        logger.info(
            f"Position sized: {position.method}, "
            f"frac={position.fraction_of_portfolio:.2%}, "
            f"${position.dollar_amount:.0f}, "
            f"warnings={len(position.warnings)}"
        )
        
        return position
    
    def get_risk_metrics(self, strategy_returns: pd.Series) -> RiskMetrics:
        """
        Get current portfolio risk metrics.
        
        Args:
            strategy_returns: Historical strategy returns
            
        Returns:
            RiskMetrics with current risk assessment
        """
        if len(strategy_returns) < 30:
            return RiskMetrics(
                current_drawdown=0.0,
                var_95=0.0,
                var_99=0.0,
                sharpe_ratio=0.0,
                volatility=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                total_trades=0,
                risk_level=RiskLevel.YELLOW,
                warnings=["Insufficient data for risk metrics"],
            )
        
        drawdown = self._current_drawdown()
        var_results = self.var_calculator.calculate(strategy_returns, self.portfolio_value)
        
        volatility = float(strategy_returns.std() * np.sqrt(252))
        sharpe = float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)) if strategy_returns.std() > 0 else 0.0
        win_rate = float((strategy_returns > 0).mean())
        
        cumsum = (1 + strategy_returns).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        max_dd = float(dd.min())
        
        _, _, risk_level = self.drawdown_gate.check(drawdown)
        
        return RiskMetrics(
            current_drawdown=drawdown,
            var_95=var_results.get("var_95", 0.0),
            var_99=var_results.get("var_99", 0.0),
            sharpe_ratio=sharpe,
            volatility=volatility,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=len(strategy_returns),
            risk_level=risk_level,
        )
    
    def _current_drawdown(self) -> float:
        """Calculate current drawdown from returns history."""
        if len(self._returns_history) < 2:
            return 0.0
        
        cumsum = (1 + self._returns_history).cumprod()
        running_max = cumsum.cummax()
        dd = (cumsum - running_max) / running_max
        return float(dd.iloc[-1])
    
    def update_returns(self, returns: pd.Series):
        """Update returns history."""
        self._returns_history = pd.concat([self._returns_history, returns])
    
    def reset(self):
        """Reset risk manager state."""
        self._position_history = []
        self._returns_history = pd.Series(dtype=float)
        self.drawdown_gate.current_stage = 0
        self.drawdown_gate.current_drawdown = 0.0
