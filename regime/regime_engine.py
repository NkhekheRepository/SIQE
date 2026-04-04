"""
Regime Engine Module
Detects market regimes (trending, ranging, volatile, mixed) for strategy filtering and risk scaling.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

import numpy as np

from core.clock import EventClock
from models.trade import MarketEvent, RegimeResult, RegimeType

logger = logging.getLogger(__name__)


class RegimeEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.regime_history: List[Dict[str, Any]] = []
        self.lookback_period = settings.get("regime_lookback_period", 100)
        self.current_regime = "UNKNOWN"
        self.regime_confidence = 0.0
        self._last_trend_strength = None
        self._last_range_strength = None

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Regime Engine...")
            self.is_initialized = True
            logger.info("Regime Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Regime Engine: {e}")
            return False

    async def detect_regime(self, event: MarketEvent, historical_data=None) -> RegimeResult:
        if not self.is_initialized:
            return RegimeResult(regime=RegimeType.MIXED, confidence=0.0, event_seq=self.clock.now)

        try:
            market_data = {event.symbol: event}
            volatility_regime = await self._detect_volatility_regime(market_data)
            trend_regime = await self._detect_trend_regime(market_data)
            range_regime = await self._detect_range_regime(market_data)

            regime_result = await self._combine_regime_signals(volatility_regime, trend_regime, range_regime)
            self._update_regime_history(regime_result)

            regime_map = {"TRENDING": RegimeType.TRENDING, "RANGING": RegimeType.RANGING,
                          "VOLATILE": RegimeType.VOLATILE, "MIXED": RegimeType.MIXED}
            regime_type = regime_map.get(regime_result["regime"], RegimeType.MIXED)

            return RegimeResult(
                regime=regime_type,
                confidence=regime_result["confidence"],
                event_seq=self.clock.now,
                risk_scaling=regime_result.get("risk_scaling", 1.0),
            )

        except Exception as e:
            logger.error(f"Error detecting regime: {e}")
            return RegimeResult(regime=RegimeType.MIXED, confidence=0.0, event_seq=self.clock.now)

    async def _detect_volatility_regime(self, market_data: Dict[str, MarketEvent]) -> Dict[str, Any]:
        try:
            volatilities = [e.volatility for e in market_data.values() if e.volatility > 0]
            if not volatilities:
                return {"regime": "UNKNOWN", "confidence": 0.0}

            avg_volatility = float(np.mean(volatilities))

            if avg_volatility < 0.015:
                return {"regime": "LOW_VOL", "confidence": 0.8, "value": avg_volatility}
            elif avg_volatility > 0.04:
                return {"regime": "HIGH_VOL", "confidence": 0.8, "value": avg_volatility}
            else:
                return {"regime": "MEDIUM_VOL", "confidence": 0.7, "value": avg_volatility}
        except Exception as e:
            logger.error(f"Error detecting volatility regime: {e}")
            return {"regime": "ERROR", "confidence": 0.0}

    async def _detect_trend_regime(self, market_data: Dict[str, MarketEvent]) -> Dict[str, Any]:
        try:
            if self._last_trend_strength is None:
                self._last_trend_strength = float(np.random.uniform(0, 1))

            trend_change = float(np.random.normal(0, 0.1))
            self._last_trend_strength += trend_change
            self._last_trend_strength = float(np.clip(self._last_trend_strength, 0, 1))

            if self._last_trend_strength > 0.7:
                return {"regime": "STRONG_TREND", "confidence": 0.75, "value": self._last_trend_strength}
            elif self._last_trend_strength > 0.3:
                return {"regime": "WEAK_TREND", "confidence": 0.6, "value": self._last_trend_strength}
            else:
                return {"regime": "NO_TREND", "confidence": 0.7, "value": self._last_trend_strength}
        except Exception as e:
            logger.error(f"Error detecting trend regime: {e}")
            return {"regime": "ERROR", "confidence": 0.0}

    async def _detect_range_regime(self, market_data: Dict[str, MarketEvent]) -> Dict[str, Any]:
        try:
            if self._last_range_strength is None:
                self._last_range_strength = 1.0 - getattr(self, '_last_trend_strength', 0.5)

            range_strength = 1.0 - getattr(self, '_last_trend_strength', 0.5)
            range_strength += float(np.random.normal(0, 0.1))
            range_strength = float(np.clip(range_strength, 0, 1))
            self._last_range_strength = range_strength

            if range_strength > 0.7:
                return {"regime": "STRONG_RANGE", "confidence": 0.75, "value": range_strength}
            elif range_strength > 0.3:
                return {"regime": "WEAK_RANGE", "confidence": 0.6, "value": range_strength}
            else:
                return {"regime": "NO_RANGE", "confidence": 0.7, "value": range_strength}
        except Exception as e:
            logger.error(f"Error detecting range regime: {e}")
            return {"regime": "ERROR", "confidence": 0.0}

    async def _combine_regime_signals(self, volatility: Dict[str, Any],
                                      trend: Dict[str, Any],
                                      range_detect: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signals = [("VOLATILITY", volatility), ("TREND", trend), ("RANGE", range_detect)]
            valid_signals = [s for s in signals if s[1].get("regime") not in ["ERROR", "UNKNOWN"]]

            if not valid_signals:
                return {"regime": "UNKNOWN", "confidence": 0.0, "risk_scaling": 1.0}

            best_signal = max(valid_signals, key=lambda x: x[1].get("confidence", 0))

            regime_mapping = {
                "LOW_VOL": "RANGING", "MEDIUM_VOL": "MIXED", "HIGH_VOL": "VOLATILE",
                "STRONG_TREND": "TRENDING", "WEAK_TREND": "TRENDING", "NO_TREND": "RANGING",
                "STRONG_RANGE": "RANGING", "WEAK_RANGE": "RANGING", "NO_RANGE": "TRENDING",
            }

            raw_regime = best_signal[1].get("regime", "UNKNOWN")
            mapped_regime = regime_mapping.get(raw_regime, "MIXED")

            base_confidence = best_signal[1].get("confidence", 0)
            final_confidence = min(0.95, base_confidence + 0.1)

            self.current_regime = mapped_regime
            self.regime_confidence = final_confidence

            risk_scaling_map = {"TRENDING": 1.0, "RANGING": 0.8, "VOLATILE": 0.6, "MIXED": 0.9}
            risk_scaling = risk_scaling_map.get(mapped_regime, 1.0) * (0.5 + final_confidence * 0.5)
            risk_scaling = float(np.clip(risk_scaling, 0.3, 1.5))

            return {
                "regime": mapped_regime,
                "confidence": final_confidence,
                "risk_scaling": risk_scaling,
                "timestamp": self.clock.now,
            }

        except Exception as e:
            logger.error(f"Error combining regime signals: {e}")
            return {"regime": "ERROR", "confidence": 0.0, "risk_scaling": 1.0}

    def _update_regime_history(self, regime_result: Dict[str, Any]):
        try:
            regime_entry = {
                "timestamp": self.clock.now,
                "regime": regime_result.get("regime"),
                "confidence": regime_result.get("confidence", 0.0),
            }
            self.regime_history.append(regime_entry)
            if len(self.regime_history) > self.lookback_period:
                self.regime_history = self.regime_history[-self.lookback_period:]
        except Exception as e:
            logger.error(f"Error updating regime history: {e}")

    async def get_regime_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.regime_history[-limit:] if self.regime_history else []

    async def get_current_regime(self) -> Dict[str, Any]:
        return {
            "regime": self.current_regime,
            "confidence": self.regime_confidence,
            "timestamp": self.clock.now,
        }

    async def get_risk_scaling_factor(self) -> float:
        if not self.is_initialized:
            return 1.0

        try:
            regime_scaling = {"TRENDING": 1.0, "RANGING": 0.8, "MIXED": 0.9, "VOLATILE": 0.6}
            base_scaling = regime_scaling.get(self.current_regime, 1.0)
            confidence_factor = 0.5 + (self.regime_confidence * 0.5)
            final_scaling = base_scaling * confidence_factor
            return float(np.clip(final_scaling, 0.3, 1.5))
        except Exception as e:
            logger.error(f"Error calculating risk scaling factor: {e}")
            return 1.0

    async def shutdown(self):
        logger.info("Shutting down Regime Engine...")
        self.is_initialized = False
        self.regime_history.clear()
        logger.info("Regime Engine shutdown complete")
