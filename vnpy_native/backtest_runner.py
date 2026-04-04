"""
SIQE V3 - VN.PY Native Backtesting Runner

Runs the SIQE CTA strategy against historical data using VN.PY's
native BacktestingEngine. Supports multiple symbols, parameter
optimization, and JSON/CSV/HTML reporting.
"""
from __future__ import annotations

import json
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.base import BacktestingMode
from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData
from vnpy.trader.database import get_database

from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy


class SiqeBacktestRunner:
    """Wrapper around VN.PY BacktestingEngine for SIQE strategy."""

    def __init__(
        self,
        vt_symbol: str = "btcusdt.BINANCE",
        interval: str = "1h",
        start: str = "2024-01-01",
        end: str = "2024-12-31",
        rate: float = 0.0005,
        slippage: float = 1.0,
        size: int = 1,
        pricetick: float = 0.01,
        capital: float = 10000.0,
        strategy_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Normalize exchange to valid VN.PY enum value
        if "." in vt_symbol:
            symbol_part, exchange_part = vt_symbol.rsplit(".", 1)
            if exchange_part.upper() == "BINANCE":
                vt_symbol = f"{symbol_part}.GLOBAL"
        self.vt_symbol = vt_symbol
        self.interval_map = {
            "1m": Interval.MINUTE,
            "1h": Interval.HOUR,
            "1d": Interval.DAILY,
        }
        self.interval = self.interval_map.get(interval, Interval.HOUR)
        self.start = datetime.fromisoformat(start)
        self.end = datetime.fromisoformat(end)
        self.rate = rate
        self.slippage = slippage
        self.size = size
        self.pricetick = pricetick
        self.capital = capital
        self.strategy_params = strategy_params or {}

        self.engine = BacktestingEngine()
        self._results: Dict[str, Any] = {}
        self._stats: Dict[str, Any] = {}
        self._trades: List[Any] = []

    def setup(self) -> None:
        """Configure the backtesting engine."""
        self.engine.set_parameters(
            vt_symbol=self.vt_symbol,
            interval=self.interval,
            start=self.start,
            end=self.end,
            rate=self.rate,
            slippage=self.slippage,
            size=self.size,
            pricetick=self.pricetick,
            capital=self.capital,
            mode=BacktestingMode.BAR,
        )
        self.engine.add_strategy(SiqeCtaStrategy, setting=self.strategy_params)

    def load_data_from_db(self) -> None:
        """Load historical bars from VN.PY database."""
        self.engine.load_data()

    def load_bars(self, bars: List[BarData]) -> None:
        """Load bars directly (bypass database)."""
        self.engine.history_data = bars

    def run(self) -> Dict[str, Any]:
        """Execute the backtest and compute results."""
        self.engine.run_backtesting()
        df = self.engine.calculate_result()
        self._stats = self.engine.calculate_statistics()
        self._trades = self.engine.get_all_trades()
        self._results = {
            "equity_curve": df.to_dict() if df is not None else {},
            "stats": self._stats,
            "trade_count": len(self._trades),
        }
        return self._results

    def get_stats(self) -> Dict[str, Any]:
        """Return backtest statistics."""
        return self._stats

    def get_trades(self) -> List[Any]:
        """Return all trade fills."""
        return self._trades

    def get_equity_curve(self):
        """Return equity curve dataframe."""
        return self.engine.calculate_result()

    def save_report(self, output_dir: str = "output/backtest") -> Dict[str, str]:
        """Save backtest report as JSON, CSV, and HTML."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON report
        json_path = out / f"backtest_{ts}.json"
        report = {
            "symbol": self.vt_symbol,
            "interval": self.interval.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "capital": self.capital,
            "strategy_params": self.strategy_params,
            "stats": self._stats,
            "trade_count": len(self._trades),
        }
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        # CSV trades
        csv_path = out / f"trades_{ts}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "datetime", "symbol", "direction", "offset",
                "price", "volume", "pnl",
            ])
            for t in self._trades:
                writer.writerow([
                    t.datetime, t.symbol, t.direction.value,
                    t.offset.value, t.price, t.volume,
                    getattr(t, "pnl", 0),
                ])

        # HTML chart
        html_path = out / f"chart_{ts}.html"
        try:
            fig = self.engine.show_chart()
            fig.write_html(str(html_path))
        except Exception:
            html_path = None

        paths = {"json": str(json_path), "csv": str(csv_path)}
        if html_path:
            paths["html"] = str(html_path)
        return paths

    def optimize(
        self,
        param_ranges: Dict[str, tuple],
        target: str = "sharpe_ratio",
        mode: str = "bf",
    ) -> List[Dict[str, Any]]:
        """
        Run parameter optimization.

        param_ranges: {"param_name": (start, end, step)}
        mode: "bf" for brute-force, "ga" for genetic algorithm
        """
        from vnpy.trader.optimize import OptimizationSetting

        opt_setting = OptimizationSetting()
        opt_setting.set_target(target)

        for name, (start, end, step) in param_ranges.items():
            opt_setting.add_parameter(name, start, end, step)

        if mode == "ga":
            results = self.engine.run_ga_optimization(
                opt_setting, pop_size=100, ngen=30
            )
        else:
            results = self.engine.run_bf_optimization(opt_setting)

        return results


def run_backtest_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function: run a backtest from a config dict.

    Example config:
    {
        "vt_symbol": "btcusdt.BINANCE",
        "interval": "1h",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "rate": 0.0005,
        "slippage": 1.0,
        "size": 1,
        "pricetick": 0.01,
        "capital": 10000,
        "strategy_params": {"fixed_size": 1, "mr_boll_period": 20},
        "output_dir": "output/backtest",
    }
    """
    runner = SiqeBacktestRunner(
        vt_symbol=config.get("vt_symbol", "btcusdt.BINANCE"),
        interval=config.get("interval", "1h"),
        start=config.get("start", "2024-01-01"),
        end=config.get("end", "2024-12-31"),
        rate=config.get("rate", 0.0005),
        slippage=config.get("slippage", 1.0),
        size=config.get("size", 1),
        pricetick=config.get("pricetick", 0.01),
        capital=config.get("capital", 10000.0),
        strategy_params=config.get("strategy_params", {}),
    )
    runner.setup()
    runner.load_data_from_db()
    runner.run()
    output_dir = config.get("output_dir", "output/backtest")
    paths = runner.save_report(output_dir)
    return {
        "stats": runner.get_stats(),
        "trade_count": runner.get_stats().get("trade_count", 0),
        "output_paths": paths,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    config = {
        "vt_symbol": "btcusdt.BINANCE",
        "interval": "1h",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "rate": 0.0005,
        "slippage": 1.0,
        "size": 1,
        "pricetick": 0.01,
        "capital": 10000.0,
        "strategy_params": {
            "fixed_size": 1,
            "mr_boll_period": 20,
            "mom_fast_period": 10,
            "mom_slow_period": 30,
            "bo_donchian_period": 20,
        },
        "output_dir": "output/backtest",
    }

    result = run_backtest_from_config(config)
    print(json.dumps(result["stats"], indent=2, default=str))
