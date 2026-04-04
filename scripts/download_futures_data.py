"""
SIQE V3 - Download USDT-M Futures Market Data

Downloads OHLCV data for Binance USDT-M perpetual futures via CCXT
and stores it in the VN.PY SQLite database for futures backtesting.

Usage:
    python scripts/download_futures_data.py                     # BTC 1h, 180 days
    python scripts/download_futures_data.py --symbol ETH        # ETH/USDT
    python scripts/download_futures_data.py --symbol BTC --timeframe 15m
    python scripts/download_futures_data.py --all               # All 6 supported pairs
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ccxt
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import get_database

SUPPORTED_SYMBOLS = {
    "BTC": "BTC/USDT:USDT",
    "ETH": "ETH/USDT:USDT",
    "SOL": "SOL/USDT:USDT",
    "BNB": "BNB/USDT:USDT",
    "XRP": "XRP/USDT:USDT",
    "DOGE": "DOGE/USDT:USDT",
}

TIMEFRAME_MAP = {
    "1m": Interval.MINUTE,
    "3m": Interval.MINUTE,
    "5m": Interval.MINUTE,
    "15m": Interval.MINUTE,
    "30m": Interval.MINUTE,
    "1h": Interval.HOUR,
    "2h": Interval.HOUR,
    "4h": Interval.HOUR,
    "6h": Interval.HOUR,
    "12h": Interval.HOUR,
    "1d": Interval.DAILY,
}

VN_SYMBOL_MAP = {
    "BTC/USDT:USDT": "BTCUSDT_SWAP_BINANCE",
    "ETH/USDT:USDT": "ETHUSDT_SWAP_BINANCE",
    "SOL/USDT:USDT": "SOLUSDT_SWAP_BINANCE",
    "BNB/USDT:USDT": "BNBUSDT_SWAP_BINANCE",
    "XRP/USDT:USDT": "XRPUSDT_SWAP_BINANCE",
    "DOGE/USDT:USDT": "DOGEUSDT_SWAP_BINANCE",
}


def download_futures_ohlcv(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    since_days: int = 180,
    limit: int = 1000,
) -> list[dict]:
    """Download OHLCV data from Binance USDT-M Futures via CCXT."""
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
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

        latest_dt = datetime.fromtimestamp(ohlcv[-1][0] / 1000)
        print(f"  Fetched {len(all_ohlcv)} candles, latest: {latest_dt}")

        if len(ohlcv) < limit:
            break

    print(f"Total candles downloaded: {len(all_ohlcv)}")
    return all_ohlcv


def convert_to_bar_data(
    ohlcv: list[dict],
    vn_symbol: str = "btcusdt",
) -> list[BarData]:
    """Convert CCXT OHLCV to VN.PY BarData objects for futures."""
    exch = Exchange.GLOBAL
    bars = []

    for candle in ohlcv:
        timestamp, open_p, high_p, low_p, close_p, volume = candle
        dt = datetime.fromtimestamp(timestamp / 1000)

        bar = BarData(
            symbol=vn_symbol,
            exchange=exch,
            datetime=dt,
            interval=Interval.HOUR,
            open_price=open_p,
            high_price=high_p,
            low_price=low_p,
            close_price=close_p,
            volume=volume,
            gateway_name="CCXT_FUTURES",
        )
        bars.append(bar)

    return bars


def save_to_vnpy_database(bars: list[BarData]) -> int:
    """Save bars to VN.PY database."""
    database = get_database()
    saved = database.save_bar_data(bars)
    print(f"Saved {saved} bars to VN.PY database")
    return saved


def download_single(
    symbol_key: str = "BTC",
    timeframe: str = "1h",
    since_days: int = 180,
) -> dict:
    """Download and store data for a single futures pair."""
    ccxt_symbol = SUPPORTED_SYMBOLS[symbol_key]
    vn_symbol = VN_SYMBOL_MAP[ccxt_symbol]
    interval = TIMEFRAME_MAP.get(timeframe, Interval.HOUR)

    print(f"\n{'=' * 60}")
    print(f"Downloading {symbol_key}/USDT perpetual futures ({timeframe})")
    print(f"{'=' * 60}")

    ohlcv = download_futures_ohlcv(
        symbol=ccxt_symbol,
        timeframe=timeframe,
        since_days=since_days,
        limit=1000,
    )

    if not ohlcv:
        print(f"ERROR: No data downloaded for {symbol_key}")
        return {"symbol": symbol_key, "status": "FAIL", "bars": 0}

    bars = convert_to_bar_data(ohlcv, vn_symbol=vn_symbol)
    for bar in bars:
        bar.interval = interval

    saved = save_to_vnpy_database(bars)

    if bars:
        first = bars[0]
        last = bars[-1]
        print(f"\nData range:")
        print(f"  First: {first.datetime} - O:{first.open_price:.2f} C:{first.close_price:.2f}")
        print(f"  Last:  {last.datetime} - O:{last.open_price:.2f} C:{last.close_price:.2f}")

    print(f"Ready for futures backtesting with {saved} bars")
    return {"symbol": symbol_key, "status": "OK", "bars": saved}


def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Futures Data Download")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC",
        choices=list(SUPPORTED_SYMBOLS.keys()),
        help="Futures pair to download",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        choices=list(TIMEFRAME_MAP.keys()),
        help="Candle timeframe",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="Number of days of history to download",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all 6 supported futures pairs",
    )
    args = parser.parse_args()

    print("SIQE V3 - USDT-M Futures Market Data Download")
    print("=" * 60)

    if args.all:
        results = []
        for sym in SUPPORTED_SYMBOLS:
            result = download_single(sym, args.timeframe, args.days)
            results.append(result)

        print(f"\n{'=' * 60}")
        print("DOWNLOAD SUMMARY")
        print(f"{'=' * 60}")
        total_bars = 0
        for r in results:
            total_bars += r["bars"]
            status = "OK" if r["status"] == "OK" else "FAIL"
            print(f"  {r['symbol']:6s}: {status} ({r['bars']} bars)")
        print(f"  {'TOTAL':6s}: {total_bars} bars")
        return 0 if all(r["status"] == "OK" for r in results) else 1
    else:
        result = download_single(args.symbol, args.timeframe, args.days)
        return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
