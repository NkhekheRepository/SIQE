"""
SIQE V3 - VN.PY Native CTA Strategy

Adapts SIQE's 3-strategy ensemble (Mean Reversion, Momentum, Breakout)
into a single VN.PY CTA strategy with real indicator-based signals,
position management, and risk controls.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from vnpy.trader.constant import Direction


class SiqeCtaStrategy(CtaTemplate):
    """
    SIQE V3 ensemble CTA strategy for VN.PY.

    Combines 3 sub-strategies with regime filtering:
    - Mean Reversion: Bollinger Bands + RSI (blocked in TRENDING)
    - Momentum: MA crossover + MACD (blocked in RANGING)
    - Breakout: Donchian Channel + ATR (blocked in RANGING)

    Regime detection uses volatility thresholds:
    - LOW vol (< 1.5% ATR/close)  -> favors mean reversion
    - HIGH vol (> 4% ATR/close)   -> favors breakout
    - MID vol                     -> favors momentum
    """

    author = "SIQE"

    # --- Mean Reversion parameters ---
    mr_boll_period: int = 20
    mr_boll_dev: float = 2.0
    mr_rsi_period: int = 14
    mr_rsi_lower: float = 30.0
    mr_rsi_upper: float = 70.0

    # --- Momentum parameters ---
    mom_fast_period: int = 10
    mom_slow_period: int = 30
    mom_macd_fast: int = 12
    mom_macd_slow: int = 26
    mom_macd_signal: int = 9

    # --- Breakout parameters ---
    bo_donchian_period: int = 20
    bo_atr_period: int = 14
    bo_atr_multiplier: float = 2.0
    bo_confirmation_bars: int = 2

    # --- Risk Management ---
    fixed_volume: float = 0.01
    atr_stop_multiplier: float = 2.0
    atr_trailing_multiplier: float = 1.5
    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.05

    # --- Regime Detection ---
    regime_lookback: int = 20
    regime_vol_low: float = 0.015
    regime_vol_high: float = 0.04

    # --- Parameters & Variables lists ---
    parameters = [
        "mr_boll_period", "mr_boll_dev", "mr_rsi_period",
        "mr_rsi_lower", "mr_rsi_upper",
        "mom_fast_period", "mom_slow_period",
        "mom_macd_fast", "mom_macd_slow", "mom_macd_signal",
        "bo_donchian_period", "bo_atr_period", "bo_atr_multiplier",
        "bo_confirmation_bars",
        "fixed_volume", "atr_stop_multiplier", "atr_trailing_multiplier",
        "max_position_pct", "max_daily_loss_pct",
        "regime_lookback", "regime_vol_low", "regime_vol_high",
    ]

    variables = [
        "regime", "regime_vol",
        "mr_signal", "mom_signal", "bo_signal",
        "entry_price", "highest_since_entry", "lowest_since_entry",
        "daily_pnl", "trade_count",
    ]

    def __init__(self, cta_engine, strategy_name: str, vt_symbol: str, setting: dict) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg: Optional[BarGenerator] = None
        self.am: Optional[ArrayManager] = None

        # Regime state
        self.regime: str = "MIXED"
        self.regime_vol: float = 0.0

        # Sub-strategy signals: -1 = short, 0 = neutral, 1 = long
        self.mr_signal: int = 0
        self.mom_signal: int = 0
        self.bo_signal: int = 0

        # Position tracking
        self.entry_price: float = 0.0
        self.highest_since_entry: float = 0.0
        self.lowest_since_entry: float = 0.0

        # PnL tracking
        self.daily_pnl: float = 0.0
        self.trade_count: int = 0
        self.start_equity: float = 0.0

        # Breakout confirmation counter
        self._bo_long_count: int = 0
        self._bo_short_count: int = 0

    def on_init(self) -> None:
        """Called on strategy initialization."""
        self.write_log("SIQE CTA Strategy initialized")
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(
            self.mr_boll_period,
            self.mom_slow_period,
            self.bo_donchian_period,
            self.bo_atr_period,
            self.regime_lookback,
        ) + 10)
        self.load_bar(10)

    def on_start(self) -> None:
        """Called when strategy starts."""
        self.write_log("SIQE CTA Strategy started")
        self.start_equity = self.cta_engine.capital if hasattr(self.cta_engine, "capital") else 0

    def on_stop(self) -> None:
        """Called when strategy stops."""
        self.write_log("SIQE CTA Strategy stopped")

    def on_tick(self, tick: TickData) -> None:
        """Feed tick data into BarGenerator."""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """Main strategy logic on each bar."""
        self.cancel_all()

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 1. Detect market regime
        self._detect_regime(am, bar)

        # 2. Compute sub-strategy signals
        self._compute_mr_signal(am, bar)
        self._compute_mom_signal(am, bar)
        self._compute_bo_signal(am, bar)

        # 3. Ensemble: combine signals with regime weighting
        ensemble_score = self._ensemble_score()

        # 4. Execute trades
        if self.pos == 0:
            if ensemble_score > 0:
                self.buy(bar.close_price, self.fixed_volume)
                self.entry_price = bar.close_price
                self.highest_since_entry = bar.close_price
                self.lowest_since_entry = bar.close_price
            elif ensemble_score < 0:
                self.short(bar.close_price, self.fixed_volume)
                self.entry_price = bar.close_price
                self.highest_since_entry = bar.close_price
                self.lowest_since_entry = bar.close_price

        elif self.pos > 0:
            self.highest_since_entry = max(self.highest_since_entry, bar.high_price)
            if self._should_exit_long(am, bar):
                self.sell(bar.close_price, abs(self.pos))

        elif self.pos < 0:
            self.lowest_since_entry = min(self.lowest_since_entry, bar.low_price)
            if self._should_exit_short(am, bar):
                self.cover(bar.close_price, abs(self.pos))

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """Called on trade fill."""
        self.trade_count += 1
        self.put_event()

    def on_order(self, order: OrderData) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass

    # ------------------------------------------------------------------
    # Regime Detection
    # ------------------------------------------------------------------
    def _detect_regime(self, am: ArrayManager, bar: BarData) -> None:
        """Detect market regime using ATR-based volatility."""
        atr = am.atr(self.regime_lookback, array=False)
        if atr is None or bar.close_price == 0:
            self.regime = "MIXED"
            self.regime_vol = 0.0
            return

        self.regime_vol = atr / bar.close_price

        if self.regime_vol < self.regime_vol_low:
            self.regime = "RANGING"
        elif self.regime_vol > self.regime_vol_high:
            self.regime = "VOLATILE"
        else:
            self.regime = "TRENDING"

    # ------------------------------------------------------------------
    # Mean Reversion Sub-Strategy
    # ------------------------------------------------------------------
    def _compute_mr_signal(self, am: ArrayManager, bar: BarData) -> None:
        """Bollinger Bands + RSI mean reversion signal."""
        if self.regime == "TRENDING":
            self.mr_signal = 0
            return

        upper, lower = am.boll(self.mr_boll_period, self.mr_boll_dev, array=False)
        rsi = am.rsi(self.mr_rsi_period, array=False)

        if upper is None or rsi is None:
            self.mr_signal = 0
            return

        if bar.close_price <= lower and rsi < self.mr_rsi_lower:
            self.mr_signal = 1
        elif bar.close_price >= upper and rsi > self.mr_rsi_upper:
            self.mr_signal = -1
        else:
            self.mr_signal = 0

    # ------------------------------------------------------------------
    # Momentum Sub-Strategy
    # ------------------------------------------------------------------
    def _compute_mom_signal(self, am: ArrayManager, bar: BarData) -> None:
        """MA crossover + MACD momentum signal."""
        if self.regime == "RANGING":
            self.mom_signal = 0
            return

        fast_ma = am.sma(self.mom_fast_period, array=False)
        slow_ma = am.sma(self.mom_slow_period, array=False)
        macd, signal_line, _ = am.macd(
            self.mom_macd_fast, self.mom_macd_slow, self.mom_macd_signal, array=False
        )

        if fast_ma is None or macd is None:
            self.mom_signal = 0
            return

        bullish = fast_ma > slow_ma and macd > signal_line
        bearish = fast_ma < slow_ma and macd < signal_line

        if bullish:
            self.mom_signal = 1
        elif bearish:
            self.mom_signal = -1
        else:
            self.mom_signal = 0

    # ------------------------------------------------------------------
    # Breakout Sub-Strategy
    # ------------------------------------------------------------------
    def _compute_bo_signal(self, am: ArrayManager, bar: BarData) -> None:
        """Donchian Channel + ATR breakout signal with confirmation."""
        if self.regime == "RANGING":
            self.bo_signal = 0
            self._bo_long_count = 0
            self._bo_short_count = 0
            return

        upper, lower = am.donchian(self.bo_donchian_period, array=False)
        atr = am.atr(self.bo_atr_period, array=False)

        if upper is None or atr is None:
            self.bo_signal = 0
            return

        # Long breakout: close above Donchian upper
        if bar.close_price > upper:
            self._bo_long_count += 1
            self._bo_short_count = 0
        else:
            self._bo_long_count = 0

        # Short breakdown: close below Donchian lower
        if bar.close_price < lower:
            self._bo_short_count += 1
            self._bo_long_count = 0
        else:
            self._bo_short_count = 0

        if self._bo_long_count >= self.bo_confirmation_bars:
            self.bo_signal = 1
        elif self._bo_short_count >= self.bo_confirmation_bars:
            self.bo_signal = -1
        else:
            self.bo_signal = 0

    # ------------------------------------------------------------------
    # Ensemble Scoring
    # ------------------------------------------------------------------
    def _ensemble_score(self) -> int:
        """
        Combine sub-strategy signals with regime weighting.

        Returns: -1 (short), 0 (neutral), 1 (long)
        """
        weights = {"mr": 0, "mom": 0, "bo": 0}

        if self.regime == "RANGING":
            weights["mr"] = 2
        elif self.regime == "TRENDING":
            weights["mom"] = 2
            weights["bo"] = 1
        elif self.regime == "VOLATILE":
            weights["bo"] = 2
            weights["mom"] = 1
        else:  # MIXED
            weights["mr"] = 1
            weights["mom"] = 1
            weights["bo"] = 1

        score = (
            weights["mr"] * self.mr_signal
            + weights["mom"] * self.mom_signal
            + weights["bo"] * self.bo_signal
        )

        if score > 0:
            return 1
        elif score < 0:
            return -1
        return 0

    # ------------------------------------------------------------------
    # Exit Logic
    # ------------------------------------------------------------------
    def _should_exit_long(self, am: ArrayManager, bar: BarData) -> bool:
        """Check if we should exit a long position."""
        atr = am.atr(self.bo_atr_period, array=False)
        if atr is None:
            atr = 0

        # ATR trailing stop
        trailing_stop = self.highest_since_entry - atr * self.atr_trailing_multiplier
        if bar.close_price < trailing_stop:
            return True

        # ATR fixed stop from entry
        stop_loss = self.entry_price - atr * self.atr_stop_multiplier
        if bar.close_price < stop_loss:
            return True

        # Opposite ensemble signal
        if self._ensemble_score() < 0:
            return True

        return False

    def _should_exit_short(self, am: ArrayManager, bar: BarData) -> bool:
        """Check if we should exit a short position."""
        atr = am.atr(self.bo_atr_period, array=False)
        if atr is None:
            atr = 0

        # ATR trailing stop
        trailing_stop = self.lowest_since_entry + atr * self.atr_trailing_multiplier
        if bar.close_price > trailing_stop:
            return True

        # ATR fixed stop from entry
        stop_loss = self.entry_price + atr * self.atr_stop_multiplier
        if bar.close_price > stop_loss:
            return True

        # Opposite ensemble signal
        if self._ensemble_score() > 0:
            return True

        return False
