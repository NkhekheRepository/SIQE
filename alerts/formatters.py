"""
SIQE V3 - Formatters

Unified message formatting for Telegram bot views across all three perspectives.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TradingState:
    """Trading state snapshot for formatting."""
    mode: str = "PAPER"  # PAPER, LIVE, BACKTEST
    symbol: str = "BTCUSDT"
    regime: str = "UNKNOWN"
    regime_confidence: float = 0.0
    signal_direction: str = "NEUTRAL"  # LONG, SHORT, NEUTRAL
    signal_strength: float = 0.0
    position_side: str = "NONE"  # LONG, SHORT, NONE
    position_size: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    leverage: int = 10
    
    # P&L metrics
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    weekly_pnl: float = 0.0
    weekly_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    
    # Performance metrics
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Trade stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Strategy signals
    signal_momentum: float = 0.0
    signal_mean_reversion: float = 0.0
    signal_volatility_breakout: float = 0.0
    
    # Params
    stop_multiplier: float = 0.5
    tp_multiplier: float = 3.0
    prefer_direction: str = "BOTH"
    
    # Timing
    last_trade_time: Optional[datetime] = None
    last_signal_time: Optional[datetime] = None
    uptime_seconds: int = 0
    
    # Status
    is_trading_active: bool = True
    next_check_seconds: int = 60
    
    # Volatility
    current_volatility: float = 0.0
    
    # Account info
    account_balance: float = 10000.0
    available_balance: float = 10000.0
    
    # Recent trades
    recent_trades: List[Dict[str, Any]] = None
    
    # Signal history for ML analysis
    recent_signals: List[Dict[str, Any]] = None
    signal_momentum: float = 0.0
    signal_mean_reversion: float = 0.0
    signal_volatility_breakout: float = 0.0
    
    # MetaHarness (system wrapper) fields
    system_state: str = "INITIALIZING"
    override_active: bool = False
    override_reason: str = ""
    recent_pnls_count: int = 0
    kill_conditions: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.recent_trades is None:
            self.recent_trades = []
        if self.recent_signals is None:
            self.recent_signals = []
        if self.kill_conditions is None:
            self.kill_conditions = {}


class DashboardFormatter:
    """Format trading state for Telegram views."""
    
    @staticmethod
    def format_header(mode: str = "PAPER", symbol: str = "BTCUSDT") -> str:
        """Format main header."""
        mode_emoji = "🧪" if mode == "PAPER" else "📡"
        return f"SIQE V3 {mode_emoji} {mode} • {symbol}"
    
    @staticmethod
    def format_dashboard(state: TradingState) -> str:
        """Format main dashboard view."""
        # System health indicator
        system_emoji = "🟢" if state.system_state == "NORMAL" else "🟡" if state.system_state == "DEGRADED" else "🔴"
        override_indicator = " ⚠️" if state.override_active else ""
        
        header = DashboardFormatter.format_header(
            mode="PAPER" if state.mode == "PAPER" else "LIVE",
            symbol=state.symbol
        )
        
        regime_emoji = "🟢" if state.regime == "BULL" else "🔴" if state.regime == "BEAR" else "🟡"
        signal_emoji = "⬆️" if state.signal_direction == "LONG" else "⬇️" if state.signal_direction == "SHORT" else "➡️"
        
        pnl_emoji = "🟢" if state.daily_pnl >= 0 else "🔴"
        pnl_sign = "+" if state.daily_pnl >= 0 else ""
        
        unreal_emoji = "🟢" if state.unrealized_pnl >= 0 else "🔴"
        unreal_sign = "+" if state.unrealized_pnl >= 0 else ""
        
        week_emoji = "🟢" if state.weekly_pnl >= 0 else "🔴"
        week_sign = "+" if state.weekly_pnl >= 0 else ""
        
        net_emoji = "🟢" if (state.unrealized_pnl + state.realized_pnl) >= 0 else "🔴"
        net_sign = "+" if (state.unrealized_pnl + state.realized_pnl) >= 0 else ""
        
        realized_emoji = "🟢" if state.realized_pnl >= 0 else "🔴"
        realized_sign = "+" if state.realized_pnl >= 0 else ""
        
        active_emoji = "▶️" if state.is_trading_active else "⏹️"
        
        lines = [
            f"<b>{header}</b> {system_emoji}{override_indicator}",
            "─" * 40,
            f"<b>Regime:</b> {regime_emoji} {state.regime} ({state.regime_confidence:.0%})",
            f"<b>Signal:</b> {signal_emoji} {state.signal_direction} ({state.signal_strength:.2f})",
            f"<b>Position:</b> {state.position_side} {state.position_size} @ ${state.entry_price:,.0f}",
            f"<b>Status:</b> {active_emoji} {'Trading' if state.is_trading_active else 'Stopped'} | Next: {state.next_check_seconds}s",
            "─" * 40,
            f"<b>Balance:</b> ${state.account_balance:,.2f} (Avail: ${state.available_balance:,.2f})",
            f"<b>Unrealized:</b> {unreal_emoji} {unreal_sign}${state.unrealized_pnl:.2f}",
            f"<b>Realized:</b> {realized_emoji} {realized_sign}${state.realized_pnl:.2f}",
            f"<b>Net P&L:</b> {net_emoji} {net_sign}${state.unrealized_pnl + state.realized_pnl:.2f}",
            "─" * 40,
            f"<b>Today:</b> {pnl_emoji} {pnl_sign}${state.daily_pnl:.2f} ({pnl_sign}{state.daily_pnl_pct:.2%}) [{state.winning_trades}W/{state.losing_trades}L]",
            f"<b>This Week:</b> {week_emoji} {week_sign}${state.weekly_pnl:.2f} ({week_sign}{state.weekly_pnl_pct:.2%})",
            f"<b>All Time:</b> {pnl_sign}${state.total_pnl:.2f} ({pnl_sign}{state.total_pnl_pct:.2%}) [{state.total_trades} trades]",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def format_quant_view(state: TradingState) -> str:
        """Format Principal Quant Developer view."""
        regime_emoji = "🟢" if state.regime == "BULL" else "🔴" if state.regime == "BEAR" else "🟡"
        signal_emoji = "⬆️" if state.signal_direction == "LONG" else "⬇️" if state.signal_direction == "SHORT" else "➡️"
        
        active_emoji = "▶️" if state.is_trading_active else "⏹️"
        
        last_trade = "Never"
        if state.last_trade_time:
            last_trade = state.last_trade_time.strftime("%H:%M UTC")
        
        lines = [
            "📊 PRINCIPLE QUANT DEVELOPER VIEW",
            "═" * 40,
            f"<b>Mode:</b> {state.mode}",
            f"<b>Status:</b> {active_emoji} {'ACTIVE' if state.is_trading_active else 'STOPPED'}",
            "─" * 40,
            f"<b>Regime:</b> {regime_emoji} {state.regime}",
            f"<b>Confidence:</b> {state.regime_confidence:.0%}",
            f"<b>Volatility:</b> {state.current_volatility:.2%}",
            "─" * 40,
            f"<b>Signal:</b> {signal_emoji} {state.signal_direction}",
            f"<b>Strength:</b> {state.signal_strength:.2f}",
            "─" * 40,
            f"<b>Position:</b> {state.position_side}",
            f"<b>Size:</b> {state.position_size} contracts",
            f"<b>Entry:</b> ${state.entry_price:,.2f}",
            f"<b>Unrealized P&L:</b> ${state.unrealized_pnl:.2f}",
            f"<b>Realized P&L:</b> ${state.realized_pnl:.2f}",
            f"<b>Net P&L:</b> ${state.unrealized_pnl + state.realized_pnl:.2f}",
            "─" * 40,
            f"<b>Stop Multiplier:</b> {state.stop_multiplier}x ATR",
            f"<b>TP Multiplier:</b> {state.tp_multiplier}x ATR",
            f"<b>Prefer Direction:</b> {state.prefer_direction}",
            "─" * 40,
            f"<b>Last Trade:</b> {last_trade}",
            f"<b>Uptime:</b> {state.uptime_seconds // 3600}h {(state.uptime_seconds % 3600) // 60}m",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def format_hedge_fund_view(state: TradingState) -> str:
        """Format Senior Hedge Fund Manager view."""
        daily_emoji = "🟢" if state.daily_pnl >= 0 else "🔴"
        total_emoji = "🟢" if (state.unrealized_pnl + state.realized_pnl) >= 0 else "🔴"
        unreal_emoji = "🟢" if state.unrealized_pnl >= 0 else "🔴"
        realized_emoji = "🟢" if state.realized_pnl >= 0 else "🔴"
        
        daily_sign = "+" if state.daily_pnl >= 0 else ""
        unreal_sign = "+" if state.unrealized_pnl >= 0 else ""
        realized_sign = "+" if state.realized_pnl >= 0 else ""
        net_sign = "+" if (state.unrealized_pnl + state.realized_pnl) >= 0 else ""
        
        net_pnl = state.unrealized_pnl + state.realized_pnl
        
        lines = [
            "💰 SENIOR HEDGE FUND MANAGER VIEW",
            "═" * 40,
            f"<b>Account Balance:</b> ${state.account_balance:,.2f}",
            "─" * 40,
            f"<b>Unrealized P&L:</b> {unreal_emoji} {unreal_sign}${state.unrealized_pnl:.2f}",
            f"<b>Realized P&L:</b> {realized_emoji} {realized_sign}${state.realized_pnl:.2f}",
            f"<b>Net P&L:</b> {total_emoji} {net_sign}${net_pnl:.2f}",
            "─" * 40,
            f"<b>Today's P&L:</b> {daily_emoji} {daily_sign}${state.daily_pnl:.2f}",
            "─" * 40,
            f"<b>Max Drawdown:</b> 🔴 {state.max_drawdown:.2%}",
            f"<b>Sharpe Ratio:</b> {state.sharpe_ratio:.2f}",
            f"<b>Win Rate:</b> {state.win_rate:.1%} ({state.winning_trades}W/{state.losing_trades}L)",
            "─" * 40,
            f"<b>Total Trades:</b> {state.total_trades}",
            f"<b>Avg Win:</b> ${state.avg_win:.2f}",
            f"<b>Avg Loss:</b> ${state.avg_loss:.2f}",
            f"<b>Profit Factor:</b> {state.profit_factor:.2f}",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def format_ml_engineer_view(state: TradingState) -> str:
        """Format AI/ML Engineer view."""
        regime_emoji = "🟢" if state.regime == "BULL" else "🔴" if state.regime == "BEAR" else "🟡"
        
        def signal_bar(value: float) -> str:
            filled = int(value * 10)
            return "█" * filled + "░" * (10 - filled)
        
        lines = [
            "🤖 AI/ML ENGINEER VIEW",
            "═" * 40,
            f"<b>Market Regime:</b> {regime_emoji} {state.regime}",
            f"<b>Confidence:</b> {state.regime_confidence:.0%}",
            f"<b>Volatility:</b> {state.current_volatility:.2%}",
            "─" * 40,
            f"<b>Aggregated Signal:</b> {state.signal_direction}",
            f"<b>Strength:</b> {state.signal_strength:.2f} {signal_bar(state.signal_strength)}",
            "─" * 40,
            f"<b>Strategy Signals:</b>",
            f"  momentum:        {state.signal_momentum:.2f} {signal_bar(state.signal_momentum)}",
            f"  mean_reversion:  {state.signal_mean_reversion:.2f} {signal_bar(state.signal_mean_reversion)}",
            f"  volatility_breakout: {state.signal_volatility_breakout:.2f} {signal_bar(state.signal_volatility_breakout)}",
            "─" * 40,
            f"<b>Decision Parameters:</b>",
            f"  stop_multiplier:    {state.stop_multiplier}",
            f"  tp_multiplier:      {state.tp_multiplier}",
            f"  prefer_direction:  {state.prefer_direction}",
        ]
        
        if state.last_signal_time:
            lines.append(f"  last_update: {state.last_signal_time.strftime('%H:%M:%S UTC')}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_positions(state: TradingState) -> str:
        """Format open positions view."""
        if state.position_side == "NONE" or state.position_size == 0:
            return "📭 No Open Positions\n" + "─" * 40 + "\nNo active positions.\n\nWaiting for signal..."
        
        pnl_emoji = "🟢" if state.unrealized_pnl >= 0 else "🔴"
        pnl_sign = "+" if state.unrealized_pnl >= 0 else ""
        
        lines = [
            "📊 Open Positions",
            "═" * 40,
            f"<b>Side:</b> {state.position_side}",
            f"<b>Size:</b> {state.position_size} contracts",
            f"<b>Entry:</b> ${state.entry_price:,.2f}",
            f"<b>Unrealized P&L:</b> {pnl_emoji} {pnl_sign}${state.unrealized_pnl:.2f}",
            f"<b>Leverage:</b> {state.leverage}x",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def format_params(state: TradingState) -> str:
        """Format strategy parameters."""
        lines = [
            "⚙️ PRINCIPLE SOFTWARE ARCHITECT VIEW",
            "═" * 40,
            f"<b>Stop Multiplier:</b> {state.stop_multiplier}x ATR",
            f"<b>Take Profit:</b> {state.tp_multiplier}x ATR",
            f"<b>Prefer Direction:</b> {state.prefer_direction}",
            f"<b>Leverage:</b> {state.leverage}x",
            "─" * 40,
            f"<b>Regime:</b> {state.regime}",
            f"<b>Confidence Threshold:</b> 80%",
        ]
        
        return "\n".join(lines)
    
    @staticmethod
    def format_meta_view(state: TradingState) -> str:
        """Format MetaHarness system wrapper view for PRINCIPLE SOFTWARE ARCHITECT."""
        state_emoji = "🟢" if state.system_state == "NORMAL" else "🟡" if state.system_state == "DEGRADED" else "🔴"
        override_emoji = "⚠️" if state.override_active else "✅"
        
        lines = [
            "🔧 PRINCIPLE SOFTWARE ARCHITECT VIEW",
            "═" * 40,
            f"<b>System State:</b> {state_emoji} {state.system_state}",
            f"<b>Override Active:</b> {override_emoji} {'YES' if state.override_active else 'NO'}",
        ]
        
        if state.override_active and state.override_reason:
            lines.append(f"<b>Reason:</b> {state.override_reason}")
        
        lines.extend([
            "─" * 40,
            f"<b>Recent P&Ls:</b> {state.recent_pnls_count} stored",
            "─" * 40,
            "<b>Kill Conditions:</b>",
        ])
        
        if state.kill_conditions:
            for key, value in state.kill_conditions.items():
                key_display = key.replace("_", " ").title()
                if isinstance(value, float):
                    lines.append(f"  {key_display}: {value:.2%}")
                else:
                    lines.append(f"  {key_display}: {value}")
        else:
            lines.append("  No kill conditions configured")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_trades(state: TradingState, limit: int = 5) -> str:
        """Format recent trades."""
        if not state.recent_trades:
            return "📊 No Trades Today\n" + "─" * 40 + "\nNo trades executed yet today."
        
        lines = ["📋 Recent Trades", "═" * 40]
        
        for i, trade in enumerate(state.recent_trades[:limit]):
            direction = trade.get("direction", "UNKNOWN")
            direction_emoji = "📈" if direction == "LONG" else "📉"
            pnl = trade.get("pnl", 0)
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            pnl_sign = "+" if pnl >= 0 else ""
            
            exit_reason = trade.get("exit_reason", "N/A")
            duration = trade.get("duration_minutes", 0)
            
            lines.append(
                f"{i+1}. {direction_emoji} {direction} | "
                f"{pnl_emoji} {pnl_sign}${pnl:.2f} | "
                f"{exit_reason} | {duration}m"
            )
        
        return "\n".join(lines)
    
    @staticmethod
    def format_welcome() -> str:
        """Format welcome message."""
        return """👋 <b>Welcome to SIQE V3</b>

Your quantitative trading assistant is ready.

<b>Quick Commands:</b>
/dashboard - Main control panel
/status - System status
/pnl - P&L summary
/signals - Signal diagnostics
/help - All commands

<b>Quick Actions:</b>
/stop - Emergency stop
/starttrading - Resume trading
"""
    
    @staticmethod
    def format_help() -> str:
        """Format help message."""
        return """📖 <b>SIQE V3 Command Reference</b>

 <b>🏛️ Five Perspectives:</b>
 ┌─────────────────────────────────────┐
 │ /status    → PRINCIPLE QUANT DEVELOPER    │
 │ /pnl       → SENIOR HEDGE FUND MANAGER    │
 │ /signals   → AI/ML ENGINEER               │
 │ /dashboard → UX Designer                  │
 │ /params    → PRINCIPLE SOFTWARE ARCHITECT │
 │ /system    → META HARNESS (Wrapper)        │
 └─────────────────────────────────────┘

<b>📊 Views (All Perspectives):</b>
/dashboard      - Main control panel
/status         - Quant developer view (regime, signals, position)
/pnl            - Hedge fund view (P&L, Sharpe, win rate)
/signals        - ML engineer view (signal components)
/signal_history - Recent signals for ML training
/positions      - Open positions
/trades         - Recent trades
/regime         - Market regime detection
/params         - Strategy parameters
/system         - MetaHarness wrapper (system state, kill conditions)

<b>⚡ Actions:</b>
/stop           - Emergency stop trading
/starttrading   - Resume trading
/refresh        - Refresh all data

<b>🔔 Subscriptions:</b>
/subscribe &lt;type&gt;    - Subscribe to alerts
/unsubscribe &lt;type&gt;  - Unsubscribe
/subscriptions         - List subscriptions

<b>Alert Categories:</b>
/subscribe trading  - Trade execution alerts
/subscribe risk     - Risk & circuit breaker alerts
/subscribe signals  - Signal generation alerts
/subscribe regime   - Regime change alerts
/subscribe all     - All alerts
/subscribe none    - Critical only
"""
    
    @staticmethod
    def format_stop_confirmed() -> str:
        """Format stop confirmation."""
        return """⏹️ <b>Trading Stopped</b>

All trading activity has been halted.

Use /starttrading to resume.
"""
    
    @staticmethod
    def format_start_confirmed() -> str:
        """Format start confirmation."""
        return """▶️ <b>Trading Resumed</b>

Trading activity has been resumed.

Use /stop to halt.
"""
    
    @staticmethod
    def format_subscriptions(subscribed: List[str], available: List[str]) -> str:
        """Format subscriptions list."""
        lines = ["🔔 <b>Your Subscriptions</b>", "═" * 40]
        
        if subscribed:
            lines.append("<b>Active:</b>")
            for s in subscribed:
                lines.append(f"  ✅ {s}")
        else:
            lines.append("<b>Active:</b> None")
        
        lines.append("─" * 40)
        lines.append("<b>Available:</b>")
        for a in available:
            checked = "✅" if a in subscribed else "○"
            lines.append(f"  {checked} {a}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_subscribe_success(alert_type: str) -> str:
        """Format subscription success."""
        return f"✅ <b>Subscribed to:</b> {alert_type}"
    
    @staticmethod
    def format_unsubscribe_success(alert_type: str) -> str:
        """Format unsubscription success."""
        return f"✅ <b>Unsubscribed from:</b> {alert_type}"
    
    @staticmethod
    def format_approval_request(action: str, details: str, timeout: int = 300) -> str:
        """Format approval request."""
        return f"""⚠️ <b>Approval Required</b> ({timeout // 60} min)

<b>Action:</b> {action}
<b>Details:</b> {details}

Please confirm or deny.
"""
    
    @staticmethod
    def format_approval_confirmed(action: str) -> str:
        """Format approval confirmed."""
        return f"✅ <b>Approved:</b> {action}"
    
    @staticmethod
    def format_approval_denied(action: str) -> str:
        """Format approval denied."""
        return f"❌ <b>Denied:</b> {action}"
    
    @staticmethod
    def format_error(message: str) -> str:
        """Format error message."""
        return f"❌ <b>Error:</b> {message}"
    
    @staticmethod
    def format_unknown_command() -> str:
        """Format unknown command."""
        return """❓ Unknown command.

Use /help for available commands.
"""
