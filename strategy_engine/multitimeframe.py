"""
SIQE V3 - Multi-Timeframe Signal Confirmation

Implements multi-timeframe confirmation to reduce false signals:
- 15m entry signal must be validated by 4h trend direction
- 1h momentum confirmation for additional filtering
- Signal strength boosted when all timeframes agree
- Signal rejected when higher timeframes contradict
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

from strategy_engine.config import MarketRegime, RegimeDetector, RegimeResult

logger = logging.getLogger(__name__)


class MTFSignal(Enum):
    """Multi-timeframe signal outcome."""
    CONFIRMED_LONG = "confirmed_long"
    CONFIRMED_SHORT = "confirmed_short"
    REJECTED = "rejected"
    WEAKENED_LONG = "weakened_long"
    WEAKENED_SHORT = "weakened_short"
    NEUTRAL = "neutral"


@dataclass
class MTFConfirmationResult:
    """Result from multi-timeframe confirmation."""
    signal: MTFSignal
    original_signal: int
    strength: float
    trend_aligned: bool
    momentum_aligned: bool
    higher_tf_regime: MarketRegime
    details: Dict[str, Any]


class MultiTimeframeConfirmator:
    """
    Validates trading signals across multiple timeframes.

    Rules:
    - 15m LONG signal requires 4h trend UP or neutral (not strongly DOWN)
    - 15m SHORT signal requires 4h trend DOWN or neutral (not strongly UP)
    - 1h momentum must not contradict the signal direction
    - Signal strength is boosted when all timeframes align
    - Signal is rejected when higher timeframes strongly contradict
    """

    def __init__(
        self,
        ema_period_higher: int = 50,
        ema_period_mid: int = 34,
        momentum_lookback: int = 20,
        min_trend_alignment_pct: float = 0.01,
    ):
        self.ema_period_higher = ema_period_higher
        self.ema_period_mid = ema_period_mid
        self.momentum_lookback = momentum_lookback
        self.min_trend_alignment_pct = min_trend_alignment_pct

    def confirm_signal(
        self,
        signal_tf_data: pd.DataFrame,
        higher_tf_data: pd.DataFrame,
        mid_tf_data: Optional[pd.DataFrame] = None,
        original_signal: int = 0,
    ) -> MTFConfirmationResult:
        """
        Confirm a signal using higher timeframe data.

        Args:
            signal_tf_data: DataFrame with high/low/close for signal timeframe (e.g. 15m)
            higher_tf_data: DataFrame with high/low/close for higher timeframe (e.g. 4h)
            mid_tf_data: Optional mid timeframe (e.g. 1h)
            original_signal: +1 for LONG, -1 for SHORT, 0 for neutral

        Returns:
            MTFConfirmationResult with confirmed/rejected signal
        """
        if original_signal == 0:
            return MTFConfirmationResult(
                signal=MTFSignal.NEUTRAL,
                original_signal=0,
                strength=0.0,
                trend_aligned=False,
                momentum_aligned=False,
                higher_tf_regime=MarketRegime.QUIET,
                details={"reason": "no_signal"},
            )

        closes_higher = higher_tf_data["close"]
        closes_signal = signal_tf_data["close"]

        ema_higher = closes_higher.ewm(span=self.ema_period_higher, adjust=False).mean()
        trend_direction = self._get_trend_direction(closes_higher, ema_higher)

        trend_aligned = self._check_trend_alignment(original_signal, trend_direction)

        momentum_aligned = True
        if mid_tf_data is not None and len(mid_tf_data) > self.momentum_lookback:
            momentum_aligned = self._check_momentum_alignment(
                original_signal, mid_tf_data
            )

        if trend_aligned and momentum_aligned:
            confirmed_signal = (
                MTFSignal.CONFIRMED_LONG if original_signal == 1
                else MTFSignal.CONFIRMED_SHORT
            )
            strength = min(1.0, 0.7 + 0.15 + 0.15)
        elif trend_aligned and not momentum_aligned:
            confirmed_signal = (
                MTFSignal.WEAKENED_LONG if original_signal == 1
                else MTFSignal.WEAKENED_SHORT
            )
            strength = 0.5
        elif not trend_aligned and momentum_aligned:
            confirmed_signal = (
                MTFSignal.WEAKENED_LONG if original_signal == 1
                else MTFSignal.WEAKENED_SHORT
            )
            strength = 0.4
        else:
            confirmed_signal = MTFSignal.REJECTED
            strength = 0.0

        higher_regime_result = RegimeDetector.detect(
            higher_tf_data["high"],
            higher_tf_data["low"],
            closes_higher,
        )

        return MTFConfirmationResult(
            signal=confirmed_signal,
            original_signal=original_signal,
            strength=strength,
            trend_aligned=trend_aligned,
            momentum_aligned=momentum_aligned,
            higher_tf_regime=higher_regime_result.regime,
            details={
                "trend_direction": trend_direction,
                "higher_tf_adx": higher_regime_result.adx,
                "higher_tf_volatility": higher_regime_result.volatility,
            },
        )

    def _get_trend_direction(
        self, closes: pd.Series, ema: pd.Series
    ) -> int:
        """
        Determine trend direction from higher timeframe.

        Returns:
            +1 for uptrend, -1 for downtrend, 0 for neutral
        """
        if len(closes) < 2 or len(ema) < 2:
            return 0

        current_price = closes.iloc[-1]
        current_ema = ema.iloc[-1]

        if np.isnan(current_price) or np.isnan(current_ema):
            return 0

        diff_pct = (current_price - current_ema) / current_ema

        if diff_pct > self.min_trend_alignment_pct:
            return 1
        elif diff_pct < -self.min_trend_alignment_pct:
            return -1
        return 0

    def _check_trend_alignment(self, signal: int, trend_direction: int) -> bool:
        """Check if signal direction aligns with higher timeframe trend."""
        if trend_direction == 0:
            return True
        return signal == trend_direction

    def _check_momentum_alignment(
        self, signal: int, mid_tf_data: pd.DataFrame
    ) -> bool:
        """Check if mid-timeframe momentum supports the signal."""
        closes = mid_tf_data["close"]
        if len(closes) < self.momentum_lookback + 1:
            return True

        momentum = closes.pct_change(self.momentum_lookback).iloc[-1]

        if np.isnan(momentum):
            return True

        if signal == 1:
            return momentum >= -0.01
        elif signal == -1:
            return momentum <= 0.01
        return True

    def batch_confirm(
        self,
        signal_tf_data: pd.DataFrame,
        higher_tf_data: pd.DataFrame,
        mid_tf_data: Optional[pd.DataFrame] = None,
        signals: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Confirm a series of signals across the full dataset.

        Returns a filtered signal series where rejected signals are zeroed out
        and confirmed signals have their strength scaled.
        """
        if signals is None:
            closes_signal = signal_tf_data["close"]
            closes_higher = higher_tf_data["close"]

            ema_signal = closes_signal.ewm(span=34, adjust=False).mean()
            ema_higher = closes_higher.ewm(span=self.ema_period_higher, adjust=False).mean()

            aligned = pd.Series(0, index=closes_signal.index)
            for i in range(len(closes_signal)):
                if i < len(ema_higher) and i < len(ema_signal):
                    sig = 1 if ema_signal.iloc[i] > closes_signal.iloc[i] * 0.999 else -1
                    trend = self._get_trend_direction(
                        closes_higher.iloc[:i+1] if i > 0 else closes_higher.iloc[:1],
                        ema_higher.iloc[:i+1] if i > 0 else ema_higher.iloc[:1],
                    )
                    if self._check_trend_alignment(sig, trend):
                        aligned.iloc[i] = sig

            return aligned

        confirmed_signals = pd.Series(0, index=signals.index)
        for i in range(len(signals)):
            if signals.iloc[i] == 0:
                continue

            end_idx = min(i + 1, len(signal_tf_data))
            signal_window = signal_tf_data.iloc[:end_idx]

            higher_ratio = len(higher_tf_data) / len(signal_tf_data)
            higher_end = max(1, int(i * higher_ratio))
            higher_window = higher_tf_data.iloc[:higher_end]

            if mid_tf_data is not None:
                mid_ratio = len(mid_tf_data) / len(signal_tf_data)
                mid_end = max(1, int(i * mid_ratio))
                mid_window = mid_tf_data.iloc[:mid_end]
            else:
                mid_window = None

            if len(higher_window) < 10:
                confirmed_signals.iloc[i] = signals.iloc[i]
                continue

            result = self.confirm_signal(
                signal_window,
                higher_window,
                mid_window,
                int(signals.iloc[i]),
            )

            if result.signal in (MTFSignal.CONFIRMED_LONG, MTFSignal.CONFIRMED_SHORT):
                confirmed_signals.iloc[i] = signals.iloc[i]
            elif result.signal in (MTFSignal.WEAKENED_LONG, MTFSignal.WEAKENED_SHORT):
                confirmed_signals.iloc[i] = signals.iloc[i] * 0.5
            else:
                confirmed_signals.iloc[i] = 0

        return confirmed_signals


class MultiTimeframeEvaluator:
    """
    Evaluates strategy performance with multi-timeframe confirmation.

    Compares base strategy returns vs MTF-filtered returns to quantify
    the improvement from higher-timeframe filtering.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.confirmator = MultiTimeframeConfirmator()

    def evaluate_with_mtf(
        self,
        signal_tf_data: pd.DataFrame,
        higher_tf_data: pd.DataFrame,
        mid_tf_data: Optional[pd.DataFrame] = None,
        base_signals: Optional[pd.Series] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate strategy with and without MTF confirmation.

        Returns dict with:
        - base_sharpe, base_return, base_trades
        - mtf_sharpe, mtf_return, mtf_trades
        - improvement_pct, signal_reduction_pct
        """
        closes = signal_tf_data["close"]
        returns = closes.pct_change().dropna()

        if base_signals is None:
            ema_fast = closes.ewm(span=12, adjust=False).mean()
            ema_slow = closes.ewm(span=26, adjust=False).mean()
            base_signals = pd.Series(0, index=closes.index)
            base_signals[ema_fast > ema_slow] = 1
            base_signals[ema_fast < ema_slow] = -1

        base_returns = base_signals.shift(1) * returns
        base_returns = base_returns.dropna()

        mtf_signals = self.confirmator.batch_confirm(
            signal_tf_data, higher_tf_data, mid_tf_data, base_signals,
        )
        mtf_returns = mtf_signals.shift(1) * returns
        mtf_returns = mtf_returns.dropna()

        base_sharpe = self._calc_sharpe(base_returns)
        mtf_sharpe = self._calc_sharpe(mtf_returns)

        base_trades = int((base_signals.diff().abs() > 0).sum())
        mtf_trades = int((mtf_signals.diff().abs() > 0).sum())

        base_total = float((1 + base_returns).prod() - 1) * 100
        mtf_total = float((1 + mtf_returns).prod() - 1) * 100

        signal_reduction = 0.0
        if base_trades > 0:
            signal_reduction = (1.0 - mtf_trades / base_trades) * 100

        improvement = 0.0
        if base_sharpe != 0:
            improvement = ((mtf_sharpe - base_sharpe) / abs(base_sharpe)) * 100

        return {
            "base_sharpe": base_sharpe,
            "base_return": base_total,
            "base_trades": base_trades,
            "mtf_sharpe": mtf_sharpe,
            "mtf_return": mtf_total,
            "mtf_trades": mtf_trades,
            "improvement_pct": improvement,
            "signal_reduction_pct": signal_reduction,
        }

    def _calc_sharpe(self, returns: pd.Series) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 10 or returns.std() == 0:
            return 0.0
        return float(returns.mean() / returns.std() * np.sqrt(252))
