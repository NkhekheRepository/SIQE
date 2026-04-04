"""
Backtest Configuration
Extends SIQE settings with backtest-specific parameters.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DataProviderType(Enum):
    YFINANCE = "yfinance"
    CCXT = "ccxt"
    CSV = "csv"
    PARQUET = "parquet"


class SlippageModelType(Enum):
    FIXED_BPS = "fixed_bps"
    LINEAR = "linear"
    VOLUME_IMPACT = "volume_impact"


class LearningMode(Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"


@dataclass
class BacktestSettings:
    """Backtest-specific configuration."""
    data_provider: DataProviderType = DataProviderType.YFINANCE
    symbols: list = field(default_factory=lambda: ["SPY"])
    start_date: str = "2023-01-01"
    end_date: str = "2024-01-01"
    timeframe: str = "1d"
    initial_equity: float = 10000.0
    slippage_model: SlippageModelType = SlippageModelType.LINEAR
    slippage_bps: float = 10.0
    volume_impact_factor: float = 0.1
    learning_mode: LearningMode = LearningMode.FIXED
    learning_interval: int = 50
    rng_seed: int = 42
    output_dir: str = "./backtest_output"
    generate_report: bool = False
    ccxt_exchange: str = "binance"
    ccxt_market_type: str = "spot"
    csv_path: Optional[str] = None
    parquet_path: Optional[str] = None
    yfinance_download_threads: int = 4
    max_bars: int = 0
    bar_buffer: int = 50
