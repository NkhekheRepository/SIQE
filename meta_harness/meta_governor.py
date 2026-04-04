"""
Meta Harness Module
System governor that controls trade validation, risk enforcement, and system state.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

from core.clock import EventClock
from models.trade import Decision, ApprovalResult, SystemState

logger = logging.getLogger(__name__)


class MetaHarness:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.system_state = SystemState.INITIALIZING
        self.override_active = False
        self.override_reason = ""

        self.kill_conditions = {
            "max_drawdown": self.settings.get("max_drawdown", 0.20),
            "max_consecutive_losses": self.settings.get("max_consecutive_losses", 5),
            "pnl_deviation_threshold": self.settings.get("pnl_deviation_threshold", 3.0),
            "min_trades_for_anomaly_detection": self.settings.get("min_trades_for_anomaly_detection", 20),
        }

        self.recent_pnls: List[float] = []
        self.max_recent_pnls = 100

        self.can_override_trading = True
        self.can_modify_risk_limits = False
        self.can_halt_system = True

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Meta Harness...")
            self.is_initialized = True
            self.system_state = SystemState.NORMAL
            logger.info("Meta Harness initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Meta Harness: {e}")
            return False

    async def validate_trade(self, decision: Decision) -> ApprovalResult:
        if not self.is_initialized:
            return ApprovalResult(approved=False, reason="Meta Harness not initialized", event_seq=decision.event_seq)

        if self.system_state == SystemState.HALTED:
            return ApprovalResult(approved=False, reason="System is halted", event_seq=decision.event_seq)

        if self.override_active:
            return ApprovalResult(approved=False, reason=f"Override active: {self.override_reason}", event_seq=decision.event_seq)

        if self.system_state not in [SystemState.NORMAL, SystemState.DEGRADED]:
            return ApprovalResult(
                approved=False,
                reason=f"System state {self.system_state.value} does not allow trading",
                event_seq=decision.event_seq,
            )

        try:
            min_ev = self.settings.get("min_ev_threshold", 0.01)
            if decision.ev_score < min_ev:
                return ApprovalResult(
                    approved=False,
                    reason=f"EV score {decision.ev_score:.4f} below meta threshold {min_ev}",
                    event_seq=decision.event_seq,
                )

            restricted_symbols = self.settings.get("restricted_symbols", [])
            if decision.symbol in restricted_symbols:
                return ApprovalResult(
                    approved=False,
                    reason=f"Symbol {decision.symbol} is restricted",
                    event_seq=decision.event_seq,
                )

            return ApprovalResult(
                approved=True,
                reason="Meta Harness validation passed",
                event_seq=decision.event_seq,
                details={"meta_approved_at": self.clock.now},
            )

        except Exception as e:
            logger.error(f"Error in Meta Harness validation: {e}")
            return ApprovalResult(approved=False, reason=f"Meta Harness error: {str(e)}", event_seq=decision.event_seq)

    async def update_system_state(self, performance_data: Dict[str, Any]):
        if not self.is_initialized:
            return

        try:
            old_state = self.system_state
            current_drawdown = performance_data.get("current_drawdown", 0.0)
            daily_pnl = performance_data.get("daily_pnl", 0.0)
            total_trades = performance_data.get("total_trades", 0)
            recent_pnl = performance_data.get("recent_pnl", 0.0)

            if recent_pnl != 0:
                self.recent_pnls.append(recent_pnl)
                if len(self.recent_pnls) > self.max_recent_pnls:
                    self.recent_pnls.pop(0)

            kill_triggered, kill_reason = await self._check_kill_conditions(
                current_drawdown, daily_pnl, total_trades
            )

            if kill_triggered:
                await self._trigger_kill_switch(kill_reason)
                return

            new_state = await self._determine_system_state(
                current_drawdown, len(self.recent_pnls), performance_data
            )

            if new_state != self.system_state:
                self.system_state = new_state
                logger.info(f"System state changed: {old_state.value} -> {new_state.value}")

        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    async def _check_kill_conditions(self, drawdown: float, daily_pnl: float,
                                     total_trades: int) -> tuple:
        if drawdown >= self.kill_conditions["max_drawdown"]:
            return True, f"Drawdown exceeded limit: {drawdown:.2%} >= {self.kill_conditions['max_drawdown']:.2%}"

        if (total_trades >= self.kill_conditions["min_trades_for_anomaly_detection"] and
                len(self.recent_pnls) >= 10):
            anomaly_detected = await self._check_pnl_anomaly()
            if anomaly_detected:
                return True, "PnL deviation anomaly detected"

        return False, ""

    async def _check_pnl_anomaly(self) -> bool:
        if len(self.recent_pnls) < 10:
            return False

        try:
            recent_mean = sum(self.recent_pnls[-10:]) / 10
            historical_mean = sum(self.recent_pnls[:-10]) / max(1, len(self.recent_pnls[:-10])) if len(self.recent_pnls) > 10 else recent_mean

            if historical_mean == 0:
                return False

            deviation = abs(recent_mean - historical_mean) / abs(historical_mean) if historical_mean != 0 else float('inf')
            return deviation > 0.5

        except Exception as e:
            logger.error(f"Error checking PnL anomaly: {e}")
            return False

    async def _trigger_kill_switch(self, reason: str):
        logger.critical(f"KILL SWITCH TRIGGERED: {reason}")
        self.system_state = SystemState.CRITICAL
        self.override_active = True
        self.override_reason = reason

    async def _determine_system_state(self, drawdown: float, recent_trades_count: int,
                                      performance_data: Dict[str, Any]) -> SystemState:
        if drawdown >= 0.15:
            return SystemState.DEGRADED
        return SystemState.NORMAL

    async def halt_system(self, reason: str = "Manual halt requested") -> Dict[str, Any]:
        logger.warning(f"Manual system halt requested: {reason}")
        self.system_state = SystemState.HALTED
        self.override_active = True
        self.override_reason = reason

        return {
            "success": True,
            "message": f"System halted: {reason}",
            "timestamp": self.clock.now,
        }

    async def resume_system(self) -> Dict[str, Any]:
        if self.system_state != SystemState.HALTED:
            return {
                "success": False,
                "message": f"System not in halted state (current: {self.system_state.value})"
            }

        logger.info("Manual system resume requested")
        self.system_state = SystemState.NORMAL
        self.override_active = False
        self.override_reason = ""

        return {
            "success": True,
            "message": "System resumed",
            "timestamp": self.clock.now,
        }

    async def adjust_risk_parameters(self, adjustments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.can_modify_risk_limits:
            return {"success": False, "message": "Risk parameter modification not allowed"}

        logger.info(f"Risk parameters adjusted: {adjustments}")
        return {"success": True, "message": "Risk parameters adjusted", "adjustments": adjustments}

    async def disable_strategy(self, strategy_name: str) -> Dict[str, Any]:
        logger.info(f"Strategy disable requested: {strategy_name}")
        return {
            "success": True,
            "message": f"Strategy {strategy_name} disable requested",
            "timestamp": self.clock.now,
        }

    async def update_performance_metrics(self, feedback_data: Dict[str, Any]) -> None:
        try:
            pnl = feedback_data.get("pnl", 0)
            trade_type = feedback_data.get("trade_type", "unknown")
            if trade_type == "successful" and pnl != 0:
                self.recent_pnls.append(pnl)
                if len(self.recent_pnls) > self.max_recent_pnls:
                    self.recent_pnls = self.recent_pnls[-self.max_recent_pnls:]
        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

    async def get_status(self) -> Dict[str, Any]:
        return {
            "system_state": self.system_state.value,
            "override_active": self.override_active,
            "override_reason": self.override_reason,
            "can_override_trading": self.can_override_trading,
            "can_modify_risk_limits": self.can_modify_risk_limits,
            "can_halt_system": self.can_halt_system,
            "recent_pnls_count": len(self.recent_pnls),
            "kill_conditions": self.kill_conditions,
            "timestamp": self.clock.now,
        }

    async def shutdown(self):
        logger.info("Shutting down Meta Harness...")
        self.is_initialized = False
        self.system_state = SystemState.SHUTDOWN
        logger.info("Meta Harness shutdown complete")
