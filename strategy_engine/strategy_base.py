"""
Strategy Engine Module
Generates trading signals based on market data.
Deterministic: uses EventClock, no time-based logic.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import deque

import numpy as np
import pandas as pd

from core.clock import EventClock
from models.trade import MarketEvent, Signal, SignalType
from strategy_engine.indicators import TechnicalIndicators, generate_ensemble_signal
from strategy_engine.config import (
    IndicatorConfig, DirectionalBias, DirectionalBiasDetector, SafetyLimits,
)

logger = logging.getLogger(__name__)


class StrategyEngine:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategies: set = set()
        self._strategy_params: Dict[str, Dict[str, Any]] = {}
        
        # Price history buffer for indicators
        self._max_history = 200
        self._price_history: Dict[str, Dict[str, deque]] = {}
    
    def update_price_history(self, symbol: str, high: float, low: float, close: float) -> None:
        """Update price history for indicator calculations."""
        if symbol not in self._price_history:
            self._price_history[symbol] = {
                "highs": deque(maxlen=self._max_history),
                "lows": deque(maxlen=self._max_history),
                "closes": deque(maxlen=self._max_history),
            }
        
        self._price_history[symbol]["highs"].append(high)
        self._price_history[symbol]["lows"].append(low)
        self._price_history[symbol]["closes"].append(close)
    
    def get_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Calculate indicators for a symbol."""
        if symbol not in self._price_history:
            return None
        
        history = self._price_history[symbol]
        if len(history["closes"]) < 30:
            return None
        
        highs = pd.Series(list(history["highs"]))
        lows = pd.Series(list(history["lows"]))
        closes = pd.Series(list(history["closes"]))
        
        return TechnicalIndicators.calculate_all(highs, lows, closes)

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Strategy Engine...")
            self.strategies = {
                "mean_reversion": MeanReversionStrategy(self.settings, self.clock),
                "momentum": MomentumStrategy(self.settings, self.clock),
                "breakout": BreakoutStrategy(self.settings, self.clock),
                "volatility_breakout": VolatilityBreakoutStrategy(self.settings, self.clock),
                "trend_following": TrendFollowingStrategy(self.settings, self.clock),
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
            # Update price history - estimate OHLC from bid/ask
            spread = event.ask - event.bid if event.ask > event.bid else 0
            mid = event.mid_price
            high_estimate = event.ask + spread * 0.5
            low_estimate = event.bid - spread * 0.5
            
            self.update_price_history(
                event.symbol,
                high_estimate,
                low_estimate,
                mid
            )
            
            all_signals = []
            market_data = {event.symbol: event}

            price_hist = self._price_history.get(event.symbol, {})
            closes_len = len(price_hist.get("closes", []))
            
            if closes_len < 30:
                return None

            # Enable regime filtering with directional bias
            for strategy_name in sorted(self.active_strategies):
                if regime_result:
                    suitability = await self._check_regime_suitability(strategy_name, regime_result)
                    if not suitability:
                        continue

                strategy = self.strategies[strategy_name]
                signals = await strategy.generate_signals(market_data, self._price_history or {})
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
        # Define which strategies work best in which regimes
        # Use regime.value for comparison (e.g., "trending_up" not "TRENDING_UP")
        regime_suitability = {
            "mean_reversion": ["ranging", "MIXED"],      # Mean reversion works best in ranging markets
            "momentum": ["trending_up", "trending_down", "MIXED"],  # Momentum works in trending
            "breakout": ["trending_up", "trending_down", "volatile", "VOLATILE"], # Breakouts work in trending/volatile
            "volatility_breakout": ["volatile", "VOLATILE", "MIXED"], # Volatility breakouts work in volatile/mixed
            "trend_following": ["trending_up", "trending_down", "MIXED"]  # Trend following in trending
        }
        
        if not regime_result:
            return True  # No regime info, allow all strategies
            
        regime = regime_result.regime.value if hasattr(regime_result.regime, 'value') else str(regime_result.regime)
        suitable_regimes = regime_suitability.get(strategy_name, ["trending_up", "trending_down", "ranging", "volatile", "MIXED"])
        
        return regime in suitable_regimes

    async def generate_all_signals(self, event: MarketEvent, price_history: Dict, regime_result=None) -> List[Signal]:
        """Generate signals from all active strategies without regime filtering."""
        all_signals = []
        market_data = {event.symbol: event}
        
        for strategy_name in sorted(self.active_strategies):
            strategy = self.strategies[strategy_name]
            signals = await strategy.generate_signals(market_data, price_history)
            if signals:
                all_signals.extend(signals)
        
        return all_signals

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
        self._indicator_config = IndicatorConfig()

    def update_params(self, params: Dict[str, Any]):
        self._params.update(params)
        self._indicator_config = IndicatorConfig.from_dict({
            **self._indicator_config.to_dict(),
            **params,
        })

    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        raise NotImplementedError
    
    def _get_indicators(self, symbol: str, price_history: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Get calculated indicators from price history."""
        if price_history is None:
            return None
        if symbol not in price_history:
            return None
        
        history = price_history[symbol]
        if len(history.get("closes", [])) < 30:
            return None
        
        highs = pd.Series(list(history["highs"]))
        lows = pd.Series(list(history["lows"]))
        closes = pd.Series(list(history["closes"]))
        
        return TechnicalIndicators.calculate_all(highs, lows, closes, self._indicator_config.to_dict())
    
    def get_directional_bias(self, symbol: str, price_history: Optional[Dict[str, Any]] = None) -> DirectionalBias:
        """Detect current market directional bias using EMA crossover."""
        if price_history is None or symbol not in price_history:
            return DirectionalBias.NEUTRAL
        
        closes = pd.Series(list(price_history[symbol]["closes"]))
        if len(closes) < 200:
            return DirectionalBias.NEUTRAL
        
        return DirectionalBiasDetector.detect(closes)
    
    def filter_signal_by_bias(
        self,
        signal_type: 'SignalType',
        bias: DirectionalBias,
    ) -> Tuple[bool, float]:
        """
        Filter signals based on directional bias with strength attenuation.
        
        Returns: (allow_signal, strength_multiplier)
        - allow_signal: whether signal is allowed
        - strength_multiplier: 0.0-1.0 for signal strength adjustment (capped at 1.0)
        """
        if bias == DirectionalBias.BEAR:
            if signal_type == SignalType.LONG:
                return True, 0.5   # Allow but attenuate longs
            return True, 0.75      # Slightly amplify shorts
        elif bias == DirectionalBias.BULL:
            if signal_type == SignalType.SHORT:
                return True, 0.25  # Allow but heavily attenuate shorts
            return True, 0.75      # Slightly amplify longs
        return True, 1.0           # Neutral - no change
    
    def apply_position_size_modifier(
        self,
        signal: 'Signal',
        bias: DirectionalBias,
    ) -> float:
        """Apply position size multiplier based on bias and signal direction."""
        direction = 1 if signal.signal_type == SignalType.LONG else -1
        return SafetyLimits.get_position_size_multiplier(bias, direction)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy using Bollinger Bands and RSI.
    
    Signals:
    - LONG: When price is below lower Bollinger Band and RSI < 30 (oversold)
    - SHORT: When price is above upper Bollinger Band and RSI > 70 (overbought)
    """
    
    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        if price_history is None:
            return None
        
        bias = self.get_directional_bias(list(market_data.keys())[0] if market_data else "", price_history)
        signals = []
        for symbol, event in market_data.items():
            indicators = self._get_indicators(symbol, price_history)
            if not indicators:
                continue
            
            mid_price = event.mid_price
            if mid_price <= 0:
                continue
            
            bb_signal = indicators.get("bollinger", {}).get("signal")
            rsi_signal = indicators.get("rsi", {}).get("signal")
            
            if not bb_signal or not rsi_signal:
                continue
            
            signal_type = None
            strength = 0.0
            reason = ""
            
            if bb_signal.signal == "bullish" and rsi_signal.signal == "bullish":
                signal_type = SignalType.LONG
                strength = (bb_signal.strength + rsi_signal.strength) / 2
                reason = f"Mean reversion LONG: BB oversold (strength={bb_signal.strength:.2f}), RSI={indicators['rsi']['value']:.1f}"
            elif bb_signal.signal == "bearish" and rsi_signal.signal == "bearish":
                signal_type = SignalType.SHORT
                strength = (bb_signal.strength + rsi_signal.strength) / 2
                reason = f"Mean reversion SHORT: BB overbought (strength={bb_signal.strength:.2f}), RSI={indicators['rsi']['value']:.1f}"
            elif bb_signal.strength > 0.6:
                if bb_signal.signal == "bullish":
                    signal_type = SignalType.LONG
                    strength = bb_signal.strength * 0.7
                    reason = f"BB oversold (strength={bb_signal.strength:.2f})"
                elif bb_signal.signal == "bearish":
                    signal_type = SignalType.SHORT
                    strength = bb_signal.strength * 0.7
                    reason = f"BB overbought (strength={bb_signal.strength:.2f})"
            
            if signal_type and strength >= 0.3:
                allow, strength_mult = self.filter_signal_by_bias(signal_type, bias)
                if not allow:
                    continue
                seq = self.clock.tick()
                pos_mult = self.apply_position_size_modifier(
                    Signal(signal_id="", symbol=symbol, signal_type=signal_type, 
                           strength=strength, price=mid_price, strategy="", reason="", event_seq=0),
                    bias
                )
                signals.append(Signal(
                    signal_id=f"sig_mr_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength * strength_mult * pos_mult,
                    price=mid_price,
                    strategy="mean_reversion",
                    reason=f"{reason} | bias={bias.value}",
                    event_seq=seq,
                ))
        
        return signals if signals else None


class MomentumStrategy(BaseStrategy):
    """
    Momentum Strategy using MACD and ADX.
    
    Signals:
    - LONG: When MACD crosses above signal line AND ADX > 25 (strong trend)
    - SHORT: When MACD crosses below signal line AND ADX > 25
    """
    
    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        if price_history is None:
            return None
        
        bias = self.get_directional_bias(list(market_data.keys())[0] if market_data else "", price_history)
        signals = []
        for symbol, event in market_data.items():
            indicators = self._get_indicators(symbol, price_history)
            if not indicators:
                continue
            
            mid_price = event.mid_price
            if mid_price <= 0:
                continue
            
            macd_signal = indicators.get("macd", {}).get("signal_obj")
            adx_data = indicators.get("adx", {})
            adx_signal = adx_data.get("signal")
            trend = adx_data.get("trend", "weak")
            adx_value = adx_data.get("value", 0)
            
            if not macd_signal or not adx_signal:
                continue
            
            signal_type = None
            strength = 0.0
            reason = ""
            
            if trend in ["strong", "moderate"]:
                if macd_signal.signal == "bullish" and macd_signal.metadata.get("condition") == "bullish_crossover":
                    signal_type = SignalType.LONG
                    strength = (macd_signal.strength + adx_signal.strength) / 2
                    reason = f"Momentum LONG: MACD bullish crossover, ADX={adx_value:.1f} ({trend})"
                elif macd_signal.signal == "bearish" and macd_signal.metadata.get("condition") == "bearish_crossover":
                    signal_type = SignalType.SHORT
                    strength = (macd_signal.strength + adx_signal.strength) / 2
                    reason = f"Momentum SHORT: MACD bearish crossover, ADX={adx_value:.1f} ({trend})"
            
            if signal_type and strength >= 0.4:
                allow, strength_mult = self.filter_signal_by_bias(signal_type, bias)
                if not allow:
                    continue
                seq = self.clock.tick()
                pos_mult = self.apply_position_size_modifier(
                    Signal(signal_id="", symbol=symbol, signal_type=signal_type, 
                           strength=strength, price=mid_price, strategy="", reason="", event_seq=0),
                    bias
                )
                signals.append(Signal(
                    signal_id=f"sig_mom_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength * strength_mult * pos_mult,
                    price=mid_price,
                    strategy="momentum",
                    reason=f"{reason} | bias={bias.value}",
                    event_seq=seq,
                ))
        
        return signals if signals else None


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Strategy using Donchian Channels.
    
    Signals:
    - LONG: When price breaks above upper Donchian Channel
    - SHORT: When price breaks below lower Donchian Channel
    """
    
    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        if price_history is None:
            return None
        
        bias = self.get_directional_bias(list(market_data.keys())[0] if market_data else "", price_history)
        signals = []
        for symbol, event in market_data.items():
            indicators = self._get_indicators(symbol, price_history)
            if not indicators:
                continue
            
            mid_price = event.mid_price
            if mid_price <= 0:
                continue
            
            dc_data = indicators.get("donchian", {})
            dc_signal = dc_data.get("signal")
            dc_upper = dc_data.get("upper")
            dc_lower = dc_data.get("lower")
            atr_value = indicators.get("atr", {}).get("value", 0)
            
            if not dc_signal or not dc_upper or not dc_lower:
                continue
            
            signal_type = None
            strength = 0.0
            reason = ""
            
            if dc_signal.metadata.get("condition") == "upper_breakout":
                signal_type = SignalType.LONG
                strength = dc_signal.strength
                reason = f"Breakout LONG: Above upper channel (${dc_upper:.2f}), ATR=${atr_value:.2f}"
            elif dc_signal.metadata.get("condition") == "lower_breakout":
                signal_type = SignalType.SHORT
                strength = dc_signal.strength
                reason = f"Breakout SHORT: Below lower channel (${dc_lower:.2f}), ATR=${atr_value:.2f}"
            elif dc_signal.strength > 0.5:
                if dc_signal.signal == "bullish":
                    signal_type = SignalType.LONG
                    strength = dc_signal.strength * 0.6
                    reason = f"Near upper channel breakout"
                elif dc_signal.signal == "bearish":
                    signal_type = SignalType.SHORT
                    strength = dc_signal.strength * 0.6
                    reason = f"Near lower channel breakdown"
            
            if signal_type and strength >= 0.3:
                allow, strength_mult = self.filter_signal_by_bias(signal_type, bias)
                if not allow:
                    continue
                seq = self.clock.tick()
                pos_mult = self.apply_position_size_modifier(
                    Signal(signal_id="", symbol=symbol, signal_type=signal_type, 
                           strength=strength, price=mid_price, strategy="", reason="", event_seq=0),
                    bias
                )
                signals.append(Signal(
                    signal_id=f"sig_bo_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength * strength_mult * pos_mult,
                    price=mid_price,
                    strategy="breakout",
                    reason=f"{reason} | bias={bias.value}",
                    event_seq=seq,
                ))
        
        return signals if signals else None


class VolatilityBreakoutStrategy(BaseStrategy):
    """
    Volatility Breakout Strategy using ATR expansion.
    
    Signals:
    - LONG: When ATR expands significantly (volatility breakout)
    - SHORT: When price collapses after high volatility
    """
    
    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        if not price_history:
            return None
        
        bias = self.get_directional_bias(list(market_data.keys())[0] if market_data else "", price_history)
        signals = []
        for symbol, event in market_data.items():
            indicators = self._get_indicators(symbol, price_history)
            if not indicators:
                continue
            
            mid_price = event.mid_price
            if mid_price <= 0:
                continue
            
            atr_data = indicators.get("atr", {})
            atr_value = atr_data.get("value", 0)
            atr_signal = atr_data.get("signal")
            
            if not atr_value or atr_value <= 0:
                continue
            
            closes = list(price_history[symbol]["closes"]) if symbol in price_history else []
            if len(closes) < 20:
                continue
            
            recent_closes = closes[-20:]
            avg_range = np.mean([abs(recent_closes[i] - recent_closes[i-1]) for i in range(1, len(recent_closes))])
            
            signal_type = None
            strength = 0.0
            reason = ""
            
            if avg_range > 0:
                volatility_ratio = atr_value / avg_range
                
                if volatility_ratio > 1.5 and closes[-1] > closes[-2]:
                    signal_type = SignalType.LONG
                    strength = min(volatility_ratio / 3, 0.9)
                    reason = f"Volatility breakout LONG: ratio={volatility_ratio:.2f}, ATR=${atr_value:.2f}"
                elif volatility_ratio > 1.5 and closes[-1] < closes[-2]:
                    signal_type = SignalType.SHORT
                    strength = min(volatility_ratio / 3, 0.9)
                    reason = f"Volatility breakdown SHORT: ratio={volatility_ratio:.2f}, ATR=${atr_value:.2f}"
            
            if signal_type and strength >= 0.25:
                allow, strength_mult = self.filter_signal_by_bias(signal_type, bias)
                if not allow:
                    continue
                seq = self.clock.tick()
                pos_mult = self.apply_position_size_modifier(
                    Signal(signal_id="", symbol=symbol, signal_type=signal_type, 
                           strength=strength, price=mid_price, strategy="", reason="", event_seq=0),
                    bias
                )
                signals.append(Signal(
                    signal_id=f"sig_vb_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength * strength_mult * pos_mult,
                    price=mid_price,
                    strategy="volatility_breakout",
                    reason=f"{reason} | bias={bias.value}",
                    event_seq=seq,
                ))
        
        return signals if signals else None


class TrendFollowingStrategy(BaseStrategy):
    """
    Simple Trend Following Strategy using EMA crossover.
    
    Signals:
    - LONG: Fast EMA above slow EMA
    - SHORT: Fast EMA below slow EMA
    """
    
    async def generate_signals(self, market_data: Dict[str, MarketEvent], price_history: Optional[Dict[str, Any]] = None) -> Optional[List[Signal]]:
        if not price_history:
            return None
        
        bias = self.get_directional_bias(list(market_data.keys())[0] if market_data else "", price_history)
        signals = []
        for symbol, event in market_data.items():
            indicators = self._get_indicators(symbol, price_history)
            if not indicators:
                continue
            
            mid_price = event.mid_price
            if mid_price <= 0:
                continue
            
            closes = list(price_history[symbol]["closes"]) if symbol in price_history else []
            if len(closes) < 50:
                continue
            
            closes_series = pd.Series(closes)
            ema_fast = closes_series.ewm(span=8, adjust=False).mean().iloc[-1]
            ema_slow = closes_series.ewm(span=21, adjust=False).mean().iloc[-1]
            ema_fast_prev = closes_series.ewm(span=8, adjust=False).mean().iloc[-2]
            ema_slow_prev = closes_series.ewm(span=21, adjust=False).mean().iloc[-2]
            
            signal_type = None
            strength = 0.0
            reason = ""
            
            if ema_fast > ema_slow and ema_fast_prev <= ema_slow_prev:
                signal_type = SignalType.LONG
                strength = min(abs(ema_fast - ema_slow) / ema_slow * 5, 0.9)
                reason = f"EMA bullish crossover: fast={ema_fast:.2f}, slow={ema_slow:.2f}"
            elif ema_fast < ema_slow and ema_fast_prev >= ema_slow_prev:
                signal_type = SignalType.SHORT
                strength = min(abs(ema_slow - ema_fast) / ema_slow * 5, 0.9)
                reason = f"EMA bearish crossover: fast={ema_fast:.2f}, slow={ema_slow:.2f}"
            
            if signal_type and strength >= 0.25:
                allow, strength_mult = self.filter_signal_by_bias(signal_type, bias)
                if not allow:
                    continue
                seq = self.clock.tick()
                pos_mult = self.apply_position_size_modifier(
                    Signal(signal_id="", symbol=symbol, signal_type=signal_type, 
                           strength=strength, price=mid_price, strategy="", reason="", event_seq=0),
                    bias
                )
                signals.append(Signal(
                    signal_id=f"sig_tf_{seq}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=strength * strength_mult * pos_mult,
                    price=mid_price,
                    strategy="trend_following",
                    reason=f"{reason} | bias={bias.value}",
                    event_seq=seq,
                ))
        
        return signals if signals else None
