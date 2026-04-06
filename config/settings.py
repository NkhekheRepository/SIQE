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
        self.min_ev_threshold = float(os.getenv("MIN_EV_THRESHOLD", "0.0"))
        
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

        # Data source settings (Phase 1)
        self.use_real_data = os.getenv("USE_REAL_DATA", "false").lower() == "true"
        self.data_source = os.getenv("DATA_SOURCE", "websocket")
        self.historical_data_path = os.getenv("HISTORICAL_DATA_PATH", "data/binance_futures/parquet/")
        self.ccxt_exchange = os.getenv("CCXT_EXCHANGE", "binance")
        self.ccxt_market_type = os.getenv("CCXT_MARKET_TYPE", "swap")

        # Futures settings (Phase 1)
        self.futures_api_key = os.getenv("FUTURES_API_KEY", "")
        self.futures_api_secret = os.getenv("FUTURES_API_SECRET", "")
        self.futures_leverage = int(os.getenv("FUTURES_LEVERAGE", "35"))
        self.futures_symbol = os.getenv("FUTURES_SYMBOL", "btcusdt")
        self.futures_risk_pct = float(os.getenv("FUTURES_RISK_PCT", "0.02"))
        self.futures_margin_alert_pct = float(os.getenv("FUTURES_MARGIN_ALERT_PCT", "0.70"))
        self.futures_margin_stop_pct = float(os.getenv("FUTURES_MARGIN_STOP_PCT", "0.90"))
        self.futures_atr_stop = float(os.getenv("FUTURES_ATR_STOP", "0.5"))
        self.futures_atr_trailing = float(os.getenv("FUTURES_ATR_TRAILING", "0.75"))

        # Adaptation boundaries (Phase 1)
        self.position_size_min = float(os.getenv("POSITION_SIZE_MIN", "0.001"))
        self.position_size_max = float(os.getenv("POSITION_SIZE_MAX", "0.08"))
        self.risk_per_trade_min = float(os.getenv("RISK_PER_TRADE_MIN", "0.005"))
        self.risk_per_trade_max = float(os.getenv("RISK_PER_TRADE_MAX", "0.03"))
        self.notional_max = float(os.getenv("NOTIONAL_MAX", "50000"))
        self.stop_loss_min_atr = float(os.getenv("STOP_LOSS_MIN_ATR", "0.75"))
        self.stop_loss_max_atr = float(os.getenv("STOP_LOSS_MAX_ATR", "2.5"))
        self.stop_loss_default_atr = float(os.getenv("STOP_LOSS_DEFAULT_ATR", "1.0"))
        self.take_profit_min_atr = float(os.getenv("TAKE_PROFIT_MIN_ATR", "1.5"))
        self.take_profit_max_atr = float(os.getenv("TAKE_PROFIT_MAX_ATR", "5.0"))
        self.take_profit_default_atr = float(os.getenv("TAKE_PROFIT_DEFAULT_ATR", "2.0"))
        self.learning_interval_min = int(os.getenv("LEARNING_INTERVAL_MIN", "5"))
        self.learning_interval_max = int(os.getenv("LEARNING_INTERVAL_MAX", "75"))
        self.learning_interval_default = int(os.getenv("LEARNING_INTERVAL_DEFAULT", "15"))
        self.rollback_threshold = int(os.getenv("ROLLBACK_THRESHOLD", "3"))
        self.rollback_cooldown = int(os.getenv("ROLLBACK_COOLDOWN", "300"))
        
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
        
        # Telegram Alert Settings
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.alert_enabled = os.getenv("ALERT_ENABLED", "true").lower() == "true"
        self.alert_rate_limit_seconds = int(os.getenv("ALERT_RATE_LIMIT_SECONDS", "60"))
        
        # Alert Thresholds
        self.alert_position_size_warning = float(os.getenv("ALERT_POSITION_SIZE_WARNING", "0.05"))
        self.alert_drawdown_warning = float(os.getenv("ALERT_DRAWDOWN_WARNING", "0.05"))
        self.alert_drawdown_critical = float(os.getenv("ALERT_DRAWDOWN_CRITICAL", "0.10"))
        self.alert_param_drift = float(os.getenv("ALERT_PARAM_DRIFT", "0.30"))
    
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
        
        if not self.use_mock_execution:
            if not self.exchange_api_key:
                errors.append("EXCHANGE_API_KEY is required for live trading (USE_MOCK_EXECUTION=false)")
            if not self.exchange_api_secret:
                errors.append("EXCHANGE_API_SECRET is required for live trading (USE_MOCK_EXECUTION=false)")
            if self.exchange_server not in ("LIVE", "SIMULATOR"):
                errors.append(f"EXCHANGE_SERVER must be LIVE or SIMULATOR, got: {self.exchange_server}")
            if self.environment != "production":
                errors.append("ENVIRONMENT should be 'production' when USE_MOCK_EXECUTION=false")
        
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
