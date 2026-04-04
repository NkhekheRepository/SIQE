"""
Memory Module
Handles persistence of system state and trade history using DuckDB
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
import json
import os

logger = logging.getLogger(__name__)


class StateManager:
    """Manages system state persistence and recovery."""
    
    def __init__(self, settings):
        self.settings = settings
        self.is_initialized = False
        self.db_path = settings.get("db_path", "./data/siqe.db")
        self.connection = None
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
    async def initialize(self) -> bool:
        """Initialize database connection and create tables."""
        try:
            logger.info("Initializing State Manager...")
            
            # Import duckdb here to handle potential import errors gracefully
            try:
                import duckdb
                self.connection = duckdb.connect(self.db_path)
            except ImportError:
                logger.error("DuckDB not installed. Please install duckdb package.")
                return False
            except Exception as e:
                logger.error(f"Failed to connect to DuckDB: {e}")
                return False
            
            # Create tables if they don't exist
            await self._create_tables()
            
            self.is_initialized = True
            logger.info(f"State Manager initialized with database at {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize State Manager: {e}")
            return False
    
    async def _create_tables(self):
        """Create necessary database tables."""
        try:
            # Trades table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id VARCHAR PRIMARY KEY,
                    symbol VARCHAR,
                    signal_type VARCHAR,
                    price DOUBLE,
                    quantity DOUBLE,
                    timestamp TIMESTAMP,
                    strategy VARCHAR,
                    ev_score DOUBLE,
                    pnl DOUBLE,
                    status VARCHAR,
                    execution_details JSON
                )
            """)
            
            # Performance table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS performance (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    win_rate DOUBLE,
                    total_pnl DOUBLE,
                    daily_pnl DOUBLE,
                    max_drawdown DOUBLE,
                    sharpe_ratio DOUBLE,
                    metadata JSON
                )
            """)
            
            # Strategy stats table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS strategy_stats (
                    id VARCHAR PRIMARY KEY,
                    strategy_name VARCHAR,
                    symbol VARCHAR,
                    signal_type VARCHAR,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    win_rate DOUBLE,
                    avg_pnl DOUBLE,
                    best_trade DOUBLE,
                    worst_trade DOUBLE,
                    last_updated TIMESTAMP,
                    metadata JSON
                )
            """)
            
            # System state table
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    system_state VARCHAR,
                    meta_override_active BOOLEAN,
                    meta_override_reason VARCHAR,
                    risk_metrics JSON,
                    performance_snapshot JSON
                )
            """)
            
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    async def save_trade(self, trade_data) -> bool:
        """Save a trade record to the database. Accepts dict or ExecutionResult."""
        if not self.is_initialized:
            return False

        try:
            if hasattr(trade_data, "execution_id"):
                data = {
                    "execution_id": trade_data.execution_id,
                    "symbol": trade_data.symbol,
                    "signal_type": trade_data.signal_type.value,
                    "price": trade_data.filled_price,
                    "quantity": trade_data.filled_quantity,
                    "timestamp": self.clock.now if hasattr(self, "clock") else datetime.now(timezone.utc).isoformat(),
                    "strategy": trade_data.strategy,
                    "ev_score": 0.0,
                    "pnl": 0.0,
                    "status": trade_data.status.value,
                    "execution_details": {"error": trade_data.error, "slippage": trade_data.slippage},
                }
            else:
                data = trade_data

            trade_id = data.get("execution_id", f"trade_{datetime.now(timezone.utc).timestamp()}")

            self.connection.execute("""
                INSERT OR IGNORE INTO trades (
                    id, symbol, signal_type, price, quantity, timestamp,
                    strategy, ev_score, pnl, status, execution_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                trade_id,
                data.get("symbol"),
                data.get("signal_type"),
                data.get("price", 0.0),
                data.get("quantity", 0.0),
                data.get("timestamp"),
                data.get("strategy", "unknown"),
                data.get("ev_score", 0.0),
                data.get("pnl", 0.0),
                data.get("status", "UNKNOWN"),
                json.dumps(data.get("execution_details", {}))
            ])

            logger.debug(f"Saved trade {trade_id} to database")
            return True

        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return False
    
    async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades from the database."""
        if not self.is_initialized:
            return []
        
        try:
            result = self.connection.execute("""
                SELECT * FROM trades 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, [limit]).fetchall()
            
            # Convert to list of dictionaries
            columns = [desc[0] for desc in self.connection.description]
            trades = []
            for row in result:
                trade = dict(zip(columns, row))
                # Parse JSON fields
                if trade.get('execution_details'):
                    try:
                        trade['execution_details'] = json.loads(trade['execution_details'])
                    except:
                        trade['execution_details'] = {}
                trades.append(trade)
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    async def save_performance_snapshot(self, performance_data: Dict[str, Any]) -> bool:
        """Save performance snapshot to database."""
        if not self.is_initialized:
            return False
        
        try:
            snapshot_id = f"perf_{datetime.now(timezone.utc).timestamp()}"
            
            self.connection.execute("""
                INSERT INTO performance (
                    id, timestamp, total_trades, winning_trades, losing_trades,
                    win_rate, total_pnl, daily_pnl, max_drawdown, sharpe_ratio, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                snapshot_id,
                performance_data.get("timestamp"),
                performance_data.get("total_trades", 0),
                performance_data.get("winning_trades", 0),
                performance_data.get("losing_trades", 0),
                performance_data.get("win_rate", 0.0),
                performance_data.get("total_pnl", 0.0),
                performance_data.get("daily_pnl", 0.0),
                performance_data.get("max_drawdown", 0.0),
                performance_data.get("sharpe_ratio", 0.0),
                json.dumps(performance_data.get("metadata", {}))
            ])
            
            logger.debug("Saved performance snapshot")
            return True
            
        except Exception as e:
            logger.error(f"Error saving performance snapshot: {e}")
            return False
    
    async def save_strategy_stats(self, strategy_data: Dict[str, Any]) -> bool:
        """Save strategy statistics to database."""
        if not self.is_initialized:
            return False
        
        try:
            # Create unique ID for strategy/symbol/signal_type combination
            strategy_id = f"{strategy_data.get('strategy_name', 'unknown')}_{strategy_data.get('symbol', 'unknown')}_{strategy_data.get('signal_type', 'unknown')}"
            
            self.connection.execute("""
                INSERT OR REPLACE INTO strategy_stats (
                    id, strategy_name, symbol, signal_type, total_trades,
                    winning_trades, losing_trades, win_rate, avg_pnl,
                    best_trade, worst_trade, last_updated, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                strategy_id,
                strategy_data.get("strategy_name", "unknown"),
                strategy_data.get("symbol", "unknown"),
                strategy_data.get("signal_type", "unknown"),
                strategy_data.get("total_trades", 0),
                strategy_data.get("winning_trades", 0),
                strategy_data.get("losing_trades", 0),
                strategy_data.get("win_rate", 0.0),
                strategy_data.get("avg_pnl", 0.0),
                strategy_data.get("best_trade", 0.0),
                strategy_data.get("worst_trade", 0.0),
                strategy_data.get("last_updated", datetime.now(timezone.utc).isoformat()),
                json.dumps(strategy_data.get("metadata", {}))
            ])
            
            logger.debug(f"Saved strategy stats for {strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving strategy stats: {e}")
            return False
    
    async def save_system_state(self, state_data: Dict[str, Any]) -> bool:
        """Save current system state to database."""
        if not self.is_initialized:
            return False
        
        try:
            state_id = f"state_{datetime.now(timezone.utc).timestamp()}"
            
            self.connection.execute("""
                INSERT INTO system_state (
                    id, timestamp, system_state, meta_override_active,
                    meta_override_reason, risk_metrics, performance_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                state_id,
                state_data.get("timestamp"),
                state_data.get("system_state", "UNKNOWN"),
                state_data.get("meta_override_active", False),
                state_data.get("meta_override_reason", ""),
                json.dumps(state_data.get("risk_metrics", {})),
                json.dumps(state_data.get("performance_snapshot", {}))
            ])
            
            logger.debug("Saved system state")
            return True
            
        except Exception as e:
            logger.error(f"Error saving system state: {e}")
            return False
    
    async def load_latest_state(self) -> Optional[Dict[str, Any]]:
        """Load the most recent system state from database."""
        if not self.is_initialized:
            return None
        
        try:
            result = self.connection.execute("""
                SELECT * FROM system_state 
                ORDER BY timestamp DESC 
                LIMIT 1
            """).fetchone()
            
            if not result:
                logger.info("No previous system state found")
                return None
            
            # Convert to dictionary
            columns = [desc[0] for desc in self.connection.description]
            state = dict(zip(columns, result))
            
            # Parse JSON fields
            for json_field in ['risk_metrics', 'performance_snapshot']:
                if state.get(json_field):
                    try:
                        state[json_field] = json.loads(state[json_field])
                    except:
                        state[json_field] = {}
            
            logger.info(f"Loaded system state from {state.get('timestamp')}")
            return state
            
        except Exception as e:
            logger.error(f"Error loading system state: {e}")
            return None
    
    async def get_trade_statistics(self) -> Dict[str, Any]:
        """Get overall trade statistics from database."""
        if not self.is_initialized:
            return {}
        
        try:
            # Get basic trade stats
            result = self.connection.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss,
                    SUM(pnl) as total_pnl
                FROM trades
            """).fetchone()
            
            if not result:
                return {}
            
            columns = [desc[0] for desc in self.connection.description]
            stats = dict(zip(columns, result))
            
            # Calculate win rate
            total = stats['total_trades'] or 0
            winning = stats['winning_trades'] or 0
            stats['win_rate'] = winning / total if total > 0 else 0.0
            
            # Calculate profit factor
            avg_win = abs(stats['avg_win'] or 0)
            avg_loss = abs(stats['avg_loss'] or 0)
            stats['profit_factor'] = (avg_win * winning) / (avg_loss * (total - winning)) if avg_loss > 0 and (total - winning) > 0 else 0.0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting trade statistics: {e}")
            return {}
    
    async def get_strategy_performance(self) -> List[Dict[str, Any]]:
        """Get performance statistics for all strategies."""
        if not self.is_initialized:
            return []
        
        try:
            result = self.connection.execute("""
                SELECT * FROM strategy_stats 
                ORDER BY last_updated DESC
            """).fetchall()
            
            # Convert to list of dictionaries
            columns = [desc[0] for desc in self.connection.description]
            strategies = []
            for row in result:
                strategy = dict(zip(columns, row))
                # Parse JSON fields
                if strategy.get('metadata'):
                    try:
                        strategy['metadata'] = json.loads(strategy['metadata'])
                    except:
                        strategy['metadata'] = {}
                strategies.append(strategy)
            
            return strategies
            
        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}")
            return []
    
    async def initialize_state(self) -> bool:
        """Initialize or load system state."""
        try:
            previous_state = await self.load_latest_state()
            if previous_state:
                logger.info("Loaded previous system state")
            else:
                logger.info("No previous state found, starting fresh")

            return True

        except Exception as e:
            logger.error(f"Error initializing state: {e}")
            return False

    async def restore_state_to_components(self, risk_engine=None, strategy_engine=None,
                                          meta_harness=None) -> bool:
        """Restore persisted state to system components."""
        try:
            previous_state = await self.load_latest_state()
            if not previous_state:
                logger.info("No previous state to restore")
                return True

            risk_metrics = previous_state.get("risk_metrics", {})
            if risk_metrics and risk_engine:
                if "current_equity" in risk_metrics:
                    risk_engine.current_equity = risk_metrics["current_equity"]
                if "peak_equity" in risk_metrics:
                    risk_engine.peak_equity = risk_metrics["peak_equity"]
                if "daily_pnl" in risk_metrics:
                    risk_engine.daily_pnl = risk_metrics["daily_pnl"]
                if "consecutive_losses" in risk_metrics:
                    risk_engine.consecutive_losses = risk_metrics["consecutive_losses"]
                logger.info(f"Restored risk state: equity={risk_engine.current_equity:.2f}, "
                           f"drawdown={risk_engine.max_drawdown:.2%}")

            perf_snapshot = previous_state.get("performance_snapshot", {})
            if perf_snapshot and strategy_engine:
                logger.info(f"Restored performance snapshot: {perf_snapshot.get('total_trades', 0)} trades")

            logger.info("State restoration to components complete")
            return True

        except Exception as e:
            logger.error(f"Error restoring state to components: {e}")
            return False
    
    async def load_state(self) -> bool:
        """Load system state for recovery."""
        return await self.initialize_state()
    
    async def save_state(self, risk_engine=None, meta_harness=None) -> bool:
        """Save current system state."""
        try:
            risk_metrics = {}
            if risk_engine:
                risk_metrics = {
                    "current_equity": risk_engine.current_equity,
                    "peak_equity": risk_engine.peak_equity,
                    "daily_pnl": risk_engine.daily_pnl,
                    "consecutive_losses": risk_engine.consecutive_losses,
                }

            system_state = "UNKNOWN"
            override_active = False
            override_reason = ""
            if meta_harness:
                system_state = meta_harness.system_state.value if hasattr(meta_harness, 'system_state') else "UNKNOWN"
                override_active = meta_harness.override_active
                override_reason = meta_harness.override_reason

            state_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_state": system_state,
                "meta_override_active": override_active,
                "meta_override_reason": override_reason,
                "risk_metrics": risk_metrics,
                "performance_snapshot": await self.get_trade_statistics()
            }

            return await self.save_system_state(state_data)

        except Exception as e:
            logger.error(f"Error saving state: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown state manager and close database connection."""
        logger.info("Shutting down State Manager...")
        
        if self.connection:
            self.connection.close()
            self.connection = None
        
        self.is_initialized = False
        logger.info("State Manager shutdown complete")
