"""
SIQE V3 - Technical Indicators

Provides real technical indicators for signal generation instead of mock/random signals.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class IndicatorResult:
    """Result from indicator calculation."""
    value: float
    signal: str  # "bullish", "bearish", "neutral"
    strength: float  # 0.0 - 1.0
    metadata: Dict[str, Any] = None


class TechnicalIndicators:
    """Collection of technical indicators for trading signals."""
    
    @staticmethod
    def bollinger_bands(
        closes: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands.
        
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        middle = closes.rolling(period).mean()
        std = closes.rolling(period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    @staticmethod
    def bollinger_signal(
        close: float,
        upper: float,
        middle: float,
        lower: float
    ) -> IndicatorResult:
        """
        Generate signal from Bollinger Bands.
        
        Returns:
            IndicatorResult with signal and strength
        """
        bandwidth = (upper - lower) / middle if middle > 0 else 0
        position = (close - lower) / (upper - lower) if upper != lower else 0.5
        
        if close < lower:
            # Oversold - potential buy
            distance = (lower - close) / lower if lower > 0 else 0
            return IndicatorResult(
                value=position,
                signal="bullish",
                strength=min(1.0, 0.5 + distance * 5),
                metadata={"reason": "oversold", "bandwidth": bandwidth}
            )
        elif close > upper:
            # Overbought - potential sell
            distance = (close - upper) / upper if upper > 0 else 0
            return IndicatorResult(
                value=position,
                signal="bearish",
                strength=min(1.0, 0.5 + distance * 5),
                metadata={"reason": "overbought", "bandwidth": bandwidth}
            )
        elif position < 0.3:
            # Near lower band
            return IndicatorResult(
                value=position,
                signal="bullish",
                strength=0.4,
                metadata={"reason": "near_lower_band"}
            )
        elif position > 0.7:
            # Near upper band
            return IndicatorResult(
                value=position,
                signal="bearish",
                strength=0.4,
                metadata={"reason": "near_upper_band"}
            )
        else:
            return IndicatorResult(
                value=position,
                signal="neutral",
                strength=0.1,
                metadata={"reason": "middle_range"}
            )
    
    @staticmethod
    def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index.
        
        Returns:
            Series of RSI values (0-100)
        """
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def rsi_signal(rsi_value: float) -> IndicatorResult:
        """
        Generate signal from RSI value.
        
        Args:
            rsi_value: RSI value (0-100)
        """
        if rsi_value < 30:
            # Oversold
            strength = (30 - rsi_value) / 30
            return IndicatorResult(
                value=rsi_value,
                signal="bullish",
                strength=strength,
                metadata={"condition": "oversold"}
            )
        elif rsi_value > 70:
            # Overbought
            strength = (rsi_value - 70) / 30
            return IndicatorResult(
                value=rsi_value,
                signal="bearish",
                strength=strength,
                metadata={"condition": "overbought"}
            )
        elif rsi_value < 40:
            return IndicatorResult(
                value=rsi_value,
                signal="bullish",
                strength=0.2,
                metadata={"condition": "bearish_territory"}
            )
        elif rsi_value > 60:
            return IndicatorResult(
                value=rsi_value,
                signal="bearish",
                strength=0.2,
                metadata={"condition": "bullish_territory"}
            )
        else:
            return IndicatorResult(
                value=rsi_value,
                signal="neutral",
                strength=0.1,
                metadata={"condition": "neutral"}
            )
    
    @staticmethod
    def macd(
        closes: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        ema_fast = closes.ewm(span=fast_period).mean()
        ema_slow = closes.ewm(span=slow_period).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def macd_signal(
        macd_line: float,
        signal_line: float,
        histogram: float
    ) -> IndicatorResult:
        """
        Generate signal from MACD values.
        """
        if histogram > 0 and macd_line > signal_line:
            # Bullish crossover
            strength = min(1.0, abs(histogram) / abs(macd_line) if macd_line != 0 else 0)
            return IndicatorResult(
                value=histogram,
                signal="bullish",
                strength=max(0.5, strength),
                metadata={"condition": "bullish_crossover"}
            )
        elif histogram < 0 and macd_line < signal_line:
            # Bearish crossover
            strength = min(1.0, abs(histogram) / abs(macd_line) if macd_line != 0 else 0)
            return IndicatorResult(
                value=histogram,
                signal="bearish",
                strength=max(0.5, strength),
                metadata={"condition": "bearish_crossover"}
            )
        elif histogram > 0:
            return IndicatorResult(
                value=histogram,
                signal="bullish",
                strength=0.3,
                metadata={"condition": "above_signal"}
            )
        else:
            return IndicatorResult(
                value=histogram,
                signal="bearish",
                strength=0.3,
                metadata={"condition": "below_signal"}
            )
    
    @staticmethod
    def atr(
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        Calculate Average True Range.
        
        Returns:
            Series of ATR values
        """
        high_low = highs - lows
        high_close = abs(highs - closes.shift())
        low_close = abs(lows - closes.shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean()
        return atr
    
    @staticmethod
    def donchian_channels(
        highs: pd.Series,
        lows: pd.Series,
        period: int = 20
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Donchian Channels.
        
        Returns:
            Tuple of (upper, middle, lower)
        """
        upper = highs.rolling(period).max()
        lower = lows.rolling(period).min()
        middle = (upper + lower) / 2
        return upper, middle, lower
    
    @staticmethod
    def donchian_signal(
        close: float,
        upper: float,
        lower: float
    ) -> IndicatorResult:
        """
        Generate signal from Donchian Channels.
        """
        range_size = upper - lower
        position = (close - lower) / range_size if range_size > 0 else 0.5
        
        if close >= upper:
            # Breakout above
            return IndicatorResult(
                value=position,
                signal="bullish",
                strength=0.8,
                metadata={"condition": "upper_breakout"}
            )
        elif close <= lower:
            # Breakdown below
            return IndicatorResult(
                value=position,
                signal="bearish",
                strength=0.8,
                metadata={"condition": "lower_breakout"}
            )
        elif position > 0.8:
            return IndicatorResult(
                value=position,
                signal="bullish",
                strength=0.4,
                metadata={"condition": "near_upper"}
            )
        elif position < 0.2:
            return IndicatorResult(
                value=position,
                signal="bearish",
                strength=0.4,
                metadata={"condition": "near_lower"}
            )
        else:
            return IndicatorResult(
                value=position,
                signal="neutral",
                strength=0.1,
                metadata={"condition": "middle"}
            )
    
    @staticmethod
    def adx(
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        period: int = 14
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """
        Calculate Average Directional Index (ADX).
        
        Returns:
            Tuple of (adx, plus_di, minus_di, trend_strength)
        """
        high_diff = highs.diff()
        low_diff = -lows.diff()
        
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        
        atr = TechnicalIndicators.atr(highs, lows, closes, period)
        
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx, plus_di, minus_di, adx
    
    @staticmethod
    def adx_signal(adx: float, plus_di: float, minus_di: float) -> Tuple[IndicatorResult, str]:
        """
        Generate signal from ADX values.
        
        Returns:
            Tuple of (signal, trend_strength)
        """
        # Trend strength
        if adx > 25:
            trend = "strong"
        elif adx > 20:
            trend = "moderate"
        else:
            trend = "weak"
        
        # Direction
        if plus_di > minus_di:
            direction = "bullish"
            strength = min(1.0, (plus_di - minus_di) / 25)
        elif minus_di > plus_di:
            direction = "bearish"
            strength = min(1.0, (minus_di - plus_di) / 25)
        else:
            direction = "neutral"
            strength = 0.1
        
        if trend == "weak":
            strength *= 0.5
        
        return IndicatorResult(
            value=adx,
            signal=direction,
            strength=strength,
            metadata={"trend": trend, "plus_di": plus_di, "minus_di": minus_di}
        ), trend
    
    @staticmethod
    def calculate_all(
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        indicators_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculate all indicators at once.
        
        Args:
            highs: High prices
            lows: Low prices
            closes: Close prices
            indicators_config: Configuration for indicator periods
            
        Returns:
            Dictionary with all indicator values and signals
        """
        if indicators_config is None:
            indicators_config = {}
        
        result = {}
        
        # Bollinger Bands
        bb_period = indicators_config.get("bollinger_period", 20)
        bb_std = indicators_config.get("bollinger_std", 2.0)
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(closes, bb_period, bb_std)
        result["bollinger"] = {
            "upper": bb_upper.iloc[-1] if len(bb_upper) > 0 else None,
            "middle": bb_middle.iloc[-1] if len(bb_middle) > 0 else None,
            "lower": bb_lower.iloc[-1] if len(bb_lower) > 0 else None,
            "signal": TechnicalIndicators.bollinger_signal(
                closes.iloc[-1], bb_upper.iloc[-1], bb_middle.iloc[-1], bb_lower.iloc[-1]
            ) if len(closes) > 0 else None
        }
        
        # RSI
        rsi_period = indicators_config.get("rsi_period", 14)
        rsi_values = TechnicalIndicators.rsi(closes, rsi_period)
        result["rsi"] = {
            "value": rsi_values.iloc[-1] if len(rsi_values) > 0 else None,
            "signal": TechnicalIndicators.rsi_signal(rsi_values.iloc[-1]) if len(rsi_values) > 0 else None
        }
        
        # MACD
        macd_fast = indicators_config.get("macd_fast", 12)
        macd_slow = indicators_config.get("macd_slow", 26)
        macd_signal = indicators_config.get("macd_signal", 9)
        macd_line, signal_line, histogram = TechnicalIndicators.macd(closes, macd_fast, macd_slow, macd_signal)
        result["macd"] = {
            "macd": macd_line.iloc[-1] if len(macd_line) > 0 else None,
            "signal": signal_line.iloc[-1] if len(signal_line) > 0 else None,
            "histogram": histogram.iloc[-1] if len(histogram) > 0 else None,
            "signal_obj": TechnicalIndicators.macd_signal(
                macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
            ) if len(macd_line) > 0 else None
        }
        
        # ATR
        atr_period = indicators_config.get("atr_period", 14)
        atr_values = TechnicalIndicators.atr(highs, lows, closes, atr_period)
        result["atr"] = {
            "value": atr_values.iloc[-1] if len(atr_values) > 0 else None
        }
        
        # Donchian
        donchian_period = indicators_config.get("donchian_period", 20)
        dc_upper, dc_middle, dc_lower = TechnicalIndicators.donchian_channels(highs, lows, donchian_period)
        result["donchian"] = {
            "upper": dc_upper.iloc[-1] if len(dc_upper) > 0 else None,
            "middle": dc_middle.iloc[-1] if len(dc_middle) > 0 else None,
            "lower": dc_lower.iloc[-1] if len(dc_lower) > 0 else None,
            "signal": TechnicalIndicators.donchian_signal(
                closes.iloc[-1], dc_upper.iloc[-1], dc_lower.iloc[-1]
            ) if len(closes) > 0 else None
        }
        
        # ADX
        adx_period = indicators_config.get("adx_period", 14)
        adx, plus_di, minus_di, _ = TechnicalIndicators.adx(highs, lows, closes, adx_period)
        adx_signal, trend = TechnicalIndicators.adx_signal(
            adx.iloc[-1] if len(adx) > 0 else 0,
            plus_di.iloc[-1] if len(plus_di) > 0 else 0,
            minus_di.iloc[-1] if len(minus_di) > 0 else 0
        )
        result["adx"] = {
            "value": adx.iloc[-1] if len(adx) > 0 else None,
            "plus_di": plus_di.iloc[-1] if len(plus_di) > 0 else None,
            "minus_di": minus_di.iloc[-1] if len(minus_di) > 0 else None,
            "trend": trend,
            "signal": adx_signal
        }
        
        return result


def generate_ensemble_signal(indicators: Dict[str, Any]) -> Tuple[str, float]:
    """
    Generate ensemble signal from multiple indicators.
    
    Args:
        indicators: Dictionary of indicator results from calculate_all()
        
    Returns:
        Tuple of (direction, confidence)
    """
    votes = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    total_weight = 0.0
    
    weights = {
        "bollinger": 1.0,
        "rsi": 1.2,
        "macd": 1.5,
        "donchian": 1.3,
        "adx": 1.0,
    }
    
    for name, weight in weights.items():
        if name in indicators and indicators[name].get("signal"):
            signal_obj = indicators[name]["signal"]
            if isinstance(signal_obj, IndicatorResult):
                signal = signal_obj.signal
                strength = signal_obj.strength
            else:
                continue
            
            votes[signal] += strength * weight
            total_weight += weight
    
    if total_weight == 0:
        return "neutral", 0.0
    
    # Normalize
    for key in votes:
        votes[key] /= total_weight
    
    # Determine direction
    max_vote = max(votes.values())
    if max_vote < 0.35:
        return "neutral", max_vote
    
    if votes["bullish"] == max_vote:
        return "bullish", votes["bullish"]
    elif votes["bearish"] == max_vote:
        return "bearish", votes["bearish"]
    else:
        return "neutral", votes["neutral"]
