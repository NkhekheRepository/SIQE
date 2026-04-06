"""
SIQE V3 - Position Sizing Engine

Production-grade position sizing using:
- Kelly Criterion (fractional for safety)
- Risk Parity (volatility-weighted)
- Maximum position limits

All sizing respects SafetyLimits and circuit breakers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

from strategy_engine.config import DirectionalBias, SafetyLimits

logger = logging.getLogger(__name__)


class RegimePositionSizer:
    """
    Regime-aware position sizing for bear market adaptation.
    
    Adjusts position sizes based on directional bias:
    - BEAR: Reduce longs to 50%, keep shorts at 100%
    - BULL: Reduce shorts to 25%, keep longs at 100%
    - NEUTRAL: 75% size for all positions
    """
    
    @staticmethod
    def calculate_multiplier(
        bias: DirectionalBias,
        direction: int,
    ) -> float:
        """
        Calculate position size multiplier based on regime and direction.
        
        Args:
            bias: Current directional bias (BULL/BEAR/NEUTRAL)
            direction: +1 for LONG, -1 for SHORT
            
        Returns:
            Multiplier to apply to base position size
        """
        return SafetyLimits.get_position_size_multiplier(bias, direction)


@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    fraction_of_portfolio: float
    dollar_amount: float
    shares: float
    stop_loss: float
    take_profit: float
    risk_per_share: float
    method: str
    confidence: float
    warnings: List[str]


class KellySizer:
    """
    Kelly Criterion position sizing.
    
    Uses fractional Kelly (default 0.25) for conservative sizing.
    Full Kelly is too aggressive for real markets due to estimation error.
    """
    
    def __init__(self, kelly_fraction: float = 0.25, min_trades: int = 30):
        self.kelly_fraction = kelly_fraction
        self.min_trades = min_trades
    
    def calculate(
        self,
        returns: pd.Series,
        portfolio_value: float = 100000.0,
        price: float = 1.0,
    ) -> PositionSize:
        """
        Calculate position size using Kelly Criterion.
        
        Args:
            returns: Series of strategy returns
            portfolio_value: Total portfolio value
            price: Current asset price
            
        Returns:
            PositionSize with recommended allocation
        """
        warnings = []
        
        if len(returns) < self.min_trades:
            warnings.append(
                f"Insufficient trades: {len(returns)} < {self.min_trades}"
            )
            return PositionSize(
                fraction_of_portfolio=0.0,
                dollar_amount=0.0,
                shares=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_per_share=0.0,
                method="kelly",
                confidence=0.0,
                warnings=warnings,
            )
        
        win_mask = returns > 0
        loss_mask = returns <= 0
        
        if win_mask.sum() == 0 or loss_mask.sum() == 0:
            return PositionSize(
                fraction_of_portfolio=0.0,
                dollar_amount=0.0,
                shares=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_per_share=0.0,
                method="kelly",
                confidence=0.0,
                warnings=["No winning or losing trades"],
            )
        
        win_rate = float(win_mask.mean())
        loss_rate = 1.0 - win_rate
        
        avg_win = float(returns[win_mask].mean())
        avg_loss = float(abs(returns[loss_mask].mean()))
        
        if avg_loss == 0:
            warnings.append("Zero average loss - using conservative estimate")
            avg_loss = avg_win * 0.5
        
        win_loss_ratio = avg_win / avg_loss
        
        kelly_pct = win_rate - (loss_rate / win_loss_ratio)
        fractional_kelly = kelly_pct * self.kelly_fraction
        
        max_position = 0.10
        position_frac = max(0.0, min(fractional_kelly, max_position))
        
        dollar_amount = portfolio_value * position_frac
        shares = dollar_amount / price if price > 0 else 0.0
        
        volatility = float(returns.std())
        stop_loss = price * (1 - 2 * volatility)
        take_profit = price * (1 + 3 * volatility)
        risk_per_share = price - stop_loss if stop_loss < price else price * 0.02
        
        confidence = min(1.0, len(returns) / 100.0)
        
        return PositionSize(
            fraction_of_portfolio=position_frac,
            dollar_amount=dollar_amount,
            shares=shares,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_per_share=risk_per_share,
            method="kelly",
            confidence=confidence,
            warnings=warnings,
        )


class RiskParitySizer:
    """
    Risk parity position sizing.
    
    Allocates capital so each position contributes equal risk.
    """
    
    def __init__(self, target_volatility: float = 0.15):
        self.target_volatility = target_volatility
    
    def calculate(
        self,
        returns: pd.Series,
        portfolio_value: float = 100000.0,
        price: float = 1.0,
    ) -> PositionSize:
        """
        Calculate position size using risk parity.
        
        Args:
            returns: Series of strategy returns
            portfolio_value: Total portfolio value
            price: Current asset price
            
        Returns:
            PositionSize with recommended allocation
        """
        warnings = []
        
        if len(returns) < 30:
            return PositionSize(
                fraction_of_portfolio=0.0,
                dollar_amount=0.0,
                shares=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_per_share=0.0,
                method="risk_parity",
                confidence=0.0,
                warnings=["Insufficient data for risk parity"],
            )
        
        volatility = float(returns.std() * np.sqrt(252))
        
        if volatility == 0:
            warnings.append("Zero volatility detected")
            volatility = 0.01
        
        position_frac = min(self.target_volatility / volatility, 0.15)
        
        dollar_amount = portfolio_value * position_frac
        shares = dollar_amount / price if price > 0 else 0.0
        
        stop_loss = price * (1 - self.target_volatility)
        take_profit = price * (1 + 2 * self.target_volatility)
        risk_per_share = price * self.target_volatility
        
        confidence = min(1.0, len(returns) / 100.0)
        
        return PositionSize(
            fraction_of_portfolio=position_frac,
            dollar_amount=dollar_amount,
            shares=shares,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_per_share=risk_per_share,
            method="risk_parity",
            confidence=confidence,
            warnings=warnings,
        )


class MaxLimitSizer:
    """
    Maximum position limit enforcer.
    
    Ensures no single position exceeds portfolio limits.
    """
    
    def __init__(
        self,
        max_position_pct: float = 0.10,
        max_sector_pct: float = 0.30,
        max_portfolio_risk: float = 0.05,
    ):
        self.max_position_pct = max_position_pct
        self.max_sector_pct = max_sector_pct
        self.max_portfolio_risk = max_portfolio_risk
    
    def enforce(
        self,
        position: PositionSize,
        portfolio_value: float = 100000.0,
        sector_exposure: float = 0.0,
    ) -> Tuple[PositionSize, List[str]]:
        """
        Enforce maximum position limits.
        
        Args:
            position: Proposed position
            portfolio_value: Total portfolio value
            sector_exposure: Current exposure to same sector
            
        Returns:
            Tuple of (adjusted_position, warnings)
        """
        warnings = list(position.warnings)
        
        max_dollar = portfolio_value * self.max_position_pct
        
        if position.dollar_amount > max_dollar:
            warnings.append(
                f"Position ${position.dollar_amount:.0f} exceeds max ${max_dollar:.0f}"
            )
            ratio = max_dollar / position.dollar_amount
            position = PositionSize(
                fraction_of_portfolio=position.fraction_of_portfolio * ratio,
                dollar_amount=max_dollar,
                shares=position.shares * ratio,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method=f"{position.method}_capped",
                confidence=position.confidence,
                warnings=warnings,
            )
        
        if sector_exposure + position.dollar_amount > portfolio_value * self.max_sector_pct:
            warnings.append("Sector concentration limit reached")
            remaining = portfolio_value * self.max_sector_pct - sector_exposure
            if remaining <= 0:
                return PositionSize(
                    fraction_of_portfolio=0.0,
                    dollar_amount=0.0,
                    shares=0.0,
                    stop_loss=0.0,
                    take_profit=0.0,
                    risk_per_share=0.0,
                    method="sector_limit",
                    confidence=0.0,
                    warnings=warnings,
                ), warnings
            
            ratio = remaining / position.dollar_amount
            position = PositionSize(
                fraction_of_portfolio=position.fraction_of_portfolio * ratio,
                dollar_amount=remaining,
                shares=position.shares * ratio,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                risk_per_share=position.risk_per_share,
                method=f"{position.method}_sector_capped",
                confidence=position.confidence,
                warnings=warnings,
            )
        
        return position, warnings


class PortfolioSizer:
    """
    Portfolio-level position sizing with correlation-aware allocation.
    
    Combines Kelly, Risk Parity, and correlation matrix to allocate
    capital across multiple assets while respecting portfolio risk limits.
    """
    
    def __init__(
        self,
        max_portfolio_risk: float = 0.02,
        max_single_position_risk: float = 0.01,
        kelly_fraction: float = 0.25,
        target_volatility: float = 0.15,
    ):
        self.max_portfolio_risk = max_portfolio_risk
        self.max_single_position_risk = max_single_position_risk
        self.kelly_fraction = kelly_fraction
        self.target_volatility = target_volatility
        self._kelly = KellySizer(kelly_fraction=kelly_fraction)
        self._risk_parity = RiskParitySizer(target_volatility=target_volatility)
        self._max_limit = MaxLimitSizer(max_position_pct=max_single_position_risk * 10)
    
    def allocate(
        self,
        symbol_returns: Dict[str, pd.Series],
        portfolio_value: float,
        prices: Dict[str, float],
        correlation_matrix: Optional[np.ndarray] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, PositionSize]:
        """
        Allocate capital across symbols using correlation-aware risk parity.
        
        Args:
            symbol_returns: Dict of symbol -> return series
            portfolio_value: Total portfolio value
            prices: Dict of symbol -> current price
            correlation_matrix: Pre-computed correlation matrix
            symbols: List of symbols to allocate
            
        Returns:
            Dict of symbol -> PositionSize
        """
        if not symbols:
            symbols = list(symbol_returns.keys())
        
        if len(symbols) == 0:
            return {}
        
        if len(symbols) == 1:
            sym = symbols[0]
            returns = symbol_returns.get(sym, pd.Series())
            price = prices.get(sym, 1.0)
            return {sym: self._kelly.calculate(returns, portfolio_value, price)}
        
        if correlation_matrix is not None and len(symbols) >= 2:
            return self._correlation_aware_allocation(
                symbols, symbol_returns, portfolio_value, prices, correlation_matrix
            )
        
        return self._risk_parity_allocation(symbols, symbol_returns, portfolio_value, prices)
    
    def _correlation_aware_allocation(
        self,
        symbols: List[str],
        symbol_returns: Dict[str, pd.Series],
        portfolio_value: float,
        prices: Dict[str, float],
        corr_matrix: np.ndarray,
    ) -> Dict[str, PositionSize]:
        """Allocate using correlation matrix to diversify risk."""
        n = len(symbols)
        vols = np.array([
            float(symbol_returns.get(s, pd.Series()).std() * np.sqrt(252))
            for s in symbols
        ])
        vols = np.clip(vols, 0.01, 2.0)
        
        risk_budget = np.ones(n) / n
        for _ in range(50):
            port_vol = np.sqrt(risk_budget @ corr_matrix @ risk_budget)
            if port_vol == 0:
                break
            marginal_risk = corr_matrix @ risk_budget
            risk_contrib = risk_budget * marginal_risk / port_vol
            target = np.ones(n) / n
            adjustment = target / np.clip(risk_contrib, 1e-10, None)
            risk_budget *= adjustment
            risk_budget /= risk_budget.sum()
        
        results = {}
        for i, sym in enumerate(symbols):
            weight = risk_budget[i]
            returns = symbol_returns.get(sym, pd.Series())
            price = prices.get(sym, 1.0)
            
            dollar_amount = portfolio_value * weight * min(self.max_portfolio_risk * 10, 0.20)
            dollar_amount = min(dollar_amount, portfolio_value * self.max_single_position_risk)
            
            shares = dollar_amount / price if price > 0 else 0.0
            vol = vols[i]
            stop_loss = price * (1 - vol * 2)
            take_profit = price * (1 + vol * 3)
            risk_per_share = price - stop_loss if stop_loss < price else price * 0.02
            
            results[sym] = PositionSize(
                fraction_of_portfolio=weight,
                dollar_amount=dollar_amount,
                shares=shares,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_share=risk_per_share,
                method="risk_parity_corr",
                confidence=min(1.0, len(returns) / 100.0) if len(returns) > 0 else 0.0,
                warnings=[],
            )
        
        return results
    
    def _risk_parity_allocation(
        self,
        symbols: List[str],
        symbol_returns: Dict[str, pd.Series],
        portfolio_value: float,
        prices: Dict[str, float],
    ) -> Dict[str, PositionSize]:
        """Equal risk contribution allocation without correlation matrix."""
        vols = {}
        for sym in symbols:
            returns = symbol_returns.get(sym, pd.Series())
            if len(returns) >= 30:
                vols[sym] = float(returns.std() * np.sqrt(252))
            else:
                vols[sym] = self.target_volatility
        
        total_inv_vol = sum(1.0 / v for v in vols.values())
        results = {}
        
        for sym in symbols:
            weight = (1.0 / vols[sym]) / total_inv_vol
            price = prices.get(sym, 1.0)
            dollar_amount = portfolio_value * weight * min(self.max_portfolio_risk * 10, 0.20)
            dollar_amount = min(dollar_amount, portfolio_value * self.max_single_position_risk)
            shares = dollar_amount / price if price > 0 else 0.0
            vol = vols[sym]
            stop_loss = price * (1 - vol * 2)
            take_profit = price * (1 + vol * 3)
            risk_per_share = price - stop_loss if stop_loss < price else price * 0.02
            
            results[sym] = PositionSize(
                fraction_of_portfolio=weight,
                dollar_amount=dollar_amount,
                shares=shares,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_share=risk_per_share,
                method="risk_parity",
                confidence=min(1.0, len(symbol_returns.get(sym, [])) / 100.0),
                warnings=[],
            )
        
        return results
