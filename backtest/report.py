"""
Report Generator
Produces JSON (always), CSV trade log (always), and optional HTML report.
"""
import json
import csv
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backtest.engine import BacktestResult
from backtest.walk_forward import WalkForwardSummary

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates backtest output reports."""

    def __init__(self, output_dir: str = "./backtest_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(
        self,
        result: BacktestResult,
        generate_html: bool = False,
        wf_summary: Optional[WalkForwardSummary] = None,
    ) -> Dict[str, str]:
        """Generate all report files. Returns dict of format -> filepath."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        paths = {}

        paths["json"] = self._write_json(result, timestamp, wf_summary)
        paths["csv"] = self._write_csv(result, timestamp)

        if generate_html:
            try:
                paths["html"] = self._write_html(result, timestamp)
            except Exception as e:
                logger.warning(f"HTML report generation failed: {e}")
                paths["html"] = ""

        logger.info(f"Reports written to {self.output_dir}: {list(paths.keys())}")
        return paths

    def _write_json(
        self,
        result: BacktestResult,
        timestamp: str,
        wf_summary: Optional[WalkForwardSummary] = None,
    ) -> str:
        path = os.path.join(self.output_dir, f"backtest_{timestamp}.json")

        output = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "seed": result.seed,
                "data_source": result.data_source,
                "run_time_seconds": result.run_time_seconds,
                "bars_analyzed": result.bars_analyzed,
            },
            "settings": result.settings,
            "config": result.config,
            "metrics": self._metrics_to_dict(result.metrics),
            "trades": result.trades,
            "parameter_updates": result.parameter_updates,
            "kill_triggered": result.kill_triggered,
            "kill_reason": result.kill_reason,
        }

        if wf_summary is not None:
            output["walk_forward"] = self._wf_summary_to_dict(wf_summary)

        with open(path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return path

    def _write_csv(self, result: BacktestResult, timestamp: str) -> str:
        path = os.path.join(self.output_dir, f"trades_{timestamp}.csv")

        if not result.trades:
            with open(path, "w") as f:
                f.write("No trades executed\n")
            return path

        fieldnames = list(result.trades[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.trades)

        return path

    def _write_html(self, result: BacktestResult, timestamp: str) -> str:
        path = os.path.join(self.output_dir, f"report_{timestamp}.html")

        m = result.metrics
        metrics_html = self._render_metrics_table(m)
        equity_html = self._render_equity_chart(m.equity_curve)
        drawdown_html = self._render_drawdown_chart(m.drawdown_curve)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SIQE V3 Backtest Report</title>
    <style>
        body {{ font-family: -apple-system, monospace; max-width: 1200px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #e0e0e0; }}
        h1 {{ color: #00d4ff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }}
        h2 {{ color: #00ff88; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #16213e; color: #00d4ff; }}
        tr:hover {{ background: #16213e; }}
        .positive {{ color: #00ff88; }}
        .negative {{ color: #ff4444; }}
        .chart {{ background: #16213e; padding: 20px; border-radius: 8px; margin: 15px 0; }}
        .bar {{ display: inline-block; background: #00d4ff; margin: 1px 0; min-height: 3px; }}
        .bar.positive {{ background: #00ff88; }}
        .bar.negative {{ background: #ff4444; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
        .card {{ background: #16213e; padding: 15px; border-radius: 8px; }}
        .card .label {{ color: #888; font-size: 0.85em; }}
        .card .value {{ font-size: 1.5em; font-weight: bold; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>SIQE V3 Backtest Report</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Seed: {result.seed} | Data: {result.data_source}</p>

    <h2>Key Metrics</h2>
    {metrics_html}

    <h2>Equity Curve</h2>
    {equity_html}

    <h2>Drawdown Curve</h2>
    {drawdown_html}

    <h2>Trade Log ({len(result.trades)} trades)</h2>
    {self._render_trade_table(result.trades)}
</body>
</html>"""

        with open(path, "w") as f:
            f.write(html)

        return path

    def _render_metrics_table(self, m) -> str:
        rows = [
            ("Total Return", f"{m.total_return_pct:.2f}%", m.total_return_pct >= 0),
            ("Sharpe Ratio", f"{m.sharpe_ratio:.3f}", m.sharpe_ratio > 0),
            ("Sortino Ratio", f"{m.sortino_ratio:.3f}", m.sortino_ratio > 0),
            ("Calmar Ratio", f"{m.calmar_ratio:.3f}", m.calmar_ratio > 0),
            ("Max Drawdown", f"{m.max_drawdown:.2%}", False),
            ("Win Rate", f"{m.win_rate:.1%}", m.win_rate > 0.5),
            ("Profit Factor", f"{m.profit_factor:.2f}", m.profit_factor > 1),
            ("Total Trades", str(m.total_trades), True),
            ("Avg Win", f"${m.avg_win:.2f}", True),
            ("Avg Loss", f"${m.avg_loss:.2f}", False),
            ("Max Consec. Wins", str(m.max_consecutive_wins), True),
            ("Max Consec. Losses", str(m.max_consecutive_losses), False),
            ("Avg Slippage", f"{m.avg_slippage_bps:.1f} bps", m.avg_slippage_bps < 20),
            ("Final Equity", f"${m.final_equity:,.2f}", m.final_equity >= m.initial_equity),
        ]

        cells = ""
        for label, value, positive in rows:
            cls = "positive" if positive else "negative"
            cells += f'<div class="card"><div class="label">{label}</div><div class="value {cls}">{value}</div></div>'

        return f'<div class="grid">{cells}</div>'

    def _render_equity_chart(self, equity_curve: list) -> str:
        if not equity_curve:
            return '<div class="chart">No data</div>'

        max_eq = max(equity_curve)
        min_eq = min(equity_curve)
        range_eq = max_eq - min_eq if max_eq != min_eq else 1

        bars = ""
        for eq in equity_curve[::max(1, len(equity_curve) // 100)]:
            height = max(2, int(((eq - min_eq) / range_eq) * 50))
            color = "positive" if eq >= equity_curve[0] else "negative"
            bars += f'<div class="bar {color}" style="height:{height}px;width:4px;"></div>'

        return f'<div class="chart" style="display:flex;align-items:flex-end;height:60px;gap:1px;">{bars}</div>'

    def _render_drawdown_chart(self, dd_curve: list) -> str:
        if not dd_curve:
            return '<div class="chart">No data</div>'

        max_dd = max(dd_curve)
        bars = ""
        for dd in dd_curve[::max(1, len(dd_curve) // 100)]:
            height = max(2, int((dd / max(max_dd, 0.01)) * 50))
            bars += f'<div class="bar negative" style="height:{height}px;width:4px;"></div>'

        return f'<div class="chart" style="display:flex;align-items:flex-end;height:60px;gap:1px;">{bars}</div>'

    def _render_trade_table(self, trades: list) -> str:
        if not trades:
            return "<p>No trades</p>"

        header = "<tr><th>#</th><th>Symbol</th><th>Type</th><th>Entry</th><th>Exit</th><th>Size</th><th>PnL</th><th>Slip</th><th>Strategy</th><th>Regime</th></tr>"
        rows = ""
        for i, t in enumerate(trades[:100], 1):
            pnl_cls = "positive" if t.get("pnl", 0) >= 0 else "negative"
            rows += (
                f"<tr><td>{i}</td><td>{t.get('symbol','')}</td>"
                f"<td>{t.get('signal_type','')}</td>"
                f"<td>{t.get('entry_price',0):.2f}</td>"
                f"<td>{t.get('exit_price',0):.2f}</td>"
                f"<td>{t.get('size',0):.4f}</td>"
                f"<td class='{pnl_cls}'>{t.get('pnl',0):.2f}</td>"
                f"<td>{t.get('slippage',0):.4f}</td>"
                f"<td>{t.get('strategy','')}</td>"
                f"<td>{t.get('regime','')}</td></tr>"
            )

        if len(trades) > 100:
            rows += f"<tr><td colspan='10'>... and {len(trades) - 100} more trades (see CSV)</td></tr>"

        return f"<table>{header}{rows}</table>"

    def _metrics_to_dict(self, metrics) -> Dict[str, Any]:
        result = {}
        for key in dir(metrics):
            if key.startswith("_"):
                continue
            val = getattr(metrics, key)
            if isinstance(val, (int, float, str, bool, list, dict)):
                result[key] = val
        return result

    def _wf_summary_to_dict(self, summary) -> Dict[str, Any]:
        return {
            "avg_test_sharpe": summary.avg_test_sharpe,
            "avg_test_return": summary.avg_test_return,
            "avg_overfit_ratio": summary.avg_overfit_ratio,
            "consistent_windows": summary.consistent_windows,
            "total_windows": summary.total_windows,
            "windows": [
                {
                    "window_id": w.window_id,
                    "train_period": f"{w.train_start} -> {w.train_end}",
                    "test_period": f"{w.test_start} -> {w.test_end}",
                    "train_sharpe": w.train_result.metrics.sharpe_ratio if w.train_result else None,
                    "test_sharpe": w.test_result.metrics.sharpe_ratio if w.test_result else None,
                    "overfit_ratio": w.overfit_ratio,
                }
                for w in summary.windows
            ],
        }
