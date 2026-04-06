"""
SIQE V3 - State Provider

Provides real-time trading state for the Telegram bot by querying existing
infrastructure (DuckDB + optional live_runner connection).
"""
import logging
import os
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timezone
from dataclasses import asdict

from alerts.formatters import TradingState

logger = logging.getLogger(__name__)


class StateProvider:
    """
    Provides TradingState from existing infrastructure.
    
    Data sources (in priority order):
    1. live_runner.state_provider() - if running (real-time)
    2. DuckDB queries via StateManager - always available
    3. Default TradingState() - fallback
    """
    
    def __init__(
        self,
        db_path: str = "./data/siqe.db",
        live_runner_callback: Optional[Callable[[], TradingState]] = None,
    ):
        self.db_path = db_path
        self.live_runner_callback = live_runner_callback
        self._duckdb = None
        self._connection = None
        self._initialized = False
        
    def initialize(self) -> bool:
        """Initialize DuckDB connection."""
        try:
            import duckdb
            self._duckdb = duckdb
            if os.path.exists(self.db_path):
                self._connection = duckdb.connect(self.db_path, read_only=True)
                self._initialized = True
                logger.info(f"StateProvider initialized with {self.db_path}")
                return True
            else:
                logger.warning(f"Database not found: {self.db_path}")
                return False
        except ImportError:
            logger.warning("DuckDB not installed - using fallback only")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize StateProvider: {e}")
            return False
    
    def get_state(self) -> TradingState:
        """
        Get current TradingState from available infrastructure.
        
        Priority: live_runner > DuckDB > Default
        """
        state = TradingState(symbol='BTCUSDT', mode='PAPER')
        
        if self.live_runner_callback:
            try:
                live_state = self.live_runner_callback()
                if live_state:
                    return live_state
            except Exception as e:
                logger.debug(f"live_runner callback failed: {e}")
        
        if self._initialized and self._connection:
            try:
                self._update_from_db(state)
            except Exception as e:
                logger.warning(f"DB query failed: {e}")
        
        return state
    
    def _update_from_db(self, state: TradingState) -> None:
        """Update TradingState from DuckDB queries."""
        conn = self._connection
        
        try:
            result = conn.execute("""
                SELECT 
                    COALESCE(SUM(pnl), 0) as daily_pnl,
                    COUNT(*) as trade_count
                FROM trades
                WHERE date(timestamp) = date('now')
            """).fetchone()
            if result:
                state.daily_pnl = result[0] or 0.0
                state.total_trades = result[1] or 0
        except Exception as e:
            logger.debug(f"Daily P&L query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT 
                    COALESCE(SUM(pnl), 0) as weekly_pnl
                FROM trades
                WHERE timestamp >= timestamp 'now' - interval '7 days'
            """).fetchone()
            if result:
                state.weekly_pnl = result[0] or 0.0
        except Exception as e:
            logger.debug(f"Weekly P&L query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT 
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing
                FROM trades
            """).fetchone()
            if result:
                state.total_pnl = result[0] or 0.0
                state.winning_trades = result[2] or 0
                state.losing_trades = result[3] or 0
                if (result[1] or 0) > 0:
                    state.win_rate = (result[2] or 0) / (result[1] or 1)
        except Exception as e:
            logger.debug(f"Total P&L query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT 
                    signal_type,
                    COUNT(*) as count,
                    AVG(ev_score) as avg_ev
                FROM trades
                WHERE timestamp >= timestamp 'now' - interval '1 hour'
                GROUP BY signal_type
                ORDER BY count DESC
                LIMIT 1
            """).fetchone()
            if result:
                state.signal_direction = result[0] or "NEUTRAL"
                state.signal_strength = result[2] or 0.0
        except Exception as e:
            logger.debug(f"Signal query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT MAX(price) as high, MIN(price) as low
                FROM trades
                WHERE timestamp >= timestamp 'now' - interval '24 hours'
            """).fetchone()
            if result and result[0] and result[1]:
                if result[0] > 0:
                    state.current_volatility = (result[0] - result[1]) / result[0]
        except Exception as e:
            logger.debug(f"Volatility query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT 
                    symbol,
                    SUM(quantity) as total_qty,
                    AVG(price) as avg_price,
                    MAX(timestamp) as last_time
                FROM trades
                WHERE status = 'OPEN'
                GROUP BY symbol
                ORDER BY last_time DESC
                LIMIT 1
            """).fetchone()
            if result:
                state.symbol = result[0] or 'BTCUSDT'
                if result[1]:
                    state.position_size = abs(result[1])
                    state.position_side = "LONG" if result[1] > 0 else "SHORT"
                    state.entry_price = result[2] or 0.0
        except Exception as e:
            logger.debug(f"Position query failed: {e}")
        
        try:
            result = conn.execute("""
                SELECT 
                    signal_type as regime,
                    COUNT(*) as signals
                FROM trades
                WHERE timestamp >= timestamp 'now' - interval '24 hours'
                GROUP BY signal_type
                ORDER BY signals DESC
                LIMIT 1
            """).fetchone()
            if result:
                regime_map = {
                    "LONG": "BULL",
                    "SHORT": "BEAR", 
                }
                state.regime = regime_map.get(result[0], "UNKNOWN")
                state.regime_confidence = min(1.0, result[1] / 10)
        except Exception as e:
            logger.debug(f"Regime query failed: {e}")
        
        # Get performance metrics
        try:
            perf = self.get_performance_metrics()
            state.sharpe_ratio = perf.get("sharpe_ratio", 0.0)
            state.profit_factor = perf.get("profit_factor", 0.0)
            state.avg_win = perf.get("avg_win", 0.0)
            state.avg_loss = perf.get("avg_loss", 0.0)
        except Exception as e:
            logger.debug(f"Performance metrics query failed: {e}")
        
        # Get signal history for ML
        try:
            self._update_signal_components(state)
        except Exception as e:
            logger.debug(f"Signal components update failed: {e}")
        
        state.last_signal_time = datetime.now(timezone.utc)
    
    def get_recent_trades(self, limit: int = 10) -> list:
        """Get recent trades from database."""
        if not self._initialized:
            return []
        
        try:
            result = self._connection.execute(f"""
                SELECT 
                    id,
                    symbol,
                    signal_type,
                    price,
                    quantity,
                    pnl,
                    timestamp
                FROM trades
                ORDER BY timestamp DESC
                LIMIT {limit}
            """).fetchall()
            
            trades = []
            for row in result:
                trades.append({
                    "id": row[0],
                    "symbol": row[1],
                    "direction": row[2],
                    "price": row[3],
                    "quantity": row[4],
                    "pnl": row[5],
                    "timestamp": row[6].isoformat() if row[6] else None,
                })
            return trades
        except Exception as e:
            logger.warning(f"Failed to get recent trades: {e}")
            return []
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics from database."""
        if not self._initialized:
            return {}
    
    def get_signal_history(self, limit: int = 20) -> list:
        """Get recent signals for ML analysis."""
        if not self._initialized:
            return []
        
        try:
            result = self._connection.execute(f"""
                SELECT 
                    timestamp,
                    signal_type,
                    ev_score,
                    confidence
                FROM trades
                WHERE signal_type IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT {limit}
            """).fetchall()
            
            signals = []
            for row in result:
                signals.append({
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "signal_type": row[1],
                    "ev_score": row[2],
                    "confidence": row[3],
                })
            return signals
        except Exception as e:
            logger.warning(f"Failed to get signal history: {e}")
            return []
    
    def _update_signal_components(self, state: TradingState) -> None:
        """Update signal components for ML view."""
        try:
            result = self._connection.execute("""
                SELECT 
                    signal_type,
                    COUNT(*) as count,
                    AVG(ev_score) as avg_ev
                FROM trades
                WHERE timestamp >= timestamp 'now' - interval '1 hour'
                GROUP BY signal_type
                ORDER BY count DESC
                LIMIT 3
            """).fetchall()
            
            for i, row in enumerate(result):
                signal_type = row[0] or "NEUTRAL"
                if i == 0:
                    state.signal_momentum = row[2] or 0.0
                elif i == 1:
                    state.signal_mean_reversion = row[2] or 0.0
                elif i == 2:
                    state.signal_volatility_breakout = row[2] or 0.0
        except Exception as e:
            logger.debug(f"Signal components query failed: {e}")
        
        state.recent_signals = self.get_signal_history(limit=20)
        
        try:
            result = self._connection.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing,
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(AVG(pnl), 0) as avg_pnl,
                    COALESCE(MAX(pnl), 0) as best_trade,
                    COALESCE(MIN(pnl), 0) as worst_trade,
                    COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0) as total_wins,
                    COALESCE(SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 0) as total_losses
                FROM trades
            """).fetchone()
            
            if result:
                total_wins = result[7] or 0.0
                total_losses = result[8] or 0.0
                profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
                
                winning_trades = result[1] or 0
                losing_trades = result[2] or 0
                avg_win = total_wins / winning_trades if winning_trades > 0 else 0.0
                avg_loss = total_losses / losing_trades if losing_trades > 0 else 0.0
                
                # Calculate Sharpe ratio from trade returns
                sharpe_ratio = 0.0
                try:
                    returns_result = self._connection.execute("""
                        SELECT pnl FROM trades ORDER BY timestamp
                    """).fetchall()
                    if len(returns_result) > 1:
                        pnls = [r[0] for r in returns_result if r[0] is not None]
                        if pnls:
                            import numpy as np
                            mean_return = np.mean(pnls)
                            std_return = np.std(pnls)
                            if std_return > 0:
                                sharpe_ratio = (mean_return / std_return) * np.sqrt(252)
                except Exception:
                    pass
                
                return {
                    "total_trades": result[0] or 0,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "total_pnl": result[3] or 0.0,
                    "avg_pnl": result[4] or 0.0,
                    "best_trade": result[5] or 0.0,
                    "worst_trade": result[6] or 0.0,
                    "sharpe_ratio": sharpe_ratio,
                    "profit_factor": profit_factor,
                    "avg_win": avg_win,
                    "avg_loss": avg_loss,
                }
        except Exception as e:
            logger.warning(f"Failed to get performance metrics: {e}")
        
        return {}
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            logger.info("StateProvider connection closed")


_state_provider_instance: Optional[StateProvider] = None


def get_state_provider(
    db_path: str = "./data/siqe.db",
    live_runner_callback: Optional[Callable[[], TradingState]] = None,
) -> StateProvider:
    """Get or create StateProvider singleton."""
    global _state_provider_instance
    
    if _state_provider_instance is None:
        _state_provider_instance = StateProvider(
            db_path=db_path,
            live_runner_callback=live_runner_callback,
        )
        _state_provider_instance.initialize()
    
    return _state_provider_instance
