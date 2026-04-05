"""
SIQE V3 - Binance USDT-M Futures CTA Strategy

Adapts SIQE's 3-strategy ensemble for leveraged futures trading with:
- Configurable leverage (35-75x)
- Margin utilization tracking
- Liquidation price calculation
- Tight stop losses for high leverage
- Circuit breaker on margin threshold
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

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
import pandas as pd


class SiqeFuturesStrategy(CtaTemplate):
    """
    SIQE V3 futures CTA strategy for Binance USDT-M contracts.

    Same 3-strategy ensemble as spot, but with:
    - Leverage-based position sizing
    - Margin tracking and alerts
    - Liquidation monitoring
    - Tighter stops for leveraged positions
    - Phase 8: Directional bias detection & signal attenuation
    """

    author = "SIQE"

    # --- Mean Reversion parameters ---
    mr_boll_period: int = 20
    mr_boll_dev: float = 1.8
    mr_rsi_period: int = 14
    mr_rsi_lower: float = 25.0
    mr_rsi_upper: float = 75.0

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
    bo_confirmation_bars: int = 1

    # --- Futures-specific ---
    leverage: int = 50
    risk_pct: float = 0.02
    margin_alert_pct: float = 0.70
    margin_stop_pct: float = 0.90

    # --- Risk Management ---
    atr_stop_multiplier: float = 1.0
    atr_trailing_multiplier: float = 0.75

    # --- Regime Detection ---
    regime_lookback: int = 20
    regime_vol_low: float = 0.015
    regime_vol_high: float = 0.04

    # --- Phase 8: Directional Bias Detection ---
    bias_ema50_period: int = 50
    bias_ema200_period: int = 200
    bias_threshold_pct: float = 0.01

    # --- Parameters & Variables lists ---
    parameters = [
        "mr_boll_period", "mr_boll_dev", "mr_rsi_period",
        "mr_rsi_lower", "mr_rsi_upper",
        "mom_fast_period", "mom_slow_period",
        "mom_macd_fast", "mom_macd_slow", "mom_macd_signal",
        "bo_donchian_period", "bo_atr_period", "bo_atr_multiplier",
        "bo_confirmation_bars",
        "leverage", "risk_pct", "margin_alert_pct", "margin_stop_pct",
        "atr_stop_multiplier", "atr_trailing_multiplier",
        "regime_lookback", "regime_vol_low", "regime_vol_high",
        "bias_ema50_period", "bias_ema200_period", "bias_threshold_pct",
    ]

    variables = [
        "regime", "regime_vol",
        "mr_signal", "mom_signal", "bo_signal",
        "entry_price", "liquidation_price",
        "margin_used", "margin_ratio",
        "highest_since_entry", "lowest_since_entry",
        "daily_pnl", "trade_count",
        "directional_bias", "bias_strength_mult", "position_size_mult",
    ]

    def __init__(self, cta_engine, strategy_name: str, vt_symbol: str, setting: dict) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg: Optional[BarGenerator] = None
        self.am: Optional[ArrayManager] = None

        # Regime state
        self.regime: str = "MIXED"
        self.regime_vol: float = 0.0

        # Sub-strategy signals
        self.mr_signal: int = 0
        self.mom_signal: int = 0
        self.bo_signal: int = 0

        # Position tracking
        self.entry_price: float = 0.0
        self.liquidation_price: float = 0.0
        self.highest_since_entry: float = 0.0
        self.lowest_since_entry: float = 0.0

        # Margin tracking
        self.margin_used: float = 0.0
        self.margin_ratio: float = 0.0

        # PnL tracking
        self.daily_pnl: float = 0.0
        self.trade_count: int = 0
        self._trading_active: bool = False

        # Entry tracking for PnL/duration calculation
        self._entry_timestamp: float = 0.0

        # Breakout confirmation
        self._bo_long_count: int = 0
        self._bo_short_count: int = 0

        # Phase 8: Directional bias state
        self.directional_bias: str = "NEUTRAL"
        self.bias_strength_mult: float = 1.0
        self.position_size_mult: float = 1.0
        self._price_history_closes: list = []
        
        # Debug and adaptive sensitivity
        self._bar_count: int = 0
        self._bars_without_signal: int = 0
        self._original_rsi_lower: int = 30
        self._original_rsi_upper: int = 70
        self._original_boll_dev: float = 2.0
        self._relaxation_factor: float = 1.0
        self._max_relaxation: float = 1.5

        # Alert manager for Telegram alerts
        self._alert_manager = None

        # SIQEEngine integration
        self._trade_callback = None
        self._risk_check_enabled = True
        self._logged_init = False
    
    def set_alert_manager(self, alert_manager) -> None:
        """Set alert manager for Telegram alerts."""
        self._alert_manager = alert_manager
        self.write_log("Alert manager connected to strategy")

    def on_init(self) -> None:
        """Initialize strategy."""
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(
            self.mr_boll_period,
            self.mom_slow_period,
            self.bo_donchian_period,
            self.bo_atr_period,
            self.regime_lookback,
        ) + 10)
        self.load_bar(1, use_database=False)

    def on_start(self) -> None:
        """Start trading."""
        self._trading_active = True
        self.write_log("SIQE Futures Strategy started")

    def on_stop(self) -> None:
        """Stop trading."""
        self.write_log("SIQE Futures Strategy stopped")

    def on_tick(self, tick: TickData) -> None:
        """Feed tick data into BarGenerator."""
        if tick.extra and tick.extra.get("bar"):
            self.bg.update_bar(tick.extra["bar"])
        else:
            self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """Main strategy logic on each bar."""
        self.cancel_all()
        self._bar_count += 1

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            if self._bar_count % 60 == 0:
                self.write_log(f"ArrayManager warming up: {self._bar_count} bars (need {am.size})")
            return

        # First init debug log
        if hasattr(self, '_logged_init') and not self._logged_init:
            self.write_log(f"ArrayManager initialized after {self._bar_count} bars")
            self._logged_init = True
            self._original_rsi_lower = self.mr_rsi_lower
            self._original_rsi_upper = self.mr_rsi_upper
            self._original_boll_dev = self.mr_boll_dev

        # Phase 8: Update price history for bias detection
        self._update_price_history(bar.close_price)
        
        # Detect directional bias (EMA crossover)
        self._detect_directional_bias()
        
        self._detect_regime(am, bar)
        self._compute_mr_signal(am, bar)
        self._compute_mom_signal(am, bar)
        self._compute_bo_signal(am, bar)

        if self.margin_ratio >= self.margin_stop_pct:
            self.write_log(f"MARGIN STOP: margin ratio {self.margin_ratio:.1%} >= {self.margin_stop_pct:.1%}")
            if self._alert_manager:
                self._alert_manager.margin_critical(
                    margin_ratio=self.margin_ratio,
                    threshold=self.margin_stop_pct
                )
            if self.pos != 0:
                self._close_position(bar.close_price)
            return

        # Alert on high margin usage
        if self.margin_ratio >= self.margin_alert_pct:
            self.write_log(f"MARGIN ALERT: {self.margin_ratio:.1%} used")
            if self._alert_manager:
                self._alert_manager.margin_warning(
                    margin_ratio=self.margin_ratio,
                    threshold=self.margin_alert_pct
                )
        
        # Check liquidation risk (price within 5% of liquidation)
        if self.pos != 0 and self.liquidation_price > 0:
            if self.pos > 0:
                distance_pct = (self.liquidation_price / bar.close_price - 1) * 100 if bar.close_price > 0 else 0
            else:
                distance_pct = (bar.close_price / self.liquidation_price - 1) * 100 if self.liquidation_price > 0 else 0
            
            if distance_pct > 0 and distance_pct <= 5.0:
                if self._alert_manager:
                    self._alert_manager.liquidation_risk(
                        current_price=bar.close_price,
                        liquidation_price=self.liquidation_price,
                        distance_pct=distance_pct
                    )

        ensemble_score = self._ensemble_score()
        
        # Track bars without signal for adaptive sensitivity
        if ensemble_score == 0:
            self._bars_without_signal += 1
        else:
            self._bars_without_signal = 0
            # Reset relaxation on signal
            if self._relaxation_factor > 1.0:
                self.mr_rsi_lower = self._original_rsi_lower
                self.mr_rsi_upper = self._original_rsi_upper
                self.mr_boll_dev = self._original_boll_dev
                self._relaxation_factor = 1.0
                self.write_log(f"Signal detected - reset thresholds to original")
        
        # Adaptive sensitivity: relax thresholds if no signals for too long
        # Relaxation makes bands WIDER to generate more signals
        if self._bars_without_signal > 60 and self._relaxation_factor < self._max_relaxation:
            self._relaxation_factor = min(self._bars_without_signal / 40, self._max_relaxation)
            # Widen RSI bands: lower goes down, upper goes up
            self.mr_rsi_lower = max(15, int(self._original_rsi_lower - 5 * (self._relaxation_factor - 1)))
            self.mr_rsi_upper = min(85, int(self._original_rsi_upper + 5 * (self._relaxation_factor - 1)))
            # Widen Bollinger bands (smaller multiplier = wider)
            self.mr_boll_dev = max(1.0, self._original_boll_dev / self._relaxation_factor)
            if self._bar_count % 30 == 0:
                self.write_log(f"Adaptive: relaxed RSILower={self.mr_rsi_lower}, RSIUpper={self.mr_rsi_upper}, BollDev={self.mr_boll_dev:.2f} (factor={self._relaxation_factor:.2f})")
        
        # Debug logging every 60 bars
        if self._bar_count % 60 == 0:
            self.write_log(f"DEBUG: REGIME={self.regime} BIAS={self.directional_bias} MR={self.mr_signal} MOM={self.mom_signal} BO={self.bo_signal} ENS={ensemble_score} NO_SIGNAL={self._bars_without_signal}")
        
        # Phase 8: Apply signal attenuation based on bias alignment
        if ensemble_score != 0:
            ensemble_score, self.bias_strength_mult = self._apply_bias_attenuation(
                ensemble_score, self.directional_bias
            )
        
        # Phase 8: Calculate bias-adjusted position size
        volume = self._calculate_volume(bar.close_price)
        volume = volume * self.position_size_mult

        if not self._trading_active:
            return

        if self.pos == 0:
            import time
            if ensemble_score > 0:
                self.buy(bar.close_price, volume)
                self.entry_price = bar.close_price
                self.highest_since_entry = bar.close_price
                self.lowest_since_entry = bar.close_price
                self._entry_timestamp = time.time()
                self._update_liquidation_price(bar.close_price, Direction.LONG)
                self.write_log(f"LONG {volume} @ {bar.close_price} liq={self.liquidation_price:.1f}")
                if self._alert_manager:
                    self._alert_manager.position_opened(
                        side="LONG",
                        volume=volume,
                        entry_price=bar.close_price
                    )
            elif ensemble_score < 0:
                self.short(bar.close_price, volume)
                self.entry_price = bar.close_price
                self.highest_since_entry = bar.close_price
                self.lowest_since_entry = bar.close_price
                self._entry_timestamp = time.time()
                self._update_liquidation_price(bar.close_price, Direction.SHORT)
                self.write_log(f"SHORT {volume} @ {bar.close_price} liq={self.liquidation_price:.1f}")
                if self._alert_manager:
                    self._alert_manager.position_opened(
                        side="SHORT",
                        volume=volume,
                        entry_price=bar.close_price
                    )

        elif self.pos > 0:
            self.highest_since_entry = max(self.highest_since_entry, bar.high_price)
            if self._should_exit_long(am, bar):
                import time
                exit_price = bar.close_price
                volume = abs(self.pos)
                pnl = (exit_price - self.entry_price) * volume if self.entry_price > 0 else 0.0
                duration_min = int((time.time() - self._entry_timestamp) / 60) if self._entry_timestamp > 0 else 0
                self.sell(bar.close_price, abs(self.pos))
                self.write_log(f"CLOSE LONG @ {bar.close_price} pnl={pnl:.2f}")
                if self._alert_manager:
                    self._alert_manager.position_closed(
                        pnl=pnl,
                        side="LONG",
                        duration_min=duration_min
                    )

        elif self.pos < 0:
            self.lowest_since_entry = min(self.lowest_since_entry, bar.low_price)
            if self._should_exit_short(am, bar):
                import time
                exit_price = bar.close_price
                volume = abs(self.pos)
                pnl = (self.entry_price - exit_price) * volume if self.entry_price > 0 else 0.0
                duration_min = int((time.time() - self._entry_timestamp) / 60) if self._entry_timestamp > 0 else 0
                self.cover(bar.close_price, abs(self.pos))
                self.write_log(f"CLOSE SHORT @ {bar.close_price} pnl={pnl:.2f}")
                if self._alert_manager:
                    self._alert_manager.position_closed(
                        pnl=pnl,
                        side="SHORT",
                        duration_min=duration_min
                    )

        self.put_event()

    def on_trade(self, trade: TradeData) -> None:
        """Called on trade fill."""
        self.trade_count += 1
        self._update_margin()
        self.put_event()
        
        if self._trade_callback:
            try:
                self._trade_callback(trade)
            except Exception as e:
                self.write_log(f"Trade callback error: {e}")

    def on_order(self, order: OrderData) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass

    # ------------------------------------------------------------------
    # SIQEEngine Integration
    # ------------------------------------------------------------------
    def set_trade_callback(self, callback) -> None:
        """Set callback for trade execution feedback to SIQEEngine."""
        self._trade_callback = callback
        self.write_log("Trade callback registered")

    async def _async_risk_check(self, signal_type: str, volume: float, price: float) -> bool:
        """Async risk check via SIQEEngine (non-blocking advisory)."""
        if not getattr(self, '_risk_check_enabled', True):
            return True
        
        risk_check = getattr(self, '_risk_check_callback', None)
        if not risk_check:
            return True
        
        try:
            import asyncio
            signal_data = {
                'signal_type': signal_type,
                'volume': volume,
                'price': price,
                'symbol': self.vt_symbol,
            }
            if asyncio.iscoroutinefunction(risk_check):
                result = await risk_check(signal_data)
            else:
                result = risk_check(signal_data)
            
            if result and hasattr(result, 'approved') and not result.approved:
                self.write_log(f"Risk check rejected: {result.reason}")
                return False
            return True
        except Exception as e:
            self.write_log(f"Risk check error: {e}")
            return True

    def set_risk_check_callback(self, callback) -> None:
        """Set async callback for pre-trade risk validation."""
        self._risk_check_callback = callback
        self.write_log("Risk check callback registered")

    # ------------------------------------------------------------------
    # Position Sizing with Leverage
    # ------------------------------------------------------------------
    def _calculate_volume(self, price: float) -> float:
        """
        Calculate trade volume based on leverage and risk percentage.

        volume = (capital * risk_pct) / (price / leverage)
        """
        capital = getattr(self.cta_engine, "capital", 10000)
        position_value = capital * self.risk_pct * self.leverage
        volume = position_value / price if price > 0 else 0

        # Round to reasonable precision (8 decimals for crypto)
        return round(volume, 8)

    def _update_margin(self) -> None:
        """Update margin usage based on current position."""
        if self.pos == 0:
            self.margin_used = 0.0
            self.margin_ratio = 0.0
            return

        capital = getattr(self.cta_engine, "capital", 10000)
        position_value = abs(self.pos) * self.entry_price
        self.margin_used = position_value / self.leverage
        self.margin_ratio = self.margin_used / capital if capital > 0 else 0

    def _update_liquidation_price(self, entry_price: float, direction: Direction) -> None:
        """
        Estimate liquidation price for cross margin, one-way position.

        Simplified: liquidation occurs when margin is depleted.
        Long:  liq = entry * (1 - 1/leverage)
        Short: liq = entry * (1 + 1/leverage)
        """
        if direction == Direction.LONG:
            self.liquidation_price = entry_price * (1 - 1 / self.leverage)
        else:
            self.liquidation_price = entry_price * (1 + 1 / self.leverage)

    def _close_position(self, price: float) -> None:
        """Close current position immediately."""
        if self.pos > 0:
            self.sell(price, abs(self.pos))
        elif self.pos < 0:
            self.cover(price, abs(self.pos))

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
    # Phase 8: Directional Bias Detection
    # ------------------------------------------------------------------
    def _update_price_history(self, close_price: float) -> None:
        """Update price history for bias detection."""
        if not hasattr(self, '_price_history_closes'):
            self._price_history_closes = []
        
        self._price_history_closes.append(close_price)
        
        max_history = max(self.bias_ema50_period, self.bias_ema200_period) + 10
        if len(self._price_history_closes) > max_history:
            self._price_history_closes = self._price_history_closes[-max_history:]

    def _detect_directional_bias(self) -> None:
        """Detect directional bias using EMA 50/200 crossover."""
        if len(self._price_history_closes) < self.bias_ema200_period + 10:
            self.directional_bias = "NEUTRAL"
            self.bias_strength_mult = 1.0
            self.position_size_mult = 1.0
            return
        
        closes = pd.Series(self._price_history_closes)
        
        ema50 = closes.ewm(span=self.bias_ema50_period, adjust=False).mean()
        ema200 = closes.ewm(span=self.bias_ema200_period, adjust=False).mean()
        
        diff_pct = (ema50.iloc[-1] - ema200.iloc[-1]) / ema200.iloc[-1]
        
        if diff_pct > self.bias_threshold_pct:
            self.directional_bias = "BULL"
        elif diff_pct < -self.bias_threshold_pct:
            self.directional_bias = "BEAR"
        else:
            self.directional_bias = "NEUTRAL"
        
        self._update_bias_multipliers()

    def _update_bias_multipliers(self) -> None:
        """Update position size multiplier based on directional bias."""
        if self.directional_bias == "NEUTRAL":
            self.position_size_mult = 0.75
        elif self.directional_bias == "BULL":
            self.position_size_mult = 1.0
        elif self.directional_bias == "BEAR":
            self.position_size_mult = 0.75

    def _apply_bias_attenuation(self, ensemble_score: int, bias: str) -> Tuple[int, float]:
        """
        Apply signal strength attenuation based on bias alignment.
        
        Returns: (adjusted_score, strength_multiplier)
        - BEAR + LONG: 0.5x (attenuated)
        - BEAR + SHORT: 1.25x (amplified)
        - BULL + LONG: 1.25x (amplified)
        - BULL + SHORT: 0.25x (heavily attenuated)
        
        Note: Uses sign-preserving logic so attenuated signals still trade,
        just with reduced conviction.
        """
        if bias == "NEUTRAL":
            return ensemble_score, 1.0
        
        strength_mult = 1.0
        
        if bias == "BEAR":
            if ensemble_score > 0:
                strength_mult = 0.5
            else:
                strength_mult = 1.25
        elif bias == "BULL":
            if ensemble_score > 0:
                strength_mult = 1.25
            else:
                strength_mult = 0.25
        
        adjusted_score = ensemble_score if strength_mult >= 1.0 else int(ensemble_score * strength_mult) + 1 if ensemble_score > 0 else int(ensemble_score * strength_mult) - 1 if ensemble_score < 0 else 0
        
        if ensemble_score != 0 and adjusted_score == 0:
            adjusted_score = ensemble_score
        
        return adjusted_score, strength_mult

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

        if bar.close_price > upper:
            self._bo_long_count += 1
            self._bo_short_count = 0
        else:
            self._bo_long_count = 0

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
        else:
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
    # Exit Logic (tighter stops for futures)
    # ------------------------------------------------------------------
    def _should_exit_long(self, am: ArrayManager, bar: BarData) -> bool:
        """Check if we should exit a long position."""
        atr = am.atr(self.bo_atr_period, array=False)
        if atr is None:
            atr = 0

        # ATR trailing stop (tighter for futures)
        trailing_stop = self.highest_since_entry - atr * self.atr_trailing_multiplier
        if bar.close_price < trailing_stop:
            return True

        # ATR fixed stop from entry (tighter for futures)
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

        # ATR trailing stop (tighter for futures)
        trailing_stop = self.lowest_since_entry + atr * self.atr_trailing_multiplier
        if bar.close_price > trailing_stop:
            return True

        # ATR fixed stop from entry (tighter for futures)
        stop_loss = self.entry_price + atr * self.atr_stop_multiplier
        if bar.close_price > stop_loss:
            return True

        # Opposite ensemble signal
        if self._ensemble_score() > 0:
            return True

        return False
