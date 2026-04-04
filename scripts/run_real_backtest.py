"""
SIQE V3 - Real Data Backtest Runner

Runs the SIQE CTA strategy against real BTC/USDT data from the VN.PY database.
"""
from __future__ import annotations

import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.base import BacktestingMode
from vnpy.trader.constant import Interval

from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy


def run_real_data_backtest():
    """Backtest SIQE CTA strategy with real BTC/USDT data from database."""
    print("SIQE V3 - Real Data Backtest")
    print("=" * 60)

    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbol="btcusdt.GLOBAL",
        interval=Interval.HOUR,
        start=datetime(2025, 10, 1),
        end=datetime(2026, 4, 4),
        rate=0.0005,
        slippage=5.0,
        size=1,
        pricetick=0.01,
        capital=10000.0,
        mode=BacktestingMode.BAR,
    )

    engine.add_strategy(SiqeCtaStrategy, setting={
        "fixed_volume": 0.01,
        "mr_boll_period": 20,
        "mr_boll_dev": 2.0,
        "mr_rsi_period": 14,
        "mom_fast_period": 10,
        "mom_slow_period": 30,
        "bo_donchian_period": 20,
        "bo_atr_period": 14,
        "bo_atr_multiplier": 2.0,
        "atr_stop_multiplier": 2.0,
        "atr_trailing_multiplier": 1.5,
    })

    print("Loading real market data from database...")
    engine.load_data()

    print("Running backtest...")
    engine.run_backtesting()

    df = engine.calculate_result()
    stats = engine.calculate_statistics()
    trades = engine.get_all_trades()

    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)

    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    print(f"\n  Total trades: {len(trades)}")

    if trades:
        wins = [t for t in trades if hasattr(t, "pnl") and t.pnl > 0]
        losses = [t for t in trades if hasattr(t, "pnl") and t.pnl <= 0]
        print(f"  Winning trades: {len(wins)}")
        print(f"  Losing trades: {len(losses)}")
        if wins:
            avg_win = sum(t.pnl for t in wins) / len(wins)
            print(f"  Avg win: {avg_win:.2f}")
        if losses:
            avg_loss = sum(t.pnl for t in losses) / len(losses)
            print(f"  Avg loss: {avg_loss:.2f}")

    # Save report
    output_dir = Path("output/backtest_real")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = {
        "symbol": "btcusdt.GLOBAL",
        "interval": "1h",
        "start": "2025-10-01",
        "end": "2026-04-04",
        "capital": 10000.0,
        "stats": {k: str(v) for k, v in stats.items()},
        "trade_count": len(trades),
    }

    json_path = output_dir / f"real_backtest_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved: {json_path}")

    # Save trades CSV
    import csv
    csv_path = output_dir / f"real_trades_{ts}.csv"
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

    return stats, trades


if __name__ == "__main__":
    stats, trades = run_real_data_backtest()
