"""
Decision Engine Module
Makes trading decisions based on EV scores.
Deterministic: uses EventClock instead of datetime.now().
"""
import asyncio
import logging
from typing import List, Optional

from core.clock import EventClock
from models.trade import EVResult, Decision, SignalType

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Decision Engine...")
            self.is_initialized = True
            logger.info("Decision Engine initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Decision Engine: {e}")
            return False

    async def make_decision(self, ev_results: List[EVResult],
                            regime_result=None) -> Optional[Decision]:
        if not self.is_initialized:
            return None

        try:
            if not ev_results:
                return None

            min_ev = self.settings.get("min_ev_threshold", 0.01)
            actionable_trades = [ev for ev in ev_results if ev.ev_score >= min_ev]

            if not actionable_trades:
                logger.debug(f"No actionable trades found (min EV: {min_ev})")
                return None

            best_trade = max(actionable_trades, key=lambda x: x.ev_score)

            confidence = min(0.95, 0.5 + (best_trade.ev_score * 10))
            if regime_result:
                regime_conf = regime_result.confidence if hasattr(regime_result, "confidence") else regime_result.get("confidence", 0.0)
                confidence *= (0.5 + regime_conf * 0.5)

            seq = self.clock.tick()
            decision = Decision.from_ev(
                best_trade,
                decision_id=f"dec_{seq}",
                confidence=confidence,
                reasoning=f"Selected trade with EV {best_trade.ev_score:.4f} from {len(actionable_trades)} actionable options",
            )

            logger.debug(f"Made decision: {decision.decision_id} for {decision.symbol} "
                         f"with EV {decision.ev_score:.4f}")

            return decision

        except Exception as e:
            logger.error(f"Error making decision: {e}")
            return None

    async def batch_decision(self, ev_results: List[EVResult]) -> List[Decision]:
        if not self.is_initialized:
            return []

        try:
            decisions = []
            for ev_result in ev_results:
                decision = await self.make_decision([ev_result])
                if decision:
                    decisions.append(decision)

            logger.debug(f"Made {len(decisions)} batch decisions from {len(ev_results)} EV results")
            return decisions

        except Exception as e:
            logger.error(f"Error making batch decisions: {e}")
            return []

    async def shutdown(self):
        logger.info("Shutting down Decision Engine...")
        self.is_initialized = False
        logger.info("Decision Engine shutdown complete")
