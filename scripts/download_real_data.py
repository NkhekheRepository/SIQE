"""
SIQE V3 - Download real market data and load into VN.PY database

Downloads OHLCV data via CCXT from Binance and stores it in the
VN.PY SQLite database for native backtesting.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import ccxt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import get_database


def download_binance_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    since_days: int = 180,
    limit: int = 1000,
) -> list[dict]:
    """Download OHLCV data from Binance via CCXT."""
    exchange = ccxt.binance({
        "enableRateLimit": True,
    })

    since_ms = exchange.parse8601(
        (datetime.now() - timedelta(days=since_days)).isoformat()
    )

    all_ohlcv = []
    print(f"Downloading {symbol} {timeframe} data for last {since_days} days...")

    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)
        since_ms = ohlcv[-1][0] + 1

        print(f"  Fetched {len(all_ohlcv)} candles, latest: {datetime.fromtimestamp(ohlcv[-1][0] / 1000)}")

        if len(ohlcv) < limit:
            break

    print(f"Total candles downloaded: {len(all_ohlcv)}")
    return all_ohlcv


def convert_to_bar_data(
    ohlcv: list[dict],
    symbol: str = "btcusdt",
    exchange: str = "BINANCE",
) -> list[BarData]:
    """Convert CCXT OHLCV to VN.PY BarData objects."""
    exch = Exchange.GLOBAL
    bars = []

    for candle in ohlcv:
        timestamp, open_p, high_p, low_p, close_p, volume = candle
        dt = datetime.fromtimestamp(timestamp / 1000)

        bar = BarData(
            symbol=symbol,
            exchange=exch,
            datetime=dt,
            interval=Interval.HOUR,
            open_price=open_p,
            high_price=high_p,
            low_price=low_p,
            close_price=close_p,
            volume=volume,
            gateway_name="CCXT",
        )
        bars.append(bar)

    return bars


def save_to_vnpy_database(bars: list[BarData]) -> int:
    """Save bars to VN.PY database."""
    database = get_database()
    saved = database.save_bar_data(bars)
    print(f"Saved {saved} bars to VN.PY database")
    return saved


def main():
    """Download real BTC/USDT data and load into VN.PY."""
    print("SIQE V3 - Real Market Data Download")
    print("=" * 60)

    # Download from Binance
    ohlcv = download_binance_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        since_days=180,
        limit=1000,
    )

    if not ohlcv:
        print("ERROR: No data downloaded")
        return False

    # Convert to BarData
    bars = convert_to_bar_data(ohlcv, symbol="btcusdt")
    print(f"Converted {len(bars)} bars to VN.PY format")

    # Save to database
    saved = save_to_vnpy_database(bars)

    # Show sample
    if bars:
        first = bars[0]
        last = bars[-1]
        print(f"\nData range:")
        print(f"  First: {first.datetime} - O:{first.open_price:.2f} H:{first.high_price:.2f} L:{first.low_price:.2f} C:{first.close_price:.2f}")
        print(f"  Last:  {last.datetime} - O:{last.open_price:.2f} H:{last.high_price:.2f} L:{last.low_price:.2f} C:{last.close_price:.2f}")

    print(f"\nReady for backtesting with {saved} bars in VN.PY database")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
