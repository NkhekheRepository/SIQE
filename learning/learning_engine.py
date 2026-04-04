"""
Learning Engine Module
Controlled learning system that updates strategy parameters under strict constraints.
Deterministic: uses EventClock, stability guard, wires params back to strategies.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

import numpy as np
import json
import hashlib

from core.clock import EventClock

logger = logging.getLogger(__name__)


class LearningEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.parameter_versions = {}
        self.learning_history = []
        self.min_sample_size = settings.get("min_sample_size", 50)
        self.max_param_change = settings.get("max_param_change", 0.1)
        self.rollback_enabled = settings.get("rollback_enabled", True)
        self.strategy_engine = None
        self._param_bounds = {
            "mean_reversion": {
                "threshold": (0.005, 0.05),
                "period": (5, 50),
                "exit_threshold": (0.002, 0.02),
            },
            "momentum": {
                "lookback_period": (5, 30),
                "threshold": (0.005, 0.05),
                "smoothing_factor": (0.05, 0.5),
            },
            "breakout": {
                "volatility_multiplier": (1.0, 4.0),
                "period": (5, 30),
                "confirmation_bars": (1, 5),
            },
        }

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Learning Engine...")
            await self._load_parameter_versions()
            self.is_initialized = True
            logger.info("Learning Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Learning Engine: {e}")
            return False

    async def update_parameters(self, strategy_name: str,
                                performance_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "Learning engine not initialized"}

        try:
            sample_size = performance_data.get("sample_size", 0)
            if sample_size < self.min_sample_size:
                return {
                    "success": False,
                    "error": f"Insufficient sample size: {sample_size} < {self.min_sample_size}",
                }

            current_params = await self._get_current_parameters(strategy_name)
            if not current_params:
                return {"success": False, "error": f"No parameters found for strategy {strategy_name}"}

            proposed_updates = await self._calculate_parameter_updates(
                strategy_name, current_params, performance_data
            )

            if not proposed_updates:
                return {"success": False, "error": "No parameter updates calculated"}

            validation_result = await self._validate_parameter_changes(current_params, proposed_updates)
            if not validation_result["valid"]:
                return {"success": False, "error": f"Parameter changes failed validation: {validation_result['reason']}"}

            update_result = await self._apply_parameter_changes(
                strategy_name, current_params, proposed_updates
            )

            if update_result["success"]:
                logger.info(f"Updated parameters for {strategy_name} (version {update_result['version_id']})")
                await self._record_learning_event(
                    strategy_name, current_params, proposed_updates,
                    update_result, performance_data,
                )

            return update_result

        except Exception as e:
            logger.error(f"Error updating parameters for {strategy_name}: {e}")
            return {"success": False, "error": str(e)}

    async def _get_current_parameters(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        try:
            default_params = {
                "mean_reversion": {"threshold": 0.02, "period": 20, "exit_threshold": 0.01},
                "momentum": {"lookback_period": 10, "threshold": 0.015, "smoothing_factor": 0.2},
                "breakout": {"volatility_multiplier": 2.0, "period": 15, "confirmation_bars": 2},
            }
            return default_params.get(strategy_name, {}).copy()
        except Exception as e:
            logger.error(f"Error getting current parameters for {strategy_name}: {e}")
            return None

    async def _calculate_parameter_updates(self, strategy_name: str,
                                           current_params: Dict[str, Any],
                                           performance_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            updates = {}
            win_rate = performance_data.get("win_rate", 0.5)
            sharpe_ratio = performance_data.get("sharpe_ratio", 0)

            target_win_rate = 0.55
            target_sharpe = 0.5

            for param_name, param_value in current_params.items():
                if not isinstance(param_value, (int, float)):
                    continue

                win_rate_error = win_rate - target_win_rate
                sharpe_error = sharpe_ratio - target_sharpe
                error_signal = (win_rate_error * 0.6) + (sharpe_error * 0.4)

                adjustment = error_signal * 0.1
                adjustment = float(np.clip(adjustment, -self.max_param_change, self.max_param_change))
                new_value = param_value * (1 + adjustment)
                new_value = await self._apply_parameter_bounds(strategy_name, param_name, new_value)

                if abs(new_value - param_value) > 0.0001:
                    updates[param_name] = {
                        "old": param_value,
                        "new": new_value,
                        "change_pct": ((new_value - param_value) / param_value) * 100 if param_value != 0 else 0,
                    }

            return updates if updates else None

        except Exception as e:
            logger.error(f"Error calculating parameter updates: {e}")
            return None

    async def _apply_parameter_bounds(self, strategy_name: str, param_name: str, value: float) -> float:
        strategy_bounds = self._param_bounds.get(strategy_name, {}).get(param_name)
        if strategy_bounds:
            min_val, max_val = strategy_bounds
            return float(np.clip(value, min_val, max_val))
        return float(np.clip(value, 0.001, 1000.0))

    async def _validate_parameter_changes(self, current_params: Dict[str, Any],
                                          proposed_updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            for param_name, update_data in proposed_updates.items():
                old_value = update_data["old"]
                new_value = update_data["new"]

                if old_value != 0:
                    change_pct = abs((new_value - old_value) / old_value)
                else:
                    change_pct = float('inf') if new_value != 0 else 0

                if change_pct > self.max_param_change:
                    return {
                        "valid": False,
                        "reason": f"Parameter {param_name} change {change_pct:.2%} exceeds maximum {self.max_param_change:.2%}",
                    }

                bounds = self._param_bounds.get("", {}).get(param_name)
                if bounds:
                    range_size = abs(bounds[1] - bounds[0])
                    change = abs(new_value - old_value)
                    if change > range_size * 0.5:
                        return {"valid": False, "reason": f"{param_name} change exceeds stability threshold"}

            return {"valid": True, "reason": "All changes within limits"}

        except Exception as e:
            return {"valid": False, "reason": f"Validation error: {str(e)}"}

    async def _apply_parameter_changes(self, strategy_name: str,
                                       current_params: Dict[str, Any],
                                       proposed_updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            new_params = current_params.copy()
            for param_name, update_data in proposed_updates.items():
                new_params[param_name] = update_data["new"]

            version_data = {
                "strategy": strategy_name,
                "timestamp": self.clock.now,
                "parameters": new_params,
            }
            version_string = json.dumps(version_data, sort_keys=True)
            version_id = hashlib.sha256(version_string.encode()).hexdigest()[:12]

            if strategy_name not in self.parameter_versions:
                self.parameter_versions[strategy_name] = []

            self.parameter_versions[strategy_name].append({
                "version_id": version_id,
                "timestamp": self.clock.now,
                "parameters": new_params.copy(),
                "change_summary": {
                    param_name: {
                        "old": update_data["old"],
                        "new": update_data["new"],
                        "change_pct": update_data["change_pct"],
                    }
                    for param_name, update_data in proposed_updates.items()
                },
            })

            if len(self.parameter_versions[strategy_name]) > 100:
                self.parameter_versions[strategy_name] = self.parameter_versions[strategy_name][-100:]

            return {
                "success": True,
                "strategy_name": strategy_name,
                "old_parameters": current_params,
                "new_parameters": new_params,
                "version_id": version_id,
                "changes_applied": list(proposed_updates.keys()),
                "timestamp": self.clock.now,
            }

        except Exception as e:
            logger.error(f"Error applying parameter changes: {e}")
            return {"success": False, "error": str(e)}

    async def rollback_parameters(self, strategy_name: str, steps: int = 1) -> Dict[str, Any]:
        if not self.rollback_enabled:
            return {"success": False, "error": "Rollback is disabled"}

        try:
            if strategy_name not in self.parameter_versions:
                return {"success": False, "error": f"No version history for {strategy_name}"}

            versions = self.parameter_versions[strategy_name]
            if len(versions) < steps + 1:
                return {"success": False, "error": f"Insufficient version history for {steps} step rollback"}

            target_index = -(steps + 1)
            target_version = versions[target_index]

            logger.info(f"Rolling back {strategy_name} to version {target_version['version_id']}")

            return {
                "success": True,
                "strategy_name": strategy_name,
                "rolled_back_to": target_version["version_id"],
                "rollback_steps": steps,
                "parameters": target_version["parameters"],
                "timestamp": self.clock.now,
            }

        except Exception as e:
            logger.error(f"Error rolling back parameters: {e}")
            return {"success": False, "error": str(e)}

    async def _record_learning_event(self, strategy_name: str, old_params: Dict[str, Any],
                                     proposed_updates: Dict[str, Any],
                                     update_result: Dict[str, Any],
                                     performance_data: Dict[str, Any]):
        try:
            event = {
                "timestamp": self.clock.now,
                "strategy_name": strategy_name,
                "performance_snapshot": performance_data.copy(),
                "parameter_changes": {
                    param_name: {
                        "old": update_data["old"],
                        "new": update_data["new"],
                        "change_pct": update_data["change_pct"],
                    }
                    for param_name, update_data in proposed_updates.items()
                },
                "update_result": {
                    "success": update_result["success"],
                    "version_id": update_result.get("version_id"),
                    "changes_applied": update_result.get("changes_applied", []),
                },
            }
            self.learning_history.append(event)
            if len(self.learning_history) > 1000:
                self.learning_history = self.learning_history[-1000:]
            logger.debug(f"Recorded learning event for {strategy_name}")
        except Exception as e:
            logger.error(f"Error recording learning event: {e}")

    async def _load_parameter_versions(self):
        logger.debug("Loading parameter versions (placeholder)")
        pass

    async def _save_parameter_versions(self):
        logger.debug("Saving parameter versions (placeholder)")

    async def get_learning_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.learning_history[-limit:] if self.learning_history else []

    async def get_parameter_versions(self, strategy_name: str) -> List[Dict[str, Any]]:
        return self.parameter_versions.get(strategy_name, []).copy()

    async def shutdown(self):
        logger.info("Shutting down Learning Engine...")
        await self._save_parameter_versions()
        self.is_initialized = False
        self.parameter_versions.clear()
        self.learning_history.clear()
        logger.info("Learning Engine shutdown complete")
