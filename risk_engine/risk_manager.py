"""
Risk Engine Module
Enforces risk limits and validates trades against risk parameters.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import Dict, Any, Optional

import numpy as np

from core.clock import EventClock
from models.trade import Decision, ApprovalResult

logger = logging.getLogger(__name__)


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

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Risk Engine...")
            self.is_initialized = True
            logger.info("Risk Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Risk Engine: {e}")
            return False

    async def validate_trade(self, decision: Decision, risk_scaling: Optional[float] = None) -> ApprovalResult:
        if not self.is_initialized:
            return ApprovalResult(approved=False, reason="Risk engine not initialized", event_seq=decision.event_seq)

        try:
            await self._reset_hourly_counter()

            if self.trade_count_hour >= self.risk_limits["max_trades_per_hour"]:
                return ApprovalResult(
                    approved=False,
                    reason=f"Hourly trade limit exceeded ({self.trade_count_hour}/{self.risk_limits['max_trades_per_hour']})",
                    event_seq=decision.event_seq,
                )

            daily_loss_pct = abs(self.daily_pnl) / self.current_equity if self.current_equity > 0 else 0
            if self.daily_pnl < 0 and daily_loss_pct >= self.risk_limits["max_daily_loss"]:
                return ApprovalResult(
                    approved=False,
                    reason=f"Daily loss limit exceeded ({daily_loss_pct:.2%} >= {self.risk_limits['max_daily_loss']:.2%})",
                    event_seq=decision.event_seq,
                )

            current_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
            if current_drawdown >= self.risk_limits["max_drawdown"]:
                return ApprovalResult(
                    approved=False,
                    reason=f"Maximum drawdown exceeded ({current_drawdown:.2%} >= {self.risk_limits['max_drawdown']:.2%})",
                    event_seq=decision.event_seq,
                )

            if self.consecutive_losses >= self.risk_limits["max_consecutive_losses"]:
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

    async def shutdown(self):
        logger.info("Shutting down Risk Engine...")
        self.is_initialized = False
        logger.info("Risk Engine shutdown complete")
