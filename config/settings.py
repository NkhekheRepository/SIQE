"""
Configuration Settings Module
Centralized configuration management for SIQE V3
"""
import os
from typing import Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Centralized settings management."""
    
    def __init__(self):
        # Environment settings
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.timezone = os.getenv("TIMEZONE", "UTC")
        
        # Trading settings
        self.initial_equity = float(os.getenv("INITIAL_EQUITY", "10000"))
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "0.1"))
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", "0.05"))
        self.max_drawdown = float(os.getenv("MAX_DRAWDOWN", "0.20"))
        self.min_ev_threshold = float(os.getenv("MIN_EV_THRESHOLD", "0.01"))
        
        # Risk management settings
        self.max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
        self.max_trades_per_hour = int(os.getenv("MAX_TRADES_PER_HOUR", "100"))
        self.pnl_deviation_threshold = float(os.getenv("PNL_DEVIATION_THRESHOLD", "3.0"))
        self.min_trades_for_anomaly_detection = int(os.getenv("MIN_TRADES_FOR_ANOMALY_DETECTION", "20"))
        self.volatility_scaling = os.getenv("VOLATILITY_SCALING", "true").lower() == "true"
        
        # Learning engine settings
        self.min_sample_size = int(os.getenv("MIN_SAMPLE_SIZE", "50"))
        self.max_param_change = float(os.getenv("MAX_PARAM_CHANGE", "0.1"))
        self.rollback_enabled = os.getenv("ROLLBACK_ENABLED", "true").lower() == "true"
        
        # Regime engine settings
        self.regime_lookback_period = int(os.getenv("REGIME_LOOKBACK_PERIOD", "100"))
        
        # Database settings
        self.db_path = os.getenv("DB_PATH", "./data/siqe.db")
        
        # Execution settings
        self.use_mock_execution = os.getenv("USE_MOCK_EXECUTION", "true").lower() == "true"
        self.slippage_model = os.getenv("SLIPPAGE_MODEL", "linear")
        self.latency_tolerance_ms = int(os.getenv("LATENCY_TOLERANCE_MS", "100"))
        
        # VN.PY settings
        self.vnpy_gateway = os.getenv("VNPY_GATEWAY", "BINANCE")
        self.exchange_api_key = os.getenv("EXCHANGE_API_KEY", "")
        self.exchange_api_secret = os.getenv("EXCHANGE_API_SECRET", "")
        self.exchange_server = os.getenv("EXCHANGE_SERVER", "SIMULATOR")
        self.proxy_host = os.getenv("PROXY_HOST", "")
        self.proxy_port = int(os.getenv("PROXY_PORT", "0"))
        
        # Logging settings
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = os.getenv("LOG_FILE", "./logs/siqe.log")
        
        # API settings
        self.api_host = os.getenv("API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("API_PORT", "8000"))
        
        # Strategy restrictions
        restricted_symbols_str = os.getenv("RESTRICTED_SYMBOLS", "")
        self.restricted_symbols = [s.strip().upper() for s in restricted_symbols_str.split(",") if s.strip()]
        
        # Feature flags
        self.enable_learning = os.getenv("ENABLE_LEARNING", "true").lower() == "true"
        self.enable_regime_detection = os.getenv("ENABLE_REGIME_DETECTION", "true").lower() == "true"
        self.enable_meta_override = os.getenv("ENABLE_META_OVERRIDE", "true").lower() == "true"

        self.max_queue_size = int(os.getenv("MAX_QUEUE_SIZE", "1000"))
        self.max_concurrent_events = int(os.getenv("MAX_CONCURRENT_EVENTS", "4"))
        self.stage_timeout = float(os.getenv("STAGE_TIMEOUT", "5.0"))
        self.max_retries = int(os.getenv("MAX_RETRIES", "3"))
        self.retry_base_delay = float(os.getenv("RETRY_BASE_DELAY", "0.1"))
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value by key."""
        return getattr(self, key, default)
    
    def set(self, key: str, value: Any):
        """Set setting value by key."""
        setattr(self, key, value)
    
    def to_dict(self) -> dict:
        """Convert settings to dictionary (excluding sensitive info)."""
        settings_dict = {}
        for key in dir(self):
            if not key.startswith('_') and key not in ['get', 'set', 'to_dict']:
                value = getattr(self, key)
                if not callable(value):
                    settings_dict[key] = value
        return settings_dict
    
    def validate(self) -> tuple[bool, list]:
        """Validate settings and return (is_valid, errors)."""
        errors = []
        
        if self.initial_equity <= 0:
            errors.append("INITIAL_EQUITY must be positive")
        
        if not 0 < self.max_position_size <= 1:
            errors.append("MAX_POSITION_SIZE must be between 0 and 1")
        
        if not 0 < self.max_daily_loss <= 1:
            errors.append("MAX_DAILY_LOSS must be between 0 and 1")
        
        if not 0 < self.max_drawdown <= 1:
            errors.append("MAX_DRAWDOWN must be between 0 and 1")
        
        if self.min_ev_threshold < 0:
            errors.append("MIN_EV_THRESHOLD must be non-negative")
        
        if self.max_consecutive_losses < 0:
            errors.append("MAX_CONSECUTIVE_LOSSES must be non-negative")
        
        if self.max_trades_per_hour <= 0:
            errors.append("MAX_TRADES_PER_HOUR must be positive")
        
        if not 0 < self.max_param_change <= 1:
            errors.append("MAX_PARAM_CHANGE must be between 0 and 1")
        
        if self.min_sample_size < 1:
            errors.append("MIN_SAMPLE_SIZE must be positive")
        
        if self.regime_lookback_period < 1:
            errors.append("REGIME_LOOKBACK_PERIOD must be positive")
        
        try:
            import pytz
            pytz.timezone(self.timezone)
        except Exception:
            errors.append(f"Invalid TIMEZONE: {self.timezone}")
        
        return len(errors) == 0, errors


_settings_instance = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def validate_settings() -> tuple[bool, list]:
    """Explicitly validate settings. Call during startup."""
    settings = get_settings()
    return settings.validate()
