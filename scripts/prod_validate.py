#!/usr/bin/env python3
"""
Production validation script for SIQE V3 trading engine.
Checks that the system is properly configured and ready for live trading.
"""
import os
import sys
import asyncio
import logging
from typing import Tuple, List

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings, get_settings, validate_settings
from infra.key_manager import KeyManager
from infra.metrics import get_metrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProductionValidator:
    """Validates SIQE V3 production readiness."""
    
    def __init__(self):
        self.settings = get_settings()
        self.key_manager = KeyManager.get_key_manager()
        self.metrics = get_metrics()
        self.errors = []
        self.warnings = []
    
    def validate_environment(self) -> Tuple[bool, List[str]]:
        """Validate environment configuration."""
        logger.info("Validating environment configuration...")
        
        # Check environment
        env = self.settings.get("environment", "development")
        if env != "production":
            self.warnings.append(f"Environment is '{env}', should be 'production' for live trading")
        
        # Check debug mode
        if self.settings.get("debug", False):
            self.warnings.append("Debug mode is enabled - disable for production")
        
        # Check timezone
        try:
            import pytz
            pytz.timezone(self.settings.get("timezone", "UTC"))
        except Exception as e:
            self.errors.append(f"Invalid timezone: {e}")
        
        return len(self.errors) == 0, self.errors
    
    def validate_api_keys(self) -> Tuple[bool, List[str]]:
        """Validate API keys are present and valid."""
        logger.info("Validating API keys...")
        
        # Check if we're supposed to be in live mode
        use_mock = self.settings.get("use_mock_execution", True)
        if use_mock:
            self.warnings.append("USE_MOCK_EXECUTION is true - system will run in paper trading mode")
            # Still validate format if keys are provided, but don't require them
            exchange = self.settings.get("vnpy_gateway", "binance").lower()
            key_status = self.key_manager.get_key_status(exchange, testnet=False)
            
            # Log masked key info if keys exist
            if key_status["has_key"]:
                logger.info(f"{exchange.upper()} API key: {key_status['masked_key']} (usage: {key_status['usage_count']})")
            elif key_status["has_secret"]:
                logger.info(f"{exchange.upper()} API secret provided (key missing)")
            
            # Only validate format if at least one is provided
            if key_status["has_key"] or key_status["has_secret"]:
                if not key_status["is_valid"]:
                    self.errors.append(f"Invalid API key/secret format for {exchange}")
                return len(self.errors) == 0, self.errors
            else:
                return True, []  # No keys required in mock mode
        
        # Validate exchange API keys for live trading
        exchange = self.settings.get("vnpy_gateway", "binance").lower()
        key_status = self.key_manager.get_key_status(exchange, testnet=False)
        
        if not key_status["has_key"]:
            self.errors.append(f"Missing API key for {exchange}")
        if not key_status["has_secret"]:
            self.errors.append(f"Missing API secret for {exchange}")
        if not key_status["is_valid"]:
            self.errors.append(f"Invalid API key/secret format for {exchange}")
        
        # Log masked key info (without exposing actual keys)
        if key_status["has_key"]:
            logger.info(f"{exchange.upper()} API key: {key_status['masked_key']} (usage: {key_status['usage_count']})")
        
        return len(self.errors) == 0, self.errors
    
    def validate_data_sources(self) -> Tuple[bool, List[str]]:
        """Validate data source configuration."""
        logger.info("Validating data sources...")
        
        use_real_data = self.settings.get("use_real_data", False)
        if not use_real_data:
            self.warnings.append("USE_REAL_DATA is false - using simulated/data from parquet files")
        
        # Check historical data path exists
        hist_path = self.settings.get("historical_data_path", "data/binance_futures/parquet/")
        if not os.path.exists(hist_path):
            self.warnings.append(f"Historical data path not found: {hist_path}")
        
        # Check if we have parquet files
        if os.path.exists(hist_path):
            parquet_files = [f for f in os.listdir(hist_path) if f.endswith('.parquet')]
            if not parquet_files:
                self.warnings.append(f"No parquet files found in {hist_path}")
            else:
                logger.info(f"Found {len(parquet_files)} parquet files for historical data")
        
        return len(self.errors) == 0, self.errors
    
    def validate_risk_parameters(self) -> Tuple[bool, List[str]]:
        """Validate risk management parameters."""
        logger.info("Validating risk parameters...")
        
        # Check position sizing
        max_pos = self.settings.get("max_position_size", 0.1)
        if not 0 < max_pos <= 1:
            self.errors.append(f"MAX_POSITION_SIZE must be between 0 and 1, got {max_pos}")
        
        # Check daily loss limit
        max_daily_loss = self.settings.get("max_daily_loss", 0.05)
        if not 0 < max_daily_loss <= 1:
            self.errors.append(f"MAX_DAILY_LOSS must be between 0 and 1, got {max_daily_loss}")
        
        # Check max drawdown
        max_dd = self.settings.get("max_drawdown", 0.20)
        if not 0 < max_dd <= 1:
            self.errors.append(f"MAX_DRAWDOWN must be between 0 and 1, got {max_dd}")
        
        # Check risk per trade boundaries
        risk_min = self.settings.get("risk_per_trade_min", 0.005)
        risk_max = self.settings.get("risk_per_trade_max", 0.03)
        if risk_min >= risk_max:
            self.errors.append(f"RISK_PER_TRADE_MIN ({risk_min}) must be < RISK_PER_TRADE_MAX ({risk_max})")
        
        # Check ATR-based stop loss boundaries
        sl_min = self.settings.get("stop_loss_min_atr", 0.75)
        sl_max = self.settings.get("stop_loss_max_atr", 2.5)
        sl_default = self.settings.get("stop_loss_default_atr", 1.0)
        if not sl_min <= sl_default <= sl_max:
            self.errors.append(f"Default ATR stop ({sl_default}) must be between min ({sl_min}) and max ({sl_max})")
        
        tp_min = self.settings.get("take_profit_min_atr", 1.5)
        tp_max = self.settings.get("take_profit_max_atr", 5.0)
        tp_default = self.settings.get("take_profit_default_atr", 2.0)
        if not tp_min <= tp_default <= tp_max:
            self.errors.append(f"Default ATR TP ({tp_default}) must be between min ({tp_min}) and max ({tp_max})")
        
        return len(self.errors) == 0, self.errors
    
    def validate_infrastructure(self) -> Tuple[bool, List[str]]:
        """Validate infrastructure components."""
        logger.info("Validating infrastructure...")
        
        # Check that required directories exist
        required_dirs = ["data", "logs", "output", "reports"]
        for dir_name in required_dirs:
            dir_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), dir_name)
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.info(f"Created directory: {dir_path}")
                except Exception as e:
                    self.errors.append(f"Failed to create directory {dir_path}: {e}")
        
        # Check that we can write to logs directory
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        if os.path.exists(logs_dir):
            test_file = os.path.join(logs_dir, ".write_test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except Exception as e:
                self.errors.append(f"Cannot write to logs directory: {e}")
        
        return len(self.errors) == 0, self.errors
    
    async def validate_runtime_components(self) -> Tuple[bool, List[str]]:
        """Validate that core components can initialize."""
        logger.info("Validating runtime components...")
        
        try:
            # Try to import and instantiate core components
            from core.data_engine import DataEngine
            from core.clock import RealTimeClock
            from execution_adapter.vnpy_bridge import ExecutionAdapter
            
            # Create a minimal clock for testing
            clock = RealTimeClock()
            
            # Try to initialize data engine (will fail gracefully if no exchange connectivity)
            data_engine = DataEngine(self.settings, clock)
            # Don't actually initialize as it requires network - just check instantiation
            
            logger.info("Core components imported successfully")
            
        except ImportError as e:
            self.errors.append(f"Failed to import core component: {e}")
        except Exception as e:
            self.warnings.append(f"Runtime component validation warning: {e}")
        
        return len(self.errors) == 0, self.errors
    
    def validate_metrics_system(self) -> Tuple[bool, List[str]]:
        """Validate metrics system is working."""
        logger.info("Validating metrics system...")
        
        try:
            # Test that we can record metrics
            from infra.metrics import get_metrics
            metrics = get_metrics()
            metrics.record_event_processed()
            metrics.record_event_rejected()
            metrics.record_trade(10.5, "BTCUSDT")
            metrics.record_pipeline_latency("test", 0.005)
            metrics.record_ws_latency("binance", 12.5)
            metrics.record_alert("test_alert")
            
            # Test gauge updates
            test_status = {
                "engine_running": 1,
                "equity": 10000,
                "daily_pnl": 100,
                "drawdown_pct": 0.5,
                "consecutive_losses": 0,
                "queue_depth": 10,
                "memory_mb": 512,
                "peak_memory_mb": 1024,
                "active_positions": 2,
                "portfolio_exposure": 5000,
                "circuit_breaker_active": 0
            }
            metrics.update_gauges(test_status)
            
            logger.info("Metrics system validated successfully")
            
        except Exception as e:
            self.errors.append(f"Metrics system validation failed: {e}")
        
        return len(self.errors) == 0, self.errors
    
    async def run_validation(self) -> bool:
        """Run all validation checks."""
        logger.info("Starting SIQE V3 production validation...")
        logger.info("=" * 60)
        
        validations = [
            ("Environment", self.validate_environment),
            ("API Keys", self.validate_api_keys),
            ("Data Sources", self.validate_data_sources),
            ("Risk Parameters", self.validate_risk_parameters),
            ("Infrastructure", self.validate_infrastructure),
            ("Runtime Components", self.validate_runtime_components),
            ("Metrics System", self.validate_metrics_system),
        ]
        
        all_passed = True
        
        for name, validator in validations:
            logger.info(f"\n{name}:")
            logger.info("-" * 40)
            
            if asyncio.iscoroutinefunction(validator):
                passed, errors = await validator()
            else:
                passed, errors = validator()
            
            if passed:
                logger.info(f"✓ {name} validation PASSED")
            else:
                logger.error(f"✗ {name} validation FAILED")
                all_passed = False
                for error in errors:
                    logger.error(f"  • {error}")
            
            # Show warnings
            for warning in self.warnings:
                if warning not in [w for _, _, w in getattr(self, '_shown_warnings', [])]:
                    logger.warning(f"  ⚠ {warning}")
        
        logger.info("\n" + "=" * 60)
        if all_passed:
            logger.info("🎉 ALL VALIDATIONS PASSED - System is ready for production!")
        else:
            logger.error("❌ VALIDATION FAILED - Please fix errors before deploying to production")
        
        if self.warnings:
            logger.info(f"\n📝 {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                logger.info(f"  • {warning}")
        
        return all_passed


async def main():
    """Main entry point."""
    validator = ProductionValidator()
    success = await validator.run_validation()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())