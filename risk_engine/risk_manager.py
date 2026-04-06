"""
Risk Engine Module
Enforces risk limits and validates trades against risk parameters.
Deterministic: uses EventClock instead of datetime.now().
Includes circuit breakers for production safety.
Phase 3: Added portfolio-level VaR, correlation matrix, Monte Carlo simulation.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

import numpy as np

from core.clock import EventClock
from models.trade import Decision, ApprovalResult
from alerts.alert_manager import AlertManager

logger = logging.getLogger(__name__)


class CircuitBreakerType(str, Enum):
    DAILY_LOSS = "daily_loss"
    DRAWDOWN = "drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    API_FAILURES = "api_failures"
    EMERGENCY_STOP = "emergency_stop"


class CircuitBreakerState:
    def __init__(self, breaker_type: CircuitBreakerType):
        self.breaker_type = breaker_type
        self.is_active = False
        self.triggered_at = 0
        self.trigger_reason = ""
        self.trigger_count = 0

    def activate(self, clock_time: int, reason: str):
        self.is_active = True
        self.triggered_at = clock_time
        self.trigger_reason = reason
        self.trigger_count += 1

    def deactivate(self):
        self.is_active = False
        self.triggered_at = 0
        self.trigger_reason = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.breaker_type.value,
            "is_active": self.is_active,
            "triggered_at": self.triggered_at,
            "trigger_reason": self.trigger_reason,
            "trigger_count": self.trigger_count,
        }


class RiskEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.daily_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_equity = 0.0
        self.current_equity = self.settings.get("initial_equity", 10000.0)
        self.consecutive_losses = 0
        self.risk_limits = {
            "max_daily_loss": self.settings.get("max_daily_loss", 0.05),
            "max_drawdown": self.settings.get("max_drawdown", 0.20),
            "max_position_size": self.settings.get("max_position_size", 0.1),
            "max_consecutive_losses": self.settings.get("max_consecutive_losses", 5),
            "max_trades_per_hour": self.settings.get("max_trades_per_hour", 100),
            "volatility_scaling": self.settings.get("volatility_scaling", True),
        }
        self.trade_count_hour = 0
        self.last_hour_reset = 0
        self.alert_manager: Optional[AlertManager] = None

        self._circuit_breakers: Dict[CircuitBreakerType, CircuitBreakerState] = {
            cb_type: CircuitBreakerState(cb_type)
            for cb_type in CircuitBreakerType
        }
        self._api_failure_count = 0
        self._max_api_failures = 3
        self._emergency_stop_reason = ""
        self._circuit_breaker_history: List[Dict[str, Any]] = []
        self._trade_returns: List[float] = []
        self._max_returns_history = 1000

        # Phase 3: Portfolio-level risk
        self._symbol_returns: Dict[str, List[float]] = {}
        self._symbol_positions: Dict[str, Dict[str, float]] = {}
        self._max_portfolio_risk = self.settings.get("max_portfolio_risk", 0.02)
        self._max_single_position_risk = self.settings.get("max_single_position_risk", 0.01)
        self._var_confidence = self.settings.get("var_confidence", 0.95)
        self._correlation_matrix: Optional[np.ndarray] = None
        self._correlation_symbols: List[str] = []
        self._correlation_lookback = 100

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Risk Engine...")
            self.is_initialized = True
            logger.info("Risk Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Risk Engine: {e}")
            return False

    def set_alert_manager(self, alert_manager: AlertManager) -> None:
        """Connect alert manager for notifications."""
        self.alert_manager = alert_manager
        logger.info("Alert manager connected to Risk Engine")

    async def validate_trade(self, decision: Decision, risk_scaling: Optional[float] = None) -> ApprovalResult:
        if not self.is_initialized:
            return ApprovalResult(approved=False, reason="Risk engine not initialized", event_seq=decision.event_seq)

        try:
            active_breakers = self._get_active_circuit_breakers()
            if active_breakers:
                breaker_names = [b.breaker_type.value for b in active_breakers]
                return ApprovalResult(
                    approved=False,
                    reason=f"Circuit breaker active: {', '.join(breaker_names)}",
                    event_seq=decision.event_seq,
                )

            await self._reset_hourly_counter()

            if self.trade_count_hour >= self.risk_limits["max_trades_per_hour"]:
                return ApprovalResult(
                    approved=False,
                    reason=f"Hourly trade limit exceeded ({self.trade_count_hour}/{self.risk_limits['max_trades_per_hour']})",
                    event_seq=decision.event_seq,
                )

            daily_loss_pct = abs(self.daily_pnl) / self.current_equity if self.current_equity > 0 else 0
            if self.daily_pnl < 0 and daily_loss_pct >= self.risk_limits["max_daily_loss"]:
                self._activate_circuit_breaker(CircuitBreakerType.DAILY_LOSS, f"Daily loss {daily_loss_pct:.2%} >= {self.risk_limits['max_daily_loss']:.2%}")
                if self.alert_manager:
                    self.alert_manager.daily_loss(
                        loss=daily_loss_pct,
                        limit=self.risk_limits["max_daily_loss"]
                    )
                return ApprovalResult(
                    approved=False,
                    reason=f"Daily loss limit exceeded ({daily_loss_pct:.2%} >= {self.risk_limits['max_daily_loss']:.2%})",
                    event_seq=decision.event_seq,
                )
            elif self.daily_pnl < 0 and daily_loss_pct >= self.risk_limits["max_daily_loss"] * 0.8:
                if self.alert_manager:
                    self.alert_manager.drawdown_warning(
                        current_dd=daily_loss_pct,
                        max_dd=self.risk_limits["max_daily_loss"],
                        alert_type="daily_loss_warning"
                    )

            current_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
            if current_drawdown >= self.risk_limits["max_drawdown"]:
                self._activate_circuit_breaker(CircuitBreakerType.DRAWDOWN, f"Drawdown {current_drawdown:.2%} >= {self.risk_limits['max_drawdown']:.2%}")
                if self.alert_manager:
                    self.alert_manager.drawdown_warning(
                        current_dd=current_drawdown,
                        max_dd=self.risk_limits["max_drawdown"],
                        alert_type="drawdown_breach"
                    )
                return ApprovalResult(
                    approved=False,
                    reason=f"Maximum drawdown exceeded ({current_drawdown:.2%} >= {self.risk_limits['max_drawdown']:.2%})",
                    event_seq=decision.event_seq,
                )
            elif current_drawdown >= self.risk_limits["max_drawdown"] * 0.8:
                if self.alert_manager:
                    self.alert_manager.drawdown_warning(
                        current_dd=current_drawdown,
                        max_dd=self.risk_limits["max_drawdown"],
                        alert_type="drawdown_warning"
                    )

            if self.consecutive_losses >= self.risk_limits["max_consecutive_losses"]:
                self._activate_circuit_breaker(CircuitBreakerType.CONSECUTIVE_LOSSES, f"Consecutive losses {self.consecutive_losses} >= {self.risk_limits['max_consecutive_losses']}")
                return ApprovalResult(
                    approved=False,
                    reason=f"Consecutive losses limit exceeded ({self.consecutive_losses} >= {self.risk_limits['max_consecutive_losses']})",
                    event_seq=decision.event_seq,
                )

            signal_strength = decision.strength
            effective_strength = signal_strength * (risk_scaling if risk_scaling else 1.0)
            estimated_position_pct = effective_strength * 0.1

            if estimated_position_pct > self.risk_limits["max_position_size"]:
                return ApprovalResult(
                    approved=False,
                    reason=f"Position size too large ({estimated_position_pct:.2%} > {self.risk_limits['max_position_size']:.2%})",
                    event_seq=decision.event_seq,
                )

            self.trade_count_hour += 1

            logger.debug(f"Trade approved: {decision.symbol} ({decision.signal_type.value}) strength={signal_strength:.2f}")

            return ApprovalResult(
                approved=True,
                reason="All risk checks passed",
                event_seq=decision.event_seq,
                details={
                    "daily_loss_pct": daily_loss_pct,
                    "current_drawdown": current_drawdown,
                    "consecutive_losses": self.consecutive_losses,
                    "trades_this_hour": self.trade_count_hour,
                },
            )

        except Exception as e:
            logger.error(f"Error validating trade: {e}")
            return ApprovalResult(approved=False, reason=f"Risk validation error: {str(e)}", event_seq=decision.event_seq)

    async def update_trade_result(self, profit: float):
        try:
            self.daily_pnl += profit
            self.current_equity += profit

            if self.current_equity > self.peak_equity:
                self.peak_equity = self.current_equity

            if profit < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

            # Track returns for VaR calculation
            return_pct = profit / self.current_equity if self.current_equity > 0 else 0
            self._trade_returns.append(return_pct)
            if len(self._trade_returns) > self._max_returns_history:
                self._trade_returns = self._trade_returns[-self._max_returns_history:]

            logger.debug(f"Updated risk metrics: PnL={profit:.2f}, Daily PnL={self.daily_pnl:.2f}, "
                         f"Equity={self.current_equity:.2f}, Consecutive losses={self.consecutive_losses}")
        except Exception as e:
            logger.error(f"Error updating trade result: {e}")

    async def reset_daily_metrics(self):
        self.daily_pnl = 0.0
        logger.info("Daily risk metrics reset")

    async def _reset_hourly_counter(self):
        now = self.clock.now
        if (now - self.last_hour_reset) >= 3600:
            self.trade_count_hour = 0
            self.last_hour_reset = now
            logger.debug("Hourly trade counter reset")

    async def get_risk_status(self) -> Dict[str, Any]:
        daily_loss_pct = abs(self.daily_pnl) / self.current_equity if self.current_equity > 0 else 0
        current_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0

        return {
            "daily_pnl": self.daily_pnl,
            "daily_loss_pct": daily_loss_pct,
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "current_drawdown": current_drawdown,
            "consecutive_losses": self.consecutive_losses,
            "trades_this_hour": self.trade_count_hour,
            "risk_limits": self.risk_limits,
            "within_limits": {
                "daily_loss": daily_loss_pct < self.risk_limits["max_daily_loss"],
                "drawdown": current_drawdown < self.risk_limits["max_drawdown"],
                "consecutive_losses": self.consecutive_losses < self.risk_limits["max_consecutive_losses"],
                "hourly_trades": self.trade_count_hour < self.risk_limits["max_trades_per_hour"],
            },
        }

    def calculate_var(self, returns: List[float], confidence: float = 0.99) -> float:
        """
        Calculate Value at Risk (VaR) using historical method.
        
        Args:
            returns: List of historical returns
            confidence: Confidence level (default 99%)
            
        Returns:
            VaR as a positive number representing potential loss
        """
        if not returns or len(returns) < 10:
            return 0.0
        
        returns_array = np.array(returns)
        var = np.percentile(returns_array, (1 - confidence) * 100)
        return abs(var)
    
    def calculate_cvar(self, returns: List[float], confidence: float = 0.99) -> float:
        """
        Calculate Conditional Value at Risk (CVaR/Expected Shortfall).
        
        Args:
            returns: List of historical returns
            confidence: Confidence level (default 99%)
            
        Returns:
            CVaR as a positive number representing expected loss beyond VaR
        """
        if not returns or len(returns) < 10:
            return 0.0
        
        returns_array = np.array(returns)
        var = np.percentile(returns_array, (1 - confidence) * 100)
        cvar = abs(returns_array[returns_array <= var].mean()) if np.any(returns_array <= var) else var
        return cvar
    
    async def get_var_status(self, returns: List[float] = None) -> Dict[str, Any]:
        """
        Get VaR/CVaR risk metrics.
        
        Args:
            returns: Optional list of returns to use for calculation
                    If not provided, uses stored trade returns
        """
        if returns is None:
            returns = self._trade_returns
        
        var_99 = self.calculate_var(returns, 0.99)
        var_95 = self.calculate_var(returns, 0.95)
        cvar_99 = self.calculate_cvar(returns, 0.99)
        
        return {
            "var_95": var_95,
            "var_99": var_99,
            "cvar_99": cvar_99,
            "confidence_95": f"{var_95:.2%} of equity",
            "confidence_99": f"{var_99:.2%} of equity",
            "expected_shortfall_99": f"{cvar_99:.2%} of equity",
            "sample_size": len(returns),
        }

    async def shutdown(self):
        logger.info("Shutting down Risk Engine...")
        self.is_initialized = False
        logger.info("Risk Engine shutdown complete")

    def _activate_circuit_breaker(self, breaker_type: CircuitBreakerType, reason: str):
        breaker = self._circuit_breakers[breaker_type]
        breaker.activate(self.clock.now, reason)
        self._circuit_breaker_history.append({
            "type": breaker_type.value,
            "reason": reason,
            "triggered_at": self.clock.now,
        })
        logger.warning(f"CIRCUIT BREAKER ACTIVATED: {breaker_type.value} - {reason}")
        
        # Send Telegram alert
        if self.alert_manager:
            self.alert_manager.circuit_breaker(
                breaker_name=breaker_type.value,
                reason=reason
            )

    def _get_active_circuit_breakers(self) -> List[CircuitBreakerState]:
        return [b for b in self._circuit_breakers.values() if b.is_active]

    async def emergency_stop(self, reason: str = "Manual emergency stop"):
        self._emergency_stop_reason = reason
        self._activate_circuit_breaker(CircuitBreakerType.EMERGENCY_STOP, reason)
        logger.critical(f"EMERGENCY STOP: {reason}")
        return {"success": True, "reason": reason, "timestamp": self.clock.now}

    async def emergency_resume(self):
        for breaker in self._circuit_breakers.values():
            breaker.deactivate()
        self._emergency_stop_reason = ""
        logger.info("Emergency resume: all circuit breakers reset")
        return {"success": True, "timestamp": self.clock.now}

    async def record_api_failure(self):
        self._api_failure_count += 1
        if self._api_failure_count >= self._max_api_failures:
            self._activate_circuit_breaker(
                CircuitBreakerType.API_FAILURES,
                f"API failures: {self._api_failure_count} >= {self._max_api_failures}",
            )
        elif self.alert_manager:
            self.alert_manager.api_failure(
                endpoint="Binance API",
                error=f"Failure #{self._api_failure_count}/{self._max_api_failures}"
            )
        logger.warning(f"API failure recorded ({self._api_failure_count}/{self._max_api_failures})")

    async def record_api_success(self):
        self._api_failure_count = 0

    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        breakers = {bt.value: b.to_dict() for bt, b in self._circuit_breakers.items()}
        active = [b for b in self._circuit_breakers.values() if b.is_active]
        return {
            "circuit_breakers": breakers,
            "any_active": len(active) > 0,
            "active_breakers": [b.breaker_type.value for b in active],
            "emergency_stop_reason": self._emergency_stop_reason,
            "api_failure_count": self._api_failure_count,
            "recent_triggers": self._circuit_breaker_history[-10:],
        }

    async def update_symbol_return(self, symbol: str, return_pct: float):
        """Track per-symbol returns for correlation and portfolio VaR."""
        if symbol not in self._symbol_returns:
            self._symbol_returns[symbol] = []
        self._symbol_returns[symbol].append(return_pct)
        if len(self._symbol_returns[symbol]) > self._correlation_lookback:
            self._symbol_returns[symbol] = self._symbol_returns[symbol][-self._correlation_lookback:]

    def update_symbol_position(self, symbol: str, notional: float, pnl: float = 0.0):
        """Track current position per symbol for portfolio risk."""
        self._symbol_positions[symbol] = {
            "notional": notional,
            "pnl": pnl,
            "timestamp": self.clock.now,
        }

    def remove_symbol_position(self, symbol: str):
        """Remove a symbol from tracked positions."""
        self._symbol_positions.pop(symbol, None)

    def get_portfolio_notional(self) -> float:
        """Total notional exposure across all positions."""
        return sum(pos.get("notional", 0.0) for pos in self._symbol_positions.values())

    def get_portfolio_pnl(self) -> float:
        """Total unrealized PnL across all positions."""
        return sum(pos.get("pnl", 0.0) for pos in self._symbol_positions.values())

    def compute_correlation_matrix(self) -> Optional[np.ndarray]:
        """Compute rolling correlation matrix across all tracked symbols."""
        symbols = sorted(self._symbol_returns.keys())
        if len(symbols) < 2:
            return None

        min_len = min(len(self._symbol_returns[s]) for s in symbols)
        if min_len < 10:
            return None

        returns_matrix = np.array([self._symbol_returns[s][-min_len:] for s in symbols])
        if np.std(returns_matrix, axis=1).min() == 0:
            return None

        corr = np.corrcoef(returns_matrix)
        corr = np.nan_to_num(corr, nan=0.0)
        corr = np.clip(corr, -1.0, 1.0)
        np.fill_diagonal(corr, 1.0)

        self._correlation_matrix = corr
        self._correlation_symbols = symbols
        return corr

    def get_correlation_matrix(self) -> Dict[str, Any]:
        """Return correlation matrix as a serializable dict."""
        if self._correlation_matrix is None:
            self.compute_correlation_matrix()

        if self._correlation_matrix is None:
            return {"error": "Insufficient data for correlation matrix"}

        matrix = self._correlation_matrix.tolist()
        symbols = self._correlation_symbols
        return {
            "symbols": symbols,
            "matrix": matrix,
            "lookback": min(len(self._symbol_returns.get(s, [])) for s in symbols) if symbols else 0,
        }

    def calculate_portfolio_var(self, confidence: float = 0.95, n_simulations: int = 10000) -> Dict[str, Any]:
        """
        Calculate portfolio VaR using Monte Carlo simulation.

        Uses the correlation matrix and per-symbol return distributions
        to simulate portfolio outcomes and estimate VaR/CVaR.
        """
        symbols = sorted(self._symbol_returns.keys())
        if len(symbols) < 2:
            return self.get_var_status(self._trade_returns)

        min_len = min(len(self._symbol_returns[s]) for s in symbols)
        if min_len < 10:
            return {"error": "Insufficient data for portfolio VaR"}

        returns_matrix = np.array([self._symbol_returns[s][-min_len:] for s in symbols])
        mean_returns = np.mean(returns_matrix, axis=1)
        std_returns = np.std(returns_matrix, axis=1)

        corr = self.compute_correlation_matrix()
        if corr is None:
            return {"error": "Could not compute correlation matrix"}

        cov_matrix = np.outer(std_returns, std_returns) * corr

        try:
            L = np.linalg.cholesky(cov_matrix)
        except np.linalg.LinAlgError:
            corr += np.eye(len(symbols)) * 1e-6
            cov_matrix = np.outer(std_returns, std_returns) * corr
            try:
                L = np.linalg.cholesky(cov_matrix)
            except np.linalg.LinAlgError:
                return {"error": "Cholesky decomposition failed"}

        z = np.random.standard_normal((n_simulations, len(symbols)))
        correlated_z = z @ L.T
        simulated_returns = mean_returns + correlated_z * std_returns

        portfolio_notional = self.get_portfolio_notional()
        if portfolio_notional <= 0:
            portfolio_notional = self.current_equity

        portfolio_pnl_sim = np.sum(simulated_returns, axis=1) * portfolio_notional

        var_pct = np.percentile(portfolio_pnl_sim, (1 - confidence) * 100)
        cvar_pct = np.mean(portfolio_pnl_sim[portfolio_pnl_sim <= var_pct]) if np.any(portfolio_pnl_sim <= var_pct) else var_pct

        return {
            "portfolio_var": abs(var_pct),
            "portfolio_cvar": abs(cvar_pct),
            "confidence": confidence,
            "n_simulations": n_simulations,
            "portfolio_notional": portfolio_notional,
            "n_symbols": len(symbols),
            "symbols": symbols,
            "var_pct_of_equity": abs(var_pct) / self.current_equity if self.current_equity > 0 else 0,
            "cvar_pct_of_equity": abs(cvar_pct) / self.current_equity if self.current_equity > 0 else 0,
        }

    def check_portfolio_risk_limits(self) -> Dict[str, Any]:
        """Check if current portfolio is within risk limits."""
        portfolio_notional = self.get_portfolio_notional()
        portfolio_risk_pct = portfolio_notional / self.current_equity if self.current_equity > 0 else 0

        violations = []
        if portfolio_risk_pct > self._max_portfolio_risk:
            violations.append(f"Portfolio risk {portfolio_risk_pct:.2%} > max {self._max_portfolio_risk:.2%}")

        for symbol, pos in self._symbol_positions.items():
            pos_risk = abs(pos.get("notional", 0)) / self.current_equity if self.current_equity > 0 else 0
            if pos_risk > self._max_single_position_risk:
                violations.append(f"{symbol} risk {pos_risk:.2%} > max single {self._max_single_position_risk:.2%}")

        return {
            "portfolio_notional": portfolio_notional,
            "portfolio_risk_pct": portfolio_risk_pct,
            "max_portfolio_risk": self._max_portfolio_risk,
            "max_single_position_risk": self._max_single_position_risk,
            "n_positions": len(self._symbol_positions),
            "within_limits": len(violations) == 0,
            "violations": violations,
        }

    async def get_portfolio_risk_status(self) -> Dict[str, Any]:
        """Comprehensive portfolio risk status."""
        var_status = self.calculate_portfolio_var(confidence=self._var_confidence)
        corr_status = self.get_correlation_matrix()
        limits_status = self.check_portfolio_risk_limits()
        single_var = await self.get_var_status(self._trade_returns)

        return {
            "portfolio": limits_status,
            "monte_carlo_var": var_status,
            "correlation": corr_status,
            "single_asset_var": single_var,
            "total_exposure": self.get_portfolio_notional(),
            "total_pnl": self.get_portfolio_pnl(),
            "current_equity": self.current_equity,
        }
