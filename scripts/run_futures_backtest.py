"""
SIQE V3 - Futures Backtest Runner

Runs the SiqeFuturesStrategy against USDT-M perpetual futures data
from the VN.PY database with configurable leverage.

Usage:
    python scripts/run_futures_backtest.py                     # BTC, 50x leverage
    python scripts/run_futures_backtest.py --symbol ETH        # ETH/USDT
    python scripts/run_futures_backtest.py --leverage 75       # 75x leverage
    python scripts/run_futures_backtest.py --all               # Backtest all 6 pairs
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.base import BacktestingMode
from vnpy.trader.constant import Interval

from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy

SUPPORTED_SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt", "dogeusdt"]


def run_futures_backtest(
    symbol: str = "btcusdt",
    leverage: int = 50,
    start_date: str = "2025-10-01",
    end_date: str = "2026-04-04",
    capital: float = 10000.0,
    interval: Interval = Interval.MINUTE15,
    rate: float = 0.0004,
    slippage: float = 2.0,
    size: int = 1,
    pricetick: float = 0.01,
) -> tuple[dict, list]:
    """Backtest SiqeFuturesStrategy with real data from database."""
    print(f"SIQE V3 - Futures Backtest: {symbol.upper()} @ {leverage}x")
    print("=" * 60)

    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbol=f"{symbol}.GLOBAL",
        interval=interval,
        start=datetime.strptime(start_date, "%Y-%m-%d"),
        end=datetime.strptime(end_date, "%Y-%m-%d"),
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital,
        mode=BacktestingMode.BAR,
    )

    engine.add_strategy(SiqeFuturesStrategy, setting={
        "leverage": leverage,
        "risk_pct": 0.02,
        "margin_alert_pct": 0.70,
        "margin_stop_pct": 0.90,
        "atr_stop_multiplier": 1.0,
        "atr_trailing_multiplier": 0.75,
        "mr_boll_period": 20,
        "mr_boll_dev": 1.8,
        "mr_rsi_period": 14,
        "mr_rsi_lower": 25.0,
        "mr_rsi_upper": 75.0,
        "mom_fast_period": 10,
        "mom_slow_period": 30,
        "bo_donchian_period": 20,
        "bo_atr_period": 14,
        "bo_atr_multiplier": 2.0,
        "bo_confirmation_bars": 1,
    })

    print("Loading futures market data from database...")
    engine.load_data()

    print("Running backtest...")
    engine.run_backtesting()

    df = engine.calculate_result()
    stats = engine.calculate_statistics()
    trades = engine.get_all_trades()

    print(f"\n{'=' * 60}")
    print(f"BACKTEST RESULTS - {symbol.upper()} ({leverage}x)")
    print(f"{'=' * 60}")

    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print(f"\n  Total trades: {len(trades)}")

    # Use daily results for win/loss since TradeData has no pnl attribute
    daily_results = getattr(engine, "daily_results", {})
    if daily_results:
        profit_days = [d for d in daily_results.values() if d.net_pnl > 0]
        loss_days = [d for d in daily_results.values() if d.net_pnl < 0]
        print(f"  Profit days: {len(profit_days)}")
        print(f"  Loss days: {len(loss_days)}")
        if profit_days:
            avg_win = sum(d.net_pnl for d in profit_days) / len(profit_days)
            print(f"  Avg profit day: {avg_win:.2f}")
        if loss_days:
            avg_loss = sum(d.net_pnl for d in loss_days) / len(loss_days)
            print(f"  Avg loss day: {avg_loss:.2f}")

    return stats, trades


def save_report(
    symbol: str,
    leverage: int,
    stats: dict,
    trades: list,
    start_date: str,
    end_date: str,
    capital: float,
) -> tuple[Path, Path]:
    """Save backtest report and trades to output directory."""
    output_dir = Path("output/backtest_futures")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = {
        "symbol": f"{symbol}.GLOBAL",
        "leverage": leverage,
        "interval": "1h",
        "start": start_date,
        "end": end_date,
        "capital": capital,
        "stats": {k: str(v) for k, v in stats.items()},
        "trade_count": len(trades),
    }

    json_path = output_dir / f"futures_{symbol}_{leverage}x_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved: {json_path}")

    csv_path = output_dir / f"futures_{symbol}_{leverage}x_trades_{ts}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "symbol", "direction", "offset", "price", "volume", "pnl"])
        for t in trades:
            writer.writerow([
                t.datetime, t.symbol, t.direction.value,
                t.offset.value, t.price, t.volume,
                getattr(t, "pnl", 0),
            ])
    print(f"Trades saved: {csv_path}")

    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Futures Backtest")
    parser.add_argument(
        "--symbol",
        type=str,
        default="btcusdt",
        choices=SUPPORTED_SYMBOLS,
        help="Futures pair to backtest",
    )
    parser.add_argument(
        "--leverage",
        type=int,
        default=50,
        choices=range(35, 76),
        metavar="35-75",
        help="Leverage (35-75x)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2025-10-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2026-04-04",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Starting capital",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Backtest all 6 supported futures pairs",
    )
    args = parser.parse_args()

    if args.all:
        results = []
        for sym in SUPPORTED_SYMBOLS:
            print(f"\n{'=' * 60}")
            stats, trades = run_futures_backtest(
                symbol=sym,
                leverage=args.leverage,
                start_date=args.start,
                end_date=args.end,
                capital=args.capital,
            )
            save_report(sym, args.leverage, stats, trades, args.start, args.end, args.capital)
            results.append({
                "symbol": sym,
                "total_return": stats.get("total_return", 0),
                "max_drawdown": stats.get("max_drawdown", 0),
                "sharpe_ratio": stats.get("sharpe_ratio", 0),
                "trade_count": len(trades),
            })

        print(f"\n{'=' * 60}")
        print("FUTURES BACKTEST SUMMARY (ALL PAIRS)")
        print(f"{'=' * 60}")
        print(f"  {'Symbol':<10} {'Return':>10} {'Max DD':>10} {'Sharpe':>10} {'Trades':>8}")
        print(f"  {'-' * 50}")
        for r in results:
            print(f"  {r['symbol'].upper():<10} {r['total_return']:>9.2%} {r['max_drawdown']:>9.2%} {r['sharpe_ratio']:>10.4f} {r['trade_count']:>8d}")
    else:
        stats, trades = run_futures_backtest(
            symbol=args.symbol,
            leverage=args.leverage,
            start_date=args.start,
            end_date=args.end,
            capital=args.capital,
        )
        save_report(args.symbol, args.leverage, stats, trades, args.start, args.end, args.capital)

    return 0


if __name__ == "__main__":
    sys.exit(main())
