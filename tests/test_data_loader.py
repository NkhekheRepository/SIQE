"""
Tests for SIQE V3 Data Loader

Tests parquet loading, validation, and data quality checks.
"""
import pytest
import sys
import os
import tempfile
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.data_loader import (
    load_parquet_data,
    validate_ohlc_data,
    resample_data,
    filter_date_range,
    compute_returns,
    detect_regime_sequence,
    DataQualityReport,
    DataValidationError,
)


def generate_valid_ohlcv(n=100, seed=42):
    """Generate valid synthetic OHLCV data."""
    rng = np.random.RandomState(seed)
    closes = 100 + np.cumsum(rng.randn(n) * 0.5)
    highs = closes + np.abs(rng.randn(n)) * 0.3
    lows = closes - np.abs(rng.randn(n)) * 0.3
    opens = closes + rng.randn(n) * 0.2
    volumes = rng.uniform(1000, 10000, n)
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "datetime": dates,
    })


class TestLoadParquetData:
    def test_load_valid_parquet(self):
        df = generate_valid_ohlcv()
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            df.to_parquet(path)
            loaded = load_parquet_data(path)
            assert len(loaded) == 100
            assert "open" in loaded.columns
            assert "close" in loaded.columns
        finally:
            os.unlink(path)

    def test_load_missing_file_raises_error(self):
        with pytest.raises(FileNotFoundError):
            load_parquet_data("/nonexistent/path/data.parquet")

    def test_standardizes_column_names(self):
        df = pd.DataFrame({
            "Open": [100.0],
            "HIGH": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [5000.0],
        })
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            df.to_parquet(path)
            loaded = load_parquet_data(path)
            assert "open" in loaded.columns
            assert "high" in loaded.columns
            assert "low" in loaded.columns
            assert "close" in loaded.columns
            assert "volume" in loaded.columns
        finally:
            os.unlink(path)

    def test_require_volume_raises_when_missing(self):
        df = pd.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        })
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            df.to_parquet(path)
            with pytest.raises(DataValidationError):
                load_parquet_data(path, require_volume=True)
        finally:
            os.unlink(path)

    def test_adds_zero_volume_when_missing(self):
        df = pd.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        })
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            df.to_parquet(path)
            loaded = load_parquet_data(path)
            assert "volume" in loaded.columns
            assert (loaded["volume"] == 0.0).all()
        finally:
            os.unlink(path)

    def test_sets_datetime_index(self):
        df = generate_valid_ohlcv()
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            df.to_parquet(path)
            loaded = load_parquet_data(path)
            assert isinstance(loaded.index, pd.DatetimeIndex)
        finally:
            os.unlink(path)


class TestValidateOhlcData:
    def test_valid_data_passes(self):
        df = generate_valid_ohlcv()
        df = df.set_index("datetime")
        is_valid, report = validate_ohlc_data(df)
        assert is_valid is True
        assert report.row_count == 100
        assert len(report.price_anomalies) == 0

    def test_missing_column_fails(self):
        df = pd.DataFrame({"open": [100.0], "close": [100.5]})
        is_valid, report = validate_ohlc_data(df)
        assert is_valid is False
        assert any("high" in a for a in report.price_anomalies)

    def test_high_less_than_low_detected(self):
        df = pd.DataFrame({
            "open": [100.0, 101.0],
            "high": [101.0, 99.0],
            "low": [99.0, 102.0],
            "close": [100.5, 100.5],
        })
        is_valid, report = validate_ohlc_data(df)
        assert is_valid is False
        assert any("High < Low" in a for a in report.price_anomalies)

    def test_negative_close_detected(self):
        df = pd.DataFrame({
            "open": [100.0, -50.0],
            "high": [101.0, 102.0],
            "low": [99.0, 98.0],
            "close": [100.5, -50.0],
        })
        is_valid, report = validate_ohlc_data(df)
        assert is_valid is False
        assert any("Non-positive close" in a for a in report.price_anomalies)

    def test_missing_values_detected(self):
        df = generate_valid_ohlcv()
        df = df.set_index("datetime")
        df.loc[df.index[0], "close"] = np.nan
        is_valid, report = validate_ohlc_data(df)
        assert is_valid is False
        assert report.missing_values["close"] == 1

    def test_volume_stats_computed(self):
        df = generate_valid_ohlcv()
        df = df.set_index("datetime")
        is_valid, report = validate_ohlc_data(df)
        assert report.volume_stats is not None
        assert "mean" in report.volume_stats
        assert "max" in report.volume_stats

    def test_date_range_reported(self):
        df = generate_valid_ohlcv()
        df = df.set_index("datetime")
        _, report = validate_ohlc_data(df)
        assert "2025-01-01" in report.date_range[0]


class TestResampleData:
    def test_resample_to_daily(self):
        df = generate_valid_ohlcv(n=200)
        df = df.set_index("datetime")
        resampled = resample_data(df, frequency="1D")
        assert len(resampled) < 200
        assert "open" in resampled.columns
        assert "high" in resampled.columns
        assert "low" in resampled.columns
        assert "close" in resampled.columns
        assert "volume" in resampled.columns

    def test_resample_preserves_ohlc_logic(self):
        df = pd.DataFrame({
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [100.0, 200.0, 300.0, 400.0],
        }, index=pd.date_range("2025-01-01", periods=4, freq="1h"))

        resampled = resample_data(df, frequency="4h")
        assert len(resampled) == 1
        assert resampled.iloc[0]["open"] == 100.0
        assert resampled.iloc[0]["high"] == 104.0
        assert resampled.iloc[0]["low"] == 99.0
        assert resampled.iloc[0]["close"] == 103.5
        assert resampled.iloc[0]["volume"] == 1000.0


class TestFilterDateRange:
    def test_filter_by_start(self):
        df = generate_valid_ohlcv(n=100)
        df = df.set_index("datetime")
        filtered = filter_date_range(df, start="2025-01-03")
        assert filtered.index.min() >= pd.Timestamp("2025-01-03")

    def test_filter_by_end(self):
        df = generate_valid_ohlcv(n=100)
        df = df.set_index("datetime")
        filtered = filter_date_range(df, end="2025-01-02")
        assert filtered.index.max() < pd.Timestamp("2025-01-02")

    def test_filter_by_both(self):
        df = generate_valid_ohlcv(n=100)
        df = df.set_index("datetime")
        filtered = filter_date_range(df, start="2025-01-02", end="2025-01-04")
        assert filtered.index.min() >= pd.Timestamp("2025-01-02")
        assert filtered.index.max() < pd.Timestamp("2025-01-04")


class TestComputeReturns:
    def test_returns_length(self):
        df = generate_valid_ohlcv(n=100)
        df = df.set_index("datetime")
        returns = compute_returns(df)
        assert len(returns) == 99

    def test_returns_are_log_returns(self):
        df = pd.DataFrame({
            "close": [100.0, 110.0, 121.0],
        }, index=pd.date_range("2025-01-01", periods=3, freq="1D"))
        returns = compute_returns(df)
        expected = np.log(110.0 / 100.0)
        assert abs(returns.iloc[0] - expected) < 1e-10


class TestDetectRegimeSequence:
    def test_regime_sequence_returns_dataframe(self):
        df = generate_valid_ohlcv(n=200)
        df = df.set_index("datetime")
        result = detect_regime_sequence(df, window=60)
        assert "regime" in result.columns
        assert result["regime"].iloc[-1] is not None

    def test_regime_values_are_valid(self):
        df = generate_valid_ohlcv(n=200)
        df = df.set_index("datetime")
        result = detect_regime_sequence(df, window=60)
        valid_regimes = {"trending_up", "trending_down", "ranging", "volatile", "quiet"}
        non_null = result["regime"].dropna()
        assert all(r in valid_regimes for r in non_null)
