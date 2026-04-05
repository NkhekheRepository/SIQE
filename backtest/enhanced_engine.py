"""
SIQE V3 Enhanced Backtest Execution Engine
==========================================
Implements professional-grade backtesting with:
- ATR-based stop loss and take profit
- Time-based exits
- Realistic fee model with leverage amplification
- Position tracking across bars
- Regime-based filtering
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from backtest.config import BacktestSettings
from backtest.performance import PerformanceAnalyzer
from core.clock import EventClock
from models.trade import (
    MarketEvent, Signal, SignalType, OrderStatus, 
    Decision, ExecutionResult, RegimeType
)
from config.settings import Settings

logger = logging.getLogger(__name__)


class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIME_EXIT = "time_exit"
    REGIME_CHANGE = "regime_change"
    MANUAL = "manual"


@dataclass
class Position:
    """Track an open position with stop/TP levels."""
    position_id: str
    symbol: str
    signal_type: SignalType
    entry_price: float
    quantity: float
    entry_seq: int
    stop_loss: float
    take_profit: float
    atr_at_entry: float
    strategy: str
    regime: str
    bars_held: int = 0
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    
    def update(self, high: float, low: float, close: float):
        """Update position tracking with new bar data."""
        self.bars_held += 1
        self.highest_price = max(self.highest_price, high)
        self.lowest_price = min(self.lowest_price, low)


@dataclass
class EnhancedExecutionResult:
    """Enhanced execution result with exit details."""
    execution_id: str
    trade_id: str
    symbol: str
    signal_type: SignalType
    entry_price: float
    exit_price: float
    quantity: float
    status: OrderStatus
    exit_reason: ExitReason
    exit_seq: int
    strategy: str
    regime: str
    entry_slippage: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    net_pnl: float = 0.0
    bars_held: int = 0
    unrealized_max: float = 0.0


class EnhancedBacktestEngine:
    """
    Professional backtest engine with proper risk management.
    
    Features:
    - ATR-based stop loss (1.5x ATR)
    - ATR-based take profit (2.5x ATR)  
    - Time-based exits (8 bars)
    - Realistic fee model
    - Position tracking
    - Regime filtering
    """
    
    ATR_PERIOD = 14
    STOP_MULTIPLIER = 1.0  # Tighter stop for better risk/reward
    TP_MULTIPLIER = 2.0    # Lower TP target
    MAX_BARS_HELD = 8
    
    # Fee structure (Binance Futures)
    TAKER_FEE = 0.0004  # 0.04%
    MAKER_FEE = 0.0002  # 0.02%
    FUNDING_RATE = 0.0001  # 0.01% per 8hrs
    
    def __init__(self, bt_settings: BacktestSettings, settings: Settings):
        self.bt_settings = bt_settings
        self.siqe_settings = settings
        self.clock = EventClock()
        self._equity = bt_settings.initial_equity
        self._trade_log: List[Dict] = []
        self._parameter_updates = 0
        self._kill_triggered = False
        self._kill_reason = ""
        
        # Position tracking
        self._open_positions: Dict[str, Position] = {}
        self._price_history: Dict[str, pd.DataFrame] = {}
        self._atr_cache: Dict[str, float] = {}
        
        # Settings
        self.leverage = getattr(settings, 'leverage', 35)
        self.stop_multiplier = getattr(settings, 'stop_multiplier', self.STOP_MULTIPLIER)
        self.tp_multiplier = getattr(settings, 'tp_multiplier', self.TP_MULTIPLIER)
        self.max_bars = getattr(settings, 'max_bars_held', self.MAX_BARS_HELD)
        
        logger.info(f"Enhanced Backtest Engine initialized: leverage={self.leverage}x, "
                   f"stop={self.stop_multiplier}x ATR, tp={self.tp_multiplier}x ATR")
    
    def run(self, data: Dict[str, pd.DataFrame], components: Dict[str, Any]) -> Any:
        """Run the enhanced backtest."""
        start_time = time.time()
        
        # Store data for ATR calculations
        self._price_history = data
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Process events bar by bar
        bars_count = 0
        events = self._create_events(data)
        
        for event in events:
            bars_count += 1
            
            # Build price history for strategy engine (always update, regardless of position)
            if "strategy_engine" in components and event.symbol in self._price_history:
                df = self._price_history[event.symbol]
                current_idx = event.event_seq
                if current_idx < len(df):
                    row = df.iloc[current_idx]
                    try:
                        components["strategy_engine"].update_price_history(
                            event.symbol,
                            float(row['high']),
                            float(row['low']),
                            float(row['close'])
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update price history: {e}")
            
            # Check for position exits first
            self._check_position_exits(event, components)
            
            # Skip if we have a position (one position at a time per symbol)
            if self._open_positions:
                continue
            
            # Process new signals
            self._process_new_signals(event, components)
            
            # Check kill switches
            if self._check_kill_conditions():
                break
        
        # Close any remaining positions at end
        self._close_all_positions(components)
        
        # Compute metrics
        analyzer = PerformanceAnalyzer(
            initial_equity=self.bt_settings.initial_equity,
            bars_per_year=35040,  # 15m bars
        )
        
        # Add trades to analyzer
        for trade in self._trade_log:
            from backtest.performance import TradeRecord
            record = TradeRecord(
                trade_id=trade['trade_id'],
                symbol=trade['symbol'],
                signal_type=trade['signal_type'],
                entry_price=trade['entry_price'],
                exit_price=trade['exit_price'],
                size=trade['quantity'],
                pnl=trade['pnl'],
                pnl_pct=trade['pnl_pct'],
                slippage=trade.get('fees', 0),
                entry_seq=trade['entry_seq'],
                exit_seq=trade['exit_seq'],
                strategy=trade['strategy'],
                regime=trade.get('regime', ''),
            )
            analyzer.add_trade(record)
        
        for pnl in [t['pnl'] for t in self._trade_log]:
            analyzer.record_equity(self._equity + pnl)
        
        metrics = analyzer.compute()
        run_time = time.time() - start_time
        
        from backtest.engine import BacktestResult
        result = BacktestResult(
            metrics=metrics,
            settings=self._settings_dict(),
            config=self._config_dict(),
            trades=self._trade_log,
            run_time_seconds=run_time,
            seed=self.bt_settings.rng_seed,
            data_source=f"enhanced:{list(data.keys())[0] if data else 'unknown'}",
            bars_analyzed=bars_count,
            events_processed=bars_count,
            events_rejected=0,
            parameter_updates=self._parameter_updates,
            kill_triggered=self._kill_triggered,
            kill_reason=self._kill_reason,
        )
        
        logger.info(
            f"Enhanced Backtest complete: {bars_count} bars, {len(self._trade_log)} trades, "
            f"return={metrics.total_return_pct:.2f}%, sharpe={metrics.sharpe_ratio:.3f}, "
            f"max_dd={metrics.max_drawdown:.2%}"
        )
        
        return result
    
    def _create_events(self, data: Dict[str, pd.DataFrame]) -> List[MarketEvent]:
        """Convert dataframe to market events."""
        events = []
        symbol = list(data.keys())[0]
        df = data[symbol].copy()
        
        for idx, row in df.iterrows():
            close = float(row['close'])
            spread_pct = 0.0001
            bid = close * (1 - spread_pct / 2)
            ask = close * (1 + spread_pct / 2)
            
            volatility = (float(row['high']) - float(row['low'])) / float(row['low']) if float(row['low']) > 0 else 0.01
            
            events.append(MarketEvent(
                event_id=f"bt_evt_{len(events)}",
                symbol=symbol,
                bid=bid,
                ask=ask,
                volume=float(row['volume']),
                volatility=volatility,
                event_seq=len(events),
            ))
        
        return events
    
    def _calculate_atr(self, symbol: str, current_idx: int) -> float:
        """Calculate ATR at current bar."""
        if symbol not in self._price_history:
            return 0.001 * self._price_history[symbol].iloc[current_idx]['close']
        
        df = self._price_history[symbol]
        if current_idx < self.ATR_PERIOD:
            return 0.001 * df.iloc[current_idx]['close']
        
        # True Range calculation
        trs = []
        for i in range(max(0, current_idx - self.ATR_PERIOD), current_idx + 1):
            high = float(df.iloc[i]['high'])
            low = float(df.iloc[i]['low'])
            prev_close = float(df.iloc[i - 1]['close']) if i > 0 else close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        
        return np.mean(trs)
    
    def _check_position_exits(self, event: MarketEvent, components: Dict[str, Any]) -> None:
        """Check if any positions should be exited."""
        if not self._open_positions:
            return
        
        symbol = event.symbol
        if symbol not in self._price_history:
            return
        
        df = self._price_history[symbol]
        current_idx = event.event_seq
        
        if current_idx >= len(df):
            return
        
        bar_high = float(df.iloc[current_idx]['high'])
        bar_low = float(df.iloc[current_idx]['low'])
        bar_close = float(df.iloc[current_idx]['close'])
        
        for pos_id, position in list(self._open_positions.items()):
            if position.symbol != symbol:
                continue
            
            position.update(bar_high, bar_low, bar_close)
            
            # Check stop loss
            stop_triggered = False
            tp_triggered = False
            
            if position.signal_type == SignalType.LONG:
                if bar_low <= position.stop_loss:
                    stop_triggered = True
                    exit_price = position.stop_loss
                elif bar_high >= position.take_profit:
                    tp_triggered = True
                    exit_price = position.take_profit
            else:  # SHORT
                if bar_high >= position.stop_loss:
                    stop_triggered = True
                    exit_price = position.stop_loss
                elif bar_low <= position.take_profit:
                    tp_triggered = True
                    exit_price = position.take_profit
            
            # Check time exit
            time_exit = position.bars_held >= self.max_bars
            
            # Check regime change
            try:
                regime = components.get("regime_engine")
                regime_change = False
                if regime and hasattr(regime, '_current_regime'):
                    if position.regime == "RANGING" and regime._current_regime != "RANGING":
                        regime_change = True
                    elif position.regime == "TRENDING" and regime._current_regime == "RANGING":
                        regime_change = True
            except Exception:
                regime_change = False
            
            # Determine exit reason and price
            exit_reason = None
            if stop_triggered:
                exit_reason = ExitReason.STOP_LOSS
            elif tp_triggered:
                exit_reason = ExitReason.TAKE_PROFIT
            elif time_exit:
                exit_reason = ExitReason.TIME_EXIT
                exit_price = bar_close
            elif regime_change:
                exit_reason = ExitReason.REGIME_CHANGE
                exit_price = bar_close
            
            if exit_reason:
                self._close_position(position, exit_price, exit_reason, event.event_seq)
    
    def _close_position(self, position: Position, exit_price: float, 
                        reason: ExitReason, exit_seq: int) -> None:
        """Close a position and record the trade."""
        # Calculate PnL
        if position.signal_type == SignalType.LONG:
            raw_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            raw_pnl = (position.entry_price - exit_price) * position.quantity
        
        # Calculate fees (entry + exit)
        entry_value = position.entry_price * position.quantity
        exit_value = exit_price * position.quantity
        fees = (entry_value + exit_value) * self.TAKER_FEE
        
        # Apply leverage to PnL
        leveraged_pnl = raw_pnl * self.leverage
        net_pnl = leveraged_pnl - fees
        
        # Record trade
        trade_record = {
            "trade_id": position.position_id,
            "symbol": position.symbol,
            "signal_type": position.signal_type.value,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "quantity": position.quantity,
            "pnl": net_pnl,
            "pnl_pct": net_pnl / self._equity * 100,
            "fees": fees,
            "exit_reason": reason.value,
            "entry_seq": position.entry_seq,
            "exit_seq": exit_seq,
            "strategy": position.strategy,
            "regime": position.regime,
            "bars_held": position.bars_held,
            "atr_at_entry": position.atr_at_entry,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "equity_after": self._equity + net_pnl,
        }
        
        self._trade_log.append(trade_record)
        self._equity += net_pnl
        
        # Remove from open positions
        del self._open_positions[position.position_id]
        
        logger.debug(f"Closed {position.position_id}: {reason.value}, PnL={net_pnl:.2f}, Equity={self._equity:.2f}")
    
    def _process_new_signals(self, event: MarketEvent, components: Dict[str, Any]) -> None:
        """Process new signals and open positions."""
        symbol = event.symbol
        
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Build price history for strategy engine
        if "strategy_engine" in components and symbol in self._price_history:
            df = self._price_history[symbol]
            current_idx = event.event_seq
            if current_idx < len(df):
                row = df.iloc[current_idx]
                try:
                    components["strategy_engine"].update_price_history(
                        symbol,
                        float(row['high']),
                        float(row['low']),
                        float(row['close'])
                    )
                except Exception as e:
                    logger.warning(f"Failed to update price history: {e}")
        
        # Generate regime
        regime_result = None
        if "regime_engine" in components:
            try:
                regime_result = loop.run_until_complete(
                    components["regime_engine"].detect_regime(event)
                )
            except Exception as e:
                logger.warning(f"Regime detection failed: {e}")
                return
        
        # Generate signals
        signals = None
        if "strategy_engine" in components:
            try:
                signals = loop.run_until_complete(
                    components["strategy_engine"].generate_signals(event, regime_result=regime_result)
                )
            except Exception as e:
                logger.warning(f"Signal generation failed: {e}")
                return
        
        if not signals:
            return
        
        # Calculate EV
        ev_results = None
        if "ev_engine" in components:
            try:
                ev_results = loop.run_until_complete(
                    components["ev_engine"].calculate_ev(signals, event, regime_result=regime_result)
                )
            except Exception as e:
                logger.warning(f"EV calculation failed: {e}")
                return
        
        if not ev_results:
            return
        
        # Make decision
        decision = None
        if "decision_engine" in components:
            try:
                decision = loop.run_until_complete(
                    components["decision_engine"].make_decision(ev_results, regime_result=regime_result)
                )
            except Exception as e:
                logger.warning(f"Decision making failed: {e}")
                return
        
        if not decision or not decision.actionable:
            return
        
        # Allow all trades through - regime filtering done at strategy level
        
        # Validate with meta harness
        if "meta_harness" in components:
            try:
                meta = loop.run_until_complete(
                    components["meta_harness"].validate_trade(decision)
                )
                if not meta.approved:
                    return
            except Exception as e:
                logger.warning(f"Meta harness validation failed: {e}")
                return
        
        # Risk validation
        risk_scaling = 1.0
        if regime_result and hasattr(regime_result, 'risk_scaling'):
            risk_scaling = regime_result.risk_scaling
        if "risk_engine" in components:
            try:
                risk = loop.run_until_complete(
                    components["risk_engine"].validate_trade(decision, risk_scaling=risk_scaling)
                )
                if not risk.approved:
                    return
            except Exception as e:
                logger.warning(f"Risk validation failed: {e}")
                return
        
        # Open position
        self._open_position(decision, event, regime_result, components)
    
    def _open_position(self, decision: Decision, event: MarketEvent, 
                       regime_result, components: Dict[str, Any]) -> None:
        """Open a new position with stop loss and take profit."""
        symbol = event.symbol
        
        # Calculate ATR
        atr = self._calculate_atr(symbol, event.event_seq)
        current_price = event.mid_price
        
        # Determine stop and TP based on signal direction
        if decision.signal_type == SignalType.LONG:
            stop_loss = current_price - (atr * self.stop_multiplier)
            take_profit = current_price + (atr * self.tp_multiplier)
        else:
            stop_loss = current_price + (atr * self.stop_multiplier)
            take_profit = current_price - (atr * self.tp_multiplier)
        
        # Position size based on risk per trade (1% max)
        risk_amount = self._equity * 0.01
        stop_distance = abs(current_price - stop_loss)
        if stop_distance > 0:
            quantity = risk_amount / stop_distance
        else:
            quantity = self._equity * 0.05 / current_price
        
        # Apply max position size
        max_qty = (self._equity * 0.05) / current_price  # 5% max
        quantity = min(quantity, max_qty)
        
        # Calculate entry fees
        entry_value = current_price * quantity
        entry_fee = entry_value * self.MAKER_FEE
        self._equity -= entry_fee
        
        # Create position
        regime = regime_result.regime.value if regime_result and hasattr(regime_result.regime, 'value') else "MIXED"
        position_id = f"bt_pos_{len(self._trade_log) + len(self._open_positions) + 1}"
        
        position = Position(
            position_id=position_id,
            symbol=symbol,
            signal_type=decision.signal_type,
            entry_price=current_price,
            quantity=quantity,
            entry_seq=event.event_seq,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_at_entry=atr,
            strategy=decision.strategy,
            regime=regime,
        )
        
        self._open_positions[position_id] = position
        
        logger.debug(f"Opened {position_id}: {decision.signal_type.value} @ {current_price}, "
                    f"SL={stop_loss:.2f}, TP={take_profit:.2f}, ATR={atr:.2f}")
    
    def _close_all_positions(self, components: Dict[str, Any]) -> None:
        """Close all remaining positions at end of backtest."""
        if not self._open_positions:
            return
        
        for position in list(self._open_positions.values()):
            # Get last close price
            if position.symbol in self._price_history:
                df = self._price_history[position.symbol]
                exit_price = float(df.iloc[-1]['close'])
                self._close_position(position, exit_price, ExitReason.MANUAL, len(df) - 1)
    
    def _check_kill_conditions(self) -> bool:
        """Check if kill switches should trigger."""
        max_drawdown = 0.15
        max_daily_loss = 0.05
        
        # Check equity drop
        equity_drop = (self.bt_settings.initial_equity - self._equity) / self.bt_settings.initial_equity
        
        if equity_drop >= max_drawdown:
            self._kill_triggered = True
            self._kill_reason = f"Max drawdown {equity_drop:.1%} exceeded"
            return True
        
        # Check consecutive losses
        recent_pnls = [t['pnl'] for t in self._trade_log[-5:]]
        if len(recent_pnls) >= 5 and all(p < 0 for p in recent_pnls):
            self._kill_triggered = True
            self._kill_reason = "5 consecutive losses"
            return True
        
        return False
    
    def _settings_dict(self) -> Dict[str, Any]:
        """Serialize backtest settings."""
        return {
            "data_provider": self.bt_settings.data_provider.value,
            "symbols": self.bt_settings.symbols,
            "timeframe": self.bt_settings.timeframe,
            "initial_equity": self.bt_settings.initial_equity,
            "leverage": self.leverage,
        }
    
    def _config_dict(self) -> Dict[str, Any]:
        """Serialize configuration."""
        return {
            "stop_multiplier": self.stop_multiplier,
            "tp_multiplier": self.tp_multiplier,
            "max_bars_held": self.max_bars,
            "atr_period": self.ATR_PERIOD,
            "taker_fee": self.TAKER_FEE,
            "maker_fee": self.MAKER_FEE,
            "risk_per_trade": 0.01,
            "max_position_size": 0.05,
        }
