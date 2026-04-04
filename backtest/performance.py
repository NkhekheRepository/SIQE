"""
Performance Analyzer
Computes comprehensive trading metrics from backtest results.
"""
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    """Single trade record for analysis."""
    trade_id: str
    symbol: str
    signal_type: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    slippage: float
    entry_seq: int
    exit_seq: int
    strategy: str
    regime: str = ""


@dataclass
class PerformanceMetrics:
    """Complete performance metrics from a backtest run."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    avg_drawdown: float = 0.0
    avg_trade_duration: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    pnl_by_symbol: Dict[str, float] = field(default_factory=dict)
    pnl_by_strategy: Dict[str, float] = field(default_factory=dict)
    pnl_by_regime: Dict[str, float] = field(default_factory=dict)
    avg_slippage_bps: float = 0.0
    total_slippage: float = 0.0
    initial_equity: float = 0.0
    final_equity: float = 0.0
    events_processed: int = 0
    events_rejected: int = 0
    bars_analyzed: int = 0


class PerformanceAnalyzer:
    """Computes performance metrics from equity curve and trade log."""

    def __init__(self, initial_equity: float = 10000.0, bars_per_year: int = 252):
        self.initial_equity = initial_equity
        self.bars_per_year = bars_per_year
        self._equity_points: List[float] = [initial_equity]
        self._trades: List[TradeRecord] = []
        self._events_processed = 0
        self._events_rejected = 0
        self._bars_analyzed = 0

    def record_equity(self, equity: float):
        self._equity_points.append(equity)

    def add_trade(self, trade: TradeRecord):
        self._trades.append(trade)

    def set_event_counts(self, processed: int, rejected: int):
        self._events_processed = processed
        self._events_rejected = rejected

    def set_bars_analyzed(self, count: int):
        self._bars_analyzed = count

    def compute(self) -> PerformanceMetrics:
        metrics = PerformanceMetrics()
        metrics.initial_equity = self.initial_equity
        metrics.events_processed = self._events_processed
        metrics.events_rejected = self._events_rejected
        metrics.bars_analyzed = self._bars_analyzed

        equity = np.array(self._equity_points, dtype=float)
        metrics.equity_curve = equity.tolist()
        metrics.final_equity = equity[-1] if len(equity) > 0 else self.initial_equity

        returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([0.0])
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        metrics.daily_returns = returns.tolist()

        if len(self._trades) == 0:
            metrics.total_return_pct = (metrics.final_equity - self.initial_equity) / self.initial_equity * 100
            metrics.sharpe_ratio = self._calc_sharpe(returns)
            metrics.sortino_ratio = self._calc_sortino(returns)
            metrics.max_drawdown, metrics.max_drawdown_duration = self._calc_max_drawdown(equity)
            metrics.drawdown_curve = self._calc_drawdown_curve(equity)
            return metrics

        trades = self._trades
        pnls = np.array([t.pnl for t in trades])

        metrics.total_trades = len(trades)
        metrics.winning_trades = int(np.sum(pnls > 0))
        metrics.losing_trades = int(np.sum(pnls <= 0))
        metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades > 0 else 0.0

        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        metrics.avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
        metrics.avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0

        gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        metrics.total_pnl = float(np.sum(pnls))
        metrics.total_return_pct = metrics.total_pnl / self.initial_equity * 100

        metrics.sharpe_ratio = self._calc_sharpe(returns)
        metrics.sortino_ratio = self._calc_sortino(returns)
        metrics.max_drawdown, metrics.max_drawdown_duration = self._calc_max_drawdown(equity)
        metrics.drawdown_curve = self._calc_drawdown_curve(equity)
        metrics.avg_drawdown = float(np.mean(metrics.drawdown_curve)) if metrics.drawdown_curve else 0.0

        if len(equity) > 1:
            peak = equity[0]
            calmar_dd = 0.0
            for eq in equity:
                peak = max(peak, eq)
                dd = (peak - eq) / peak if peak > 0 else 0
                calmar_dd = max(calmar_dd, dd)
            annualized_return = (metrics.final_equity / self.initial_equity) ** (self.bars_per_year / max(1, len(equity))) - 1
            metrics.calmar_ratio = annualized_return / calmar_dd if calmar_dd > 0 else 0.0

        durations = [t.exit_seq - t.entry_seq for t in trades if t.exit_seq > t.entry_seq]
        metrics.avg_trade_duration = float(np.mean(durations)) if durations else 0.0

        metrics.max_consecutive_wins = self._max_consecutive(pnls > 0)
        metrics.max_consecutive_losses = self._max_consecutive(pnls <= 0)

        total_slip = sum(abs(t.slippage) * t.size for t in trades)
        metrics.total_slippage = total_slip
        avg_notional = np.mean([t.entry_price * t.size for t in trades]) if trades else 1.0
        metrics.avg_slippage_bps = (total_slip / avg_notional * 10000) if avg_notional > 0 and len(trades) > 0 else 0.0

        for t in trades:
            metrics.pnl_by_symbol[t.symbol] = metrics.pnl_by_symbol.get(t.symbol, 0.0) + t.pnl
            metrics.pnl_by_strategy[t.strategy] = metrics.pnl_by_strategy.get(t.strategy, 0.0) + t.pnl
            if t.regime:
                metrics.pnl_by_regime[t.regime] = metrics.pnl_by_regime.get(t.regime, 0.0) + t.pnl

        return metrics

    def _calc_sharpe(self, returns: np.ndarray) -> float:
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * math.sqrt(self.bars_per_year))

    def _calc_sortino(self, returns: np.ndarray) -> float:
        if len(returns) < 2:
            return 0.0
        downside = returns[returns < 0]
        if len(downside) == 0:
            return float("inf") if np.mean(returns) > 0 else 0.0
        downside_std = float(np.std(downside))
        if downside_std == 0:
            return 0.0
        return float(np.mean(returns) / downside_std * math.sqrt(self.bars_per_year))

    def _calc_max_drawdown(self, equity: np.ndarray) -> tuple:
        if len(equity) < 2:
            return 0.0, 0
        peak = equity[0]
        max_dd = 0.0
        max_dd_duration = 0
        current_dd_start = 0

        for i, eq in enumerate(equity):
            if eq > peak:
                peak = eq
                current_dd_start = i
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = i - current_dd_start

        return max_dd, max_dd_duration

    def _calc_drawdown_curve(self, equity: np.ndarray) -> List[float]:
        if len(equity) < 2:
            return [0.0]
        peak = equity[0]
        dd_curve = []
        for eq in equity:
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0
            dd_curve.append(dd)
        return dd_curve

    def _max_consecutive(self, mask: np.ndarray) -> int:
        if len(mask) == 0:
            return 0
        max_run = 0
        current_run = 0
        for val in mask:
            if val:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0
        return max_run
