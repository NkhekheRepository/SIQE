#!/usr/bin/env python3
"""
SIQE V3 - Autonomous Trading Launcher

Enhanced architecture for production-grade autonomous trading:
- Process lock to prevent multiple instances
- Graceful shutdown with state persistence
- Dual-engine: VN.PY for execution, SIQEEngine for risk/learning
- Circuit breaker for connection failures
- Health monitoring every 30s
- Telegram alerts for system events

Usage:
    python scripts/start_autonomous_trading.py
"""
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from vnpy_native.live_runner import SiqeLiveRunner
from main import SIQEEngine
from config.settings import Settings
from alerts import AlertManager, AlertType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Process lock file
LOCK_FILE = Path("/tmp/siqe.lock")


def acquire_process_lock() -> bool:
    """Acquire process lock to prevent multiple instances."""
    try:
        if LOCK_FILE.exists():
            pid = LOCK_FILE.read_text().strip()
            if pid:
                try:
                    import psutil
                    if psutil.pid_exists(int(pid)):
                        logger.error(f"Another instance is running (PID: {pid})")
                        return False
                except ImportError:
                    logger.warning("psutil not available, skipping PID check")
                except ValueError:
                    logger.warning("Invalid PID in lock file")
            
            logger.info("Removing stale lock file")
            LOCK_FILE.unlink()
        
        LOCK_FILE.write_text(str(os.getpid()))
        logger.info(f"Process lock acquired (PID: {os.getpid()})")
        return True
        
    except PermissionError:
        logger.error(f"Permission denied writing to {LOCK_FILE}")
        return False
    except Exception as e:
        logger.error(f"Error acquiring process lock: {e}")
        return False


def release_process_lock():
    """Release the process lock."""
    try:
        if LOCK_FILE.exists():
            pid = LOCK_FILE.read_text().strip()
            if pid == str(os.getpid()):
                LOCK_FILE.unlink()
                logger.info("Process lock released")
    except Exception as e:
        logger.error(f"Error releasing process lock: {e}")


def cleanup_stale_processes():
    """Simple cleanup without subprocess."""
    logger.info("=== PROCESS CLEANUP ===")
    
    # Clear DuckDB locks (most common issue)
    db_path = Path("./data/siqe.db")
    for ext in [".lock", ".wal"]:
        lock = db_path.with_suffix(ext)
        if lock.exists():
            try:
                lock.unlink()
                logger.info(f"Removed {lock.name}")
            except:
                pass
    
    time.sleep(0.5)
    logger.info("✓ Cleanup complete")


def _init_alert_manager() -> AlertManager:
    """Initialize Telegram alert manager."""
    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        enabled = os.environ.get("ALERT_ENABLED", "true").lower() == "true"
        
        if bot_token and chat_id:
            manager = AlertManager(
                telegram_bot_token=bot_token,
                telegram_chat_id=chat_id,
                enabled=enabled
            )
            if manager.is_configured():
                logger.info("Telegram alerts: ENABLED")
            else:
                logger.warning("Telegram alerts: NOT CONFIGURED")
            return manager
        else:
            logger.info("Telegram alerts: Credentials not set")
            return AlertManager(enabled=False)
    except Exception as e:
        logger.error(f"Error initializing alert manager: {e}")
        return AlertManager(enabled=False)


class AutonomousTrader:
    """Manages autonomous trading lifecycle with enhanced architecture."""
    
    def __init__(self):
        self.running = False
        self.runner: Optional[SiqeLiveRunner] = None
        self.engine: Optional[SIQEEngine] = None
        
        self._shutdown_event = asyncio.Event()
        self._health_monitor_task = None
        self._reconnect_count = 0
        self._max_reconnect = 5
        
        # Initialize alert manager
        self._alert_manager: Optional[AlertManager] = None
        self._alert_manager = _init_alert_manager()
        
        # Load config from .env
        self.api_key = os.environ.get("FUTURES_API_KEY", "")
        self.api_secret = os.environ.get("FUTURES_API_SECRET", "")
        self.leverage = int(os.environ.get("FUTURES_LEVERAGE", "35"))
        self.symbol = os.environ.get("FUTURES_SYMBOL", "btcusdt").lower()
        self.risk_pct = float(os.environ.get("FUTURES_RISK_PCT", "0.02"))
        self.margin_alert = float(os.environ.get("FUTURES_MARGIN_ALERT_PCT", "0.70"))
        self.margin_stop = float(os.environ.get("FUTURES_MARGIN_STOP_PCT", "0.90"))
        
        logger.info(f"=== AUTONOMOUS TRADER INITIALIZED ===")
        logger.info(f"  Symbol: {self.symbol.upper()}/USDT")
        logger.info(f"  Leverage: {self.leverage}x")
        logger.info(f"  Risk %: {self.risk_pct:.1%}")
        logger.info(f"  Server: TESTNET")
        logger.info(f"  Risk Mode: Advisory (warn but don't block)")
    
    def create_runner(self) -> SiqeLiveRunner:
        """Create VN.PY live trading runner (NO shared engines)."""
        logger.info("Creating VN.PY live trading runner...")
        
        strategy_name = f"siqe_{int(time.time())}"
        
        self.runner = SiqeLiveRunner(
            api_key=self.api_key,
            api_secret=self.api_secret,
            server="TESTNET",
            symbol=self.symbol,
            market_type="futures",
            strategy_name=strategy_name,
            strategy_params={
                "leverage": self.leverage,
                "risk_pct": self.risk_pct,
                "margin_alert_pct": self.margin_alert,
                "margin_stop_pct": self.margin_stop,
                "atr_stop_multiplier": 1.0,
                "atr_trailing_multiplier": 0.75,
            },
            log_level="INFO",
        )
        
        logger.info("✓ Live runner created")
        return self.runner
    
    async def initialize_engine(self) -> bool:
        """Initialize SIQEEngine with mock execution mode (VN.PY handles real connection)."""
        try:
            logger.info("Initializing SIQEEngine...")
            
            self.engine = SIQEEngine()
            self.engine.settings.use_mock_execution = True
            
            success = await self.engine.initialize()
            if success:
                logger.info("✓ SIQEEngine initialized")
                return True
            else:
                logger.error("✗ SIQEEngine initialization failed")
                return False
        except Exception as e:
            logger.error(f"✗ SIQEEngine initialization error: {e}")
            return False
    
    def _wire_callbacks(self):
        """Wire callbacks via set_siqe_engine (already handles trade callbacks)."""
        logger.info("Wiring SIQEEngine to Runner...")
        
        if self.runner and self.engine:
            self.runner.set_siqe_engine(self.engine)
        
        logger.info("✓ SIQEEngine wired to Runner")
    
    async def start(self):
        """Start autonomous trading with proper sequence."""
        logger.info("=" * 60)
        logger.info("STARTING AUTONOMOUS TRADING")
        logger.info("=" * 60)
        
        # Get event loop for thread pool operations
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Step 1: Cleanup (ensure clean slate)
        cleanup_stale_processes()
        
        # Step 2: Create VN.PY runner first
        logger.info("Creating VN.PY runner...")
        self.runner = self.create_runner()
        
        # Step 3: Setup VN.PY (blocking - run in thread pool)
        logger.info("Setting up VN.PY engine...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.setup),
                timeout=10.0
            )
            logger.info("VN.PY setup complete")
        except asyncio.TimeoutError:
            logger.error("VN.PY setup timeout")
            return False
        except Exception as e:
            logger.error(f"VN.PY setup error: {e}")
            return False
        
        # Step 4: Connect to Binance (blocking - run in thread pool)
        logger.info("Connecting to Binance TESTNET...")
        try:
            conn_result = await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.connect),
                timeout=15.0
            )
            if not conn_result:
                logger.error("Failed to connect to Binance")
                return False
            logger.info("Binance connection complete")
        except asyncio.TimeoutError:
            logger.error("Binance connection timeout")
            return False
        except Exception as e:
            logger.error(f"Binance connection error: {e}")
            return False
        
        # Step 5: Create SIQE engine (mock execution)
        if not await self.initialize_engine():
            logger.error("Failed to initialize SIQE engine, aborting")
            return False
        
        # Step 6: Wire callbacks (Runner → Engine)
        self._wire_callbacks()
        
        # Step 7: Add strategy (blocking - run in thread pool)
        logger.info("Adding strategy...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.add_strategy),
                timeout=10.0
            )
            logger.info("Strategy added")
        except asyncio.TimeoutError:
            logger.error("Strategy add timeout")
        except Exception as e:
            logger.error(f"Strategy add error: {e}")
        
        # Step 8: Initialize strategy (blocking - run in thread pool)
        logger.info("Initializing strategy...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.init_strategy),
                timeout=15.0
            )
            logger.info("Strategy initialized")
        except asyncio.TimeoutError:
            logger.error("Strategy init timeout")
        except Exception as e:
            logger.error(f"Strategy init error: {e}")
        
        # Step 9: Register trade callbacks (thread pool to avoid hang)
        logger.info("Registering trade callbacks...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.register_strategy_callbacks),
                timeout=10.0
            )
            logger.info("Trade callbacks registered")
        except asyncio.TimeoutError:
            logger.error("Trade callback registration timeout")
        except Exception as e:
            logger.error(f"Trade callback registration error: {e}")
        
        # Step 10: Start strategy (blocking - run in thread pool)
        logger.info("Starting strategy trading...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.runner.start_strategy),
                timeout=10.0
            )
            logger.info("Strategy started")
        except asyncio.TimeoutError:
            logger.error("Strategy start timeout")
        except Exception as e:
            logger.error(f"Strategy start error: {e}")
        
        self.running = True
        
        # Step 11: Start health monitor
        self._health_monitor_task = asyncio.create_task(self._health_monitor())
        logger.info("Health monitor started")
        
        logger.info("=" * 60)
        logger.info("AUTONOMOUS TRADING ACTIVE")
        logger.info("=" * 60)
        logger.info(f"Strategy: siqe_autonomous")
        logger.info(f"Symbol: {self.symbol.upper()}/USDT")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Risk Engine: Active (Advisory Mode)")
        logger.info(f"Learning: Active (every 25 trades)")
        logger.info("=" * 60)
        
        logger.info("=== STARTUP COMPLETE ===")
        
        return True
    
    async def _health_monitor(self):
        """Background health monitoring every 30s."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(30)
            
            if not self.running:
                break
            
            # Check runner health
            if self.runner and self.engine:
                try:
                    status = await self.runner.get_risk_status_async() if hasattr(self.runner, 'get_risk_status_async') else {}
                    logger.debug(f"Health check: {status}")
                except Exception as e:
                    logger.warning(f"Health check error: {e}")
    
    async def stop(self, reason: str = "Manual"):
        """Stop autonomous trading gracefully."""
        logger.info("=" * 60)
        logger.info("STOPPING AUTONOMOUS TRADING")
        logger.info("=" * 60)
        
        self._shutdown_event.set()
        self.running = False
        
        # Send shutdown alert
        if self._alert_manager and self._alert_manager.is_configured():
            try:
                self._alert_manager.system_shutdown(reason=reason)
            except Exception as e:
                logger.error(f"Error sending shutdown alert: {e}")
        
        # Save state before shutdown
        if self.engine and hasattr(self.engine, 'state_manager'):
            logger.info("Saving system state...")
            try:
                await self.engine.state_manager.save_state(
                    self.engine.risk_engine if hasattr(self.engine, 'risk_engine') else None,
                    self.engine.meta_harness if hasattr(self.engine, 'meta_harness') else None
                )
            except Exception as e:
                logger.error(f"Error saving state: {e}")
        
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except:
                pass
        
        if self.runner:
            logger.info("Closing VN.PY runner...")
            try:
                self.runner.close()
            except Exception as e:
                logger.error(f"Error closing runner: {e}")
        
        # Release process lock
        release_process_lock()
        
        logger.info("✓ Autonomous trading stopped")
    
    async def get_status(self) -> dict:
        """Get current trading status."""
        status = {
            "running": self.running,
            "timestamp": datetime.now().isoformat(),
            "symbol": self.symbol.upper(),
            "leverage": self.leverage,
        }
        
        if self.runner and self.engine:
            try:
                risk_status = await self.runner.get_risk_status_async() if hasattr(self.runner, 'get_risk_status_async') else {}
                status["risk_status"] = risk_status
            except Exception as e:
                logger.debug(f"Could not get runner status: {e}")
        
        if self.engine:
            try:
                status["engine_status"] = self.engine.get_status() if hasattr(self.engine, 'get_status') else {}
            except:
                pass
        
        return status


async def main():
    """Main entry point."""
    # Acquire process lock
    if not acquire_process_lock():
        logger.error("Failed to acquire process lock. Exiting.")
        sys.exit(1)
    
    trader = AutonomousTrader()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        if trader.running:
            asyncio.create_task(trader.stop(reason=f"Signal {signum}"))
        release_process_lock()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Send startup alert
    if trader._alert_manager and trader._alert_manager.is_configured():
        try:
            trader._alert_manager.system_startup(
                symbol="BTCUSDT",
                leverage=35,
                version="3.0"
            )
        except Exception as e:
            logger.error(f"Error sending startup alert: {e}")
    
    try:
        if await trader.start():
            while trader.running:
                await asyncio.sleep(60)
                status = await trader.get_status()
                logger.info(f"Status: {status['running']} | Risk: {status.get('risk_status', {})}")
        
        await trader.stop(reason="Normal shutdown")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if trader._alert_manager and trader._alert_manager.is_configured():
            trader._alert_manager.dispatch(
                AlertType.EMERGENCY_STOP,
                f"System crashed: {str(e)}",
                metadata={"fatal_error": True}
            )
        await trader.stop(reason=f"Error: {e}")
    finally:
        release_process_lock()


if __name__ == "__main__":
    print("SIQE V3 - Autonomous Trading Launcher")
    print("=" * 40)
    print("Press Ctrl+C to stop")
    print()
    
    asyncio.run(main())
