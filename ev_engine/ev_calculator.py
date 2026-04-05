"""
Expected Value Engine Module
Calculates expected value of trading signals.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

import numpy as np

from core.clock import EventClock
from models.trade import MarketEvent, Signal, EVResult, SignalType

logger = logging.getLogger(__name__)


class EVEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.historical_performance: Dict[str, Dict[str, Any]] = {}

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing EV Engine...")
            self.historical_performance = {}
            self.is_initialized = True
            logger.info("EV Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize EV Engine: {e}")
            return False

    async def calculate_ev(self, signals: List[Signal], event: MarketEvent,
                           regime_result=None) -> Optional[List[EVResult]]:
        if not self.is_initialized:
            return None

        try:
            ev_results = []
            min_ev_threshold = self.settings.get("min_ev_threshold", 0.0)
            for signal in signals:
                ev_score = await self._calculate_signal_ev(signal, regime_result)
                actionable = ev_score > min_ev_threshold
                ev_results.append(EVResult.from_signal(signal, ev_score, actionable))

            logger.debug(f"Calculated EV for {len(ev_results)} signals")
            return ev_results if ev_results else None

        except Exception as e:
            logger.error(f"Error calculating EV: {e}")
            return None

    async def _calculate_signal_ev(self, signal: Signal, regime_result=None) -> float:
        try:
            strategy = signal.strategy
            key = f"{strategy}_{signal.symbol}_{signal.signal_type.value}"

            if key not in self.historical_performance:
                # Default: win rate 50%, avg_win 2%, avg_loss 1.5%
                # This gives positive EV: 0.5 * 0.02 - 0.5 * 0.015 = 0.0025
                self.historical_performance[key] = {
                    "win_rate": 0.50,
                    "avg_win": 0.02,
                    "avg_loss": 0.015,
                    "sample_size": 0,
                }

            perf = self.historical_performance[key]
            strength_factor = 0.5 + (signal.strength * 0.5)

            regime_scaling = 1.0
            if regime_result:
                regime = regime_result.regime.value if hasattr(regime_result, "regime") else regime_result.get("regime", "MIXED")
                confidence = regime_result.confidence if hasattr(regime_result, "confidence") else regime_result.get("confidence", 0.0)
                # More favorable regimes get higher scaling
                regime_map = {"TRENDING": 1.2, "RANGING": 1.0, "VOLATILE": 0.7, "MIXED": 1.1}
                regime_scaling = regime_map.get(regime, 1.0) * (0.5 + confidence * 0.5)

            base_win_rate = perf["win_rate"]
            adjusted_win_rate = min(0.95, base_win_rate * strength_factor * regime_scaling)
            prob_loss = 1.0 - adjusted_win_rate
            
            # Use asymmetric multipliers - wins should be larger than losses
            avg_win = perf["avg_win"] * strength_factor * regime_scaling
            avg_loss = perf["avg_loss"] * strength_factor  # Losses not scaled by regime

            ev = (adjusted_win_rate * avg_win) - (prob_loss * avg_loss)

            if abs(ev) < 0.00001:
                ev = 0.0

            return ev

        except Exception as e:
            logger.error(f"Error calculating EV for signal {signal}: {e}")
            return 0.0

    async def update_performance(self, symbol: str, strategy: str,
                                 signal_type: str, profit: float):
        try:
            key = f"{strategy}_{symbol}_{signal_type}"

            if key not in self.historical_performance:
                self.historical_performance[key] = {
                    "win_rate": 0.5,
                    "avg_win": 0.02,
                    "avg_loss": 0.015,
                    "sample_size": 0,
                }

            perf = self.historical_performance[key]
            perf["sample_size"] += 1

            if profit > 0:
                perf["win_rate"] = ((perf["win_rate"] * (perf["sample_size"] - 1)) + 1.0) / perf["sample_size"]
                if perf["sample_size"] == 1:
                    perf["avg_win"] = profit
                else:
                    perf["avg_win"] = ((perf["avg_win"] * (perf["sample_size"] - 1)) + profit) / perf["sample_size"]
            else:
                perf["win_rate"] = ((perf["win_rate"] * (perf["sample_size"] - 1)) + 0.0) / perf["sample_size"]
                loss_amount = abs(profit)
                if perf["sample_size"] == 1:
                    perf["avg_loss"] = loss_amount
                else:
                    perf["avg_loss"] = ((perf["avg_loss"] * (perf["sample_size"] - 1)) + loss_amount) / perf["sample_size"]

            logger.debug(f"Updated performance for {key}: win_rate={perf['win_rate']:.3f}")

        except Exception as e:
            logger.error(f"Error updating performance: {e}")

    async def get_performance_stats(self) -> Dict[str, Any]:
        return self.historical_performance.copy()

    async def shutdown(self):
        logger.info("Shutting down EV Engine...")
        self.is_initialized = False
        self.historical_performance.clear()
        logger.info("EV Engine shutdown complete")
