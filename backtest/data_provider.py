"""
Historical Data Provider
Fetches OHLCV data from free APIs (yfinance, CCXT) or local files (CSV, Parquet)
and converts to MarketEvent objects for deterministic replay.
"""
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, List, Optional, Dict, Any

import numpy as np
import pandas as pd

from core.clock import EventClock
from models.trade import MarketEvent
from backtest.config import DataProviderType, BacktestSettings

logger = logging.getLogger(__name__)


class BaseDataProvider(ABC):
    """Abstract base for historical data providers."""

    @abstractmethod
    def fetch(self, settings: BacktestSettings) -> Dict[str, pd.DataFrame]:
        """Fetch historical OHLCV data, return {symbol: DataFrame}."""
        pass

    def to_market_events(
        self,
        data: Dict[str, pd.DataFrame],
        clock: EventClock,
        settings: BacktestSettings,
    ) -> List[MarketEvent]:
        """Convert OHLCV DataFrames to ordered list of MarketEvent objects."""
        events = []
        seq = 0

        all_rows = []
        for symbol, df in data.items():
            df = df.copy()
            df["_symbol"] = symbol
            all_rows.append(df)

        if not all_rows:
            return events

        combined = pd.concat(all_rows, ignore_index=True)

        if "datetime" not in combined.columns and "date" in combined.columns:
            combined["datetime"] = combined["date"]

        if "datetime" not in combined.columns:
            combined["datetime"] = combined.index

        combined["datetime"] = pd.to_datetime(combined["datetime"])
        combined = combined.sort_values("datetime").reset_index(drop=True)

        if settings.max_bars > 0:
            combined = combined.tail(settings.max_bars)

        for _, row in combined.iterrows():
            close_price = float(row.get("close", row.get("Close", 0)))
            if close_price <= 0:
                continue

            spread_pct = 0.0001
            if "spread_pct" in row:
                spread_pct = float(row["spread_pct"])
            elif "volume" in row and float(row["volume"]) > 0:
                spread_pct = min(0.001, 0.0001 / max(1, np.log10(float(row["volume"]))))

            bid = close_price * (1 - spread_pct / 2)
            ask = close_price * (1 + spread_pct / 2)

            volatility = float(row.get("volatility", 0.02))
            if volatility <= 0 and "high" in row and "low" in row:
                high = float(row["high"])
                low = float(row["low"])
                if low > 0:
                    volatility = (high - low) / low

            volume = float(row.get("volume", row.get("Volume", 100)))

            seq += 1
            clock.tick()

            events.append(MarketEvent(
                event_id=f"bt_evt_{seq}",
                symbol=str(row["_symbol"]),
                bid=round(bid, 8),
                ask=round(ask, 8),
                volume=round(volume, 8),
                volatility=round(volatility, 6),
                event_seq=seq,
            ))

        return events


class YFinanceProvider(BaseDataProvider):
    """Fetches historical data from Yahoo Finance (free, no API key)."""

    def fetch(self, settings: BacktestSettings) -> Dict[str, pd.DataFrame]:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

        data = {}
        for symbol in settings.symbols:
            logger.info(f"Fetching {symbol} from yfinance ({settings.start_date} to {settings.end_date})")
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=settings.start_date,
                end=settings.end_date,
                interval=self._map_timeframe(settings.timeframe),
                auto_adjust=True,
            )

            if df.empty:
                logger.warning(f"No data for {symbol} from yfinance")
                continue

            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]]
            df.index.name = "datetime"
            df = df.reset_index()

            data[symbol] = df
            logger.info(f"Fetched {len(df)} bars for {symbol}")

        return data

    def _map_timeframe(self, timeframe: str) -> str:
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "1h",
            "1d": "1d",
            "1wk": "1wk",
            "1mo": "1mo",
        }
        return mapping.get(timeframe, "1d")


class CCXTProvider(BaseDataProvider):
    """Fetches historical data from crypto exchanges via CCXT (free, no API key for public data)."""

    def fetch(self, settings: BacktestSettings) -> Dict[str, pd.DataFrame]:
        try:
            import ccxt
        except ImportError:
            raise ImportError("ccxt not installed. Run: pip install ccxt")

        exchange_class = getattr(ccxt, settings.ccxt_exchange.lower(), None)
        if exchange_class is None:
            raise ValueError(f"Unknown CCXT exchange: {settings.ccxt_exchange}")

        exchange = exchange_class({
            "enableRateLimit": True,
        })

        data = {}
        timeframe = self._map_timeframe(settings.timeframe)

        for symbol in settings.symbols:
            logger.info(f"Fetching {symbol} from {settings.ccxt_exchange} ({settings.ccxt_market_type})")

            start_ts = int(datetime.strptime(settings.start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(settings.end_date, "%Y-%m-%d").timestamp() * 1000)

            all_ohlcv = []
            since = start_ts

            while since < end_ts:
                ohlcv = exchange.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=1000,
                )
                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1

                if len(all_ohlcv) >= 10000:
                    break

            if not all_ohlcv:
                logger.warning(f"No data for {symbol} from {settings.ccxt_exchange}")
                continue

            df = pd.DataFrame(all_ohlcv, columns=["datetime", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
            df = df[df["datetime"] <= pd.Timestamp(end_ts, unit="ms")]

            data[symbol] = df
            logger.info(f"Fetched {len(df)} bars for {symbol}")

        return data

    def _map_timeframe(self, timeframe: str) -> str:
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1wk": "1w",
        }
        return mapping.get(timeframe, "1d")


class CSVProvider(BaseDataProvider):
    """Loads historical data from local CSV files."""

    def fetch(self, settings: BacktestSettings) -> Dict[str, pd.DataFrame]:
        if not settings.csv_path:
            raise ValueError("csv_path must be set for CSV provider")

        data = {}
        csv_path = settings.csv_path

        if os.path.isdir(csv_path):
            for filename in os.listdir(csv_path):
                if filename.endswith(".csv"):
                    symbol = filename.replace(".csv", "").upper()
                    df = pd.read_csv(os.path.join(csv_path, filename))
                    df = self._normalize(df)
                    data[symbol] = df
        else:
            symbol = settings.symbols[0] if settings.symbols else "UNKNOWN"
            df = pd.read_csv(csv_path)
            df = self._normalize(df)
            data[symbol] = df

        return data

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        cols_lower = {c.lower(): c for c in df.columns}
        rename_map = {}
        for std_col in ["open", "high", "low", "close", "volume"]:
            if std_col in cols_lower:
                rename_map[cols_lower[std_col]] = std_col
        df = df.rename(columns=rename_map)

        if "date" in df.columns and "datetime" not in df.columns:
            df = df.rename(columns={"date": "datetime"})

        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"CSV missing columns: {missing}. Found: {list(df.columns)}")

        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime")

        return df


class ParquetProvider(BaseDataProvider):
    """Loads historical data from local Parquet files."""

    def fetch(self, settings: BacktestSettings) -> Dict[str, pd.DataFrame]:
        if not settings.parquet_path:
            raise ValueError("parquet_path must be set for Parquet provider")

        data = {}
        path = settings.parquet_path

        if os.path.isdir(path):
            for filename in os.listdir(path):
                if filename.endswith(".parquet"):
                    symbol = filename.replace(".parquet", "").upper()
                    df = pd.read_parquet(os.path.join(path, filename))
                    data[symbol] = df
        else:
            symbol = settings.symbols[0] if settings.symbols else "UNKNOWN"
            df = pd.read_parquet(path)
            data[symbol] = df

        return data


class HistoricalDataProvider:
    """Unified interface for all historical data providers."""

    PROVIDER_MAP = {
        DataProviderType.YFINANCE: YFinanceProvider,
        DataProviderType.CCXT: CCXTProvider,
        DataProviderType.CSV: CSVProvider,
        DataProviderType.PARQUET: ParquetProvider,
    }

    def __init__(self, settings: BacktestSettings):
        self.settings = settings
        self._provider = self._create_provider()

    def _create_provider(self) -> BaseDataProvider:
        provider_cls = self.PROVIDER_MAP.get(self.settings.data_provider)
        if provider_cls is None:
            raise ValueError(f"Unknown data provider: {self.settings.data_provider}")
        return provider_cls()

    def fetch(self) -> Dict[str, pd.DataFrame]:
        """Fetch raw OHLCV data from the configured source."""
        return self._provider.fetch(self.settings)

    def get_events(self, clock: EventClock) -> List[MarketEvent]:
        """Fetch data and convert to ordered MarketEvent list."""
        data = self.fetch()
        return self._provider.to_market_events(data, clock, self.settings)

    def get_event_iterator(self, clock: EventClock) -> Iterator[MarketEvent]:
        """Yield MarketEvent objects one at a time for streaming replay."""
        data = self.fetch()
        events = self._provider.to_market_events(data, clock, self.settings)
        for event in events:
            yield event
