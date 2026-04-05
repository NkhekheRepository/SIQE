"""
SIQE V3 - Real Market Data Loader

Production-grade parquet data loading and validation for backtesting
and walk-forward validation on real market data.

Handles:
- Parquet loading from Binance futures data
- Column standardization (open/high/low/close/volume/datetime)
- Data quality validation with fail-fast checks
- Resampling and filtering utilities
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = {"open", "high", "low", "close"}
OPTIONAL_COLUMNS = {"volume", "datetime"}


class DataValidationError(Exception):
    """Raised when data validation fails."""
    pass


@dataclass
class DataQualityReport:
    """Report on data quality after validation."""
    is_valid: bool
    row_count: int
    date_range: Tuple[str, str]
    missing_values: Dict[str, int]
    price_anomalies: List[str]
    volume_stats: Optional[Dict[str, float]] = None
    warnings: List[str] = field(default_factory=list)


def load_parquet_data(
    path: str,
    standardize_columns: bool = True,
    require_volume: bool = False,
) -> pd.DataFrame:
    """
    Load parquet data and standardize column names.

    Args:
        path: Path to parquet file or directory
        standardize_columns: If True, normalize column names to lowercase
        require_volume: If True, raise error if volume column missing

    Returns:
        DataFrame with standardized columns and datetime index

    Raises:
        FileNotFoundError: If path doesn't exist
        DataValidationError: If required columns missing
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    if path.is_dir():
        dfs = []
        for p in sorted(path.glob("*.parquet")):
            df = pd.read_parquet(p)
            df["_source_file"] = p.stem
            dfs.append(df)
        if not dfs:
            raise DataValidationError(f"No parquet files found in: {path}")
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_parquet(path)

    if standardize_columns:
        df = _standardize_columns(df)

    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()

    if require_volume and "volume" not in df.columns:
        raise DataValidationError("Volume column required but not found")

    if "volume" not in df.columns:
        df["volume"] = 0.0

    logger.info(f"Loaded {len(df)} rows from {path}")
    return df


def validate_ohlc_data(df: pd.DataFrame) -> Tuple[bool, DataQualityReport]:
    """
    Validate OHLCV data quality with comprehensive checks.

    Checks:
    - Required columns present
    - No missing values in OHLC
    - High >= Low for all rows
    - Positive prices
    - Volume non-negative (if present)
    - No duplicate timestamps
    - Chronological ordering

    Args:
        df: DataFrame to validate

    Returns:
        Tuple of (is_valid, DataQualityReport)
    """
    errors = []
    warnings = []
    missing_values = {}

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            errors.append(f"Missing required column: {col}")
        else:
            missing_values[col] = int(df[col].isna().sum())
            if missing_values[col] > 0:
                errors.append(f"Column '{col}' has {missing_values[col]} missing values")

    if errors:
        report = DataQualityReport(
            is_valid=False,
            row_count=len(df),
            date_range=("", ""),
            missing_values=missing_values,
            price_anomalies=errors,
            warnings=warnings,
        )
        return False, report

    anomalies = []

    if (df["high"] < df["low"]).any():
        count = int((df["high"] < df["low"]).sum())
        anomalies.append(f"High < Low in {count} rows")

    if (df["close"] <= 0).any():
        count = int((df["close"] <= 0).sum())
        anomalies.append(f"Non-positive close in {count} rows")

    if (df["open"] <= 0).any():
        count = int((df["open"] <= 0).sum())
        anomalies.append(f"Non-positive open in {count} rows")

    if "volume" in df.columns:
        neg_vol = (df["volume"] < 0).sum()
        if neg_vol > 0:
            anomalies.append(f"Negative volume in {int(neg_vol)} rows")

    if df.index.duplicated().any():
        dup_count = int(df.index.duplicated().sum())
        anomalies.append(f"{dup_count} duplicate timestamps")

    if not df.index.is_monotonic_increasing:
        warnings.append("Data not sorted chronologically")

    date_range = (str(df.index.min()), str(df.index.max()))

    volume_stats = None
    if "volume" in df.columns:
        volume_stats = {
            "mean": float(df["volume"].mean()),
            "median": float(df["volume"].median()),
            "min": float(df["volume"].min()),
            "max": float(df["volume"].max()),
            "zero_count": int((df["volume"] == 0).sum()),
        }

    is_valid = len(anomalies) == 0

    report = DataQualityReport(
        is_valid=is_valid,
        row_count=len(df),
        date_range=date_range,
        missing_values=missing_values,
        price_anomalies=anomalies,
        volume_stats=volume_stats,
        warnings=warnings,
    )

    if is_valid:
        logger.info(
            f"Data validation passed: {len(df)} rows, "
            f"{date_range[0]} to {date_range[1]}"
        )
    else:
        logger.warning(f"Data validation failed: {'; '.join(anomalies)}")

    return is_valid, report


def resample_data(
    df: pd.DataFrame,
    frequency: str = "4h",
) -> pd.DataFrame:
    """
    Resample OHLCV data to a different frequency.

    Args:
        df: DataFrame with datetime index
        frequency: Pandas frequency string (e.g., '4h', '1d', '15min')

    Returns:
        Resampled DataFrame
    """
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    available = {k: v for k, v in agg_dict.items() if k in df.columns}
    return df.resample(frequency).agg(available).dropna()


def filter_date_range(
    df: pd.DataFrame,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Filter DataFrame to a date range.

    Args:
        df: DataFrame with datetime index
        start: Start date (inclusive), ISO format
        end: End date (exclusive), ISO format

    Returns:
        Filtered DataFrame
    """
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index < pd.Timestamp(end)]
    return df


def compute_returns(df: pd.DataFrame) -> pd.Series:
    """
    Compute log returns from close prices.

    Args:
        df: DataFrame with 'close' column

    Returns:
        Series of log returns
    """
    return np.log(df["close"] / df["close"].shift(1)).dropna()


def detect_regime_sequence(
    df: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """
    Detect regime for each rolling window of data.

    Args:
        df: DataFrame with high/low/close columns
        window: Rolling window size for regime detection

    Returns:
        DataFrame with added 'regime' column
    """
    from strategy_engine.config import RegimeDetector, MarketRegime

    regimes = []
    for i in range(window, len(df)):
        window_data = df.iloc[i - window:i]
        result = RegimeDetector.detect(
            window_data["high"],
            window_data["low"],
            window_data["close"],
        )
        regimes.append(result.regime.value)

    regime_series = pd.Series(regimes, index=df.index[window:])
    df_with_regime = df.copy()
    df_with_regime["regime"] = regime_series
    return df_with_regime


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase standard format."""
    column_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if lower in ("open", "o"):
            column_map[col] = "open"
        elif lower in ("high", "h"):
            column_map[col] = "high"
        elif lower in ("low", "l"):
            column_map[col] = "low"
        elif lower in ("close", "c"):
            column_map[col] = "close"
        elif lower in ("volume", "vol", "v"):
            column_map[col] = "volume"
        elif lower in ("datetime", "date", "timestamp", "time"):
            column_map[col] = "datetime"

    if column_map:
        df = df.rename(columns=column_map)

    return df
