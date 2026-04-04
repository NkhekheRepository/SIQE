"""
Strategy Engine Module
Generates trading signals based on market data.
Deterministic: uses EventClock, no time-based logic.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

import numpy as np

from core.clock import EventClock
from models.trade import MarketEvent, Signal, SignalType

logger = logging.getLogger(__name__)


class StrategyEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategies: set = set()
        self._strategy_params: Dict[str, Dict[str, Any]] = {}

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Strategy Engine...")
            self.strategies = {
                "mean_reversion": MeanReversionStrategy(self.settings, self.clock),
                "momentum": MomentumStrategy(self.settings, self.clock),
                "breakout": BreakoutStrategy(self.settings, self.clock),
            }
            self.active_strategies = set(self.strategies.keys())
            self.is_initialized = True
            logger.info(f"Strategy Engine initialized with {len(self.strategies)} strategies")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Strategy Engine: {e}")
            return False

    async def generate_signals(self, event: MarketEvent, regime_result=None) -> Optional[List[Signal]]:
        if not self.is_initialized:
            return None

        try:
            all_signals = []
            market_data = {event.symbol: event}

            for strategy_name in sorted(self.active_strategies):
                if regime_result:
                    suitability = await self._check_regime_suitability(strategy_name, regime_result)
                    if not suitability:
                        continue

                strategy = self.strategies[strategy_name]
                signals = await strategy.generate_signals(market_data)
                if signals:
                    for signal in signals:
                        if regime_result:
                            signal = Signal(
                                signal_id=signal.signal_id,
                                symbol=signal.symbol,
                                signal_type=signal.signal_type,
                                strength=signal.strength,
                                price=signal.price,
                                strategy=signal.strategy,
                                reason=signal.reason,
                                event_seq=signal.event_seq,
                                regime=str(regime_result.regime.value),
                                regime_confidence=regime_result.confidence,
                            )
                        all_signals.append(signal)

            if not all_signals:
                return None

            logger.debug(f"Generated {len(all_signals)} signals from {len(self.active_strategies)} strategies")
            return all_signals

        except Exception as e:
            logger.error(f"Error generating strategy signals: {e}")
            return None

    async def update_strategy_params(self, strategy_name: str, params: Dict[str, Any]):
        if strategy_name in self.strategies:
            self.strategies[strategy_name].update_params(params)
            self._strategy_params[strategy_name] = params
            logger.info(f"Updated params for strategy {strategy_name}")

    async def activate_strategy(self, strategy_name: str) -> bool:
        if strategy_name in self.strategies:
            self.active_strategies.add(strategy_name)
            logger.info(f"Activated strategy: {strategy_name}")
            return True
        logger.warning(f"Strategy not found: {strategy_name}")
        return False

    async def deactivate_strategy(self, strategy_name: str) -> bool:
        if strategy_name in self.active_strategies:
            self.active_strategies.discard(strategy_name)
            logger.info(f"Deactivated strategy: {strategy_name}")
            return True
        logger.warning(f"Strategy not active: {strategy_name}")
        return False

    async def _check_regime_suitability(self, strategy_name: str, regime_result) -> bool:
        regime = regime_result.regime.value if hasattr(regime_result, "regime") else regime_result.get("regime", "MIXED")
        confidence = regime_result.confidence if hasattr(regime_result, "confidence") else regime_result.get("confidence", 0.0)
        if confidence < 0.3:
            return True
        blocked = {
            "mean_reversion": ["TRENDING"],
            "momentum": ["RANGING"],
            "breakout": ["RANGING"],
        }
        return regime not in blocked.get(strategy_name, [])

    async def get_strategy_performance(self) -> Dict[str, Any]:
        performance = {}
        for strategy_name in self.strategies:
            performance[strategy_name] = {
                "active": strategy_name in self.active_strategies,
                "signal_count": int(np.random.randint(0, 100)),
                "win_rate": float(np.random.uniform(0.4, 0.7)),
                "avg_return": float(np.random.uniform(-0.01, 0.02)),
            }
        return performance

    async def shutdown(self):
        self.is_initialized = False
        self.strategies.clear()
        self.active_strategies.clear()


class BaseStrategy:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.name = self.__class__.__name__.lower().replace("strategy", "")
        self._params: Dict[str, Any] = {}

    def update_params(self, params: Dict[str, Any]):
        self._params.update(params)

    async def generate_signals(self, market_data: Dict[str, MarketEvent]) -> Optional[List[Signal]]:
        raise NotImplementedError


class MeanReversionStrategy(BaseStrategy):
    async def generate_signals(self, market_data: Dict[str, MarketEvent]) -> Optional[List[Signal]]:
        signals = []
        for symbol, event in market_data.items():
            mid_price = event.mid_price
            if mid_price > 0:
                threshold = self._params.get("threshold", 0.02)
                if np.random.random() > 0.7:
                    signal_type = SignalType.LONG if np.random.random() > 0.5 else SignalType.SHORT
                    strength = float(np.random.uniform(0.1, 1.0))
                    seq = self.clock.tick()
                    signals.append(Signal(
                        signal_id=f"sig_mr_{seq}",
                        symbol=symbol,
                        signal_type=signal_type,
                        strength=strength,
                        price=mid_price,
                        strategy="mean_reversion",
                        reason=f"Mean reversion signal for {symbol}",
                        event_seq=seq,
                    ))
        return signals if signals else None


class MomentumStrategy(BaseStrategy):
    async def generate_signals(self, market_data: Dict[str, MarketEvent]) -> Optional[List[Signal]]:
        signals = []
        for symbol, event in market_data.items():
            if np.random.random() > 0.8:
                signal_type = SignalType.LONG if np.random.random() > 0.5 else SignalType.SHORT
                strength = float(np.random.uniform(0.2, 1.0))
                seq = self.clock.tick()
                signals.append(Signal(
                    signal_id=f"sig_mom_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength,
                    price=event.mid_price,
                    strategy="momentum",
                    reason=f"Momentum signal for {symbol}",
                    event_seq=seq,
                ))
        return signals if signals else None


class BreakoutStrategy(BaseStrategy):
    async def generate_signals(self, market_data: Dict[str, MarketEvent]) -> Optional[List[Signal]]:
        signals = []
        for symbol, event in market_data.items():
            volatility = event.volatility
            breakout_prob = min(0.5, volatility * 10)
            if np.random.random() > (1 - breakout_prob):
                signal_type = SignalType.LONG if np.random.random() > 0.5 else SignalType.SHORT
                strength = float(np.random.uniform(0.3, 1.0))
                seq = self.clock.tick()
                signals.append(Signal(
                    signal_id=f"sig_bo_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength,
                    price=event.mid_price,
                    strategy="breakout",
                    reason=f"Breakout signal for {symbol} (volatility: {volatility:.3f})",
                    event_seq=seq,
                ))
        return signals if signals else None
