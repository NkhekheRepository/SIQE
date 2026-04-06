import os
import threading
import resource

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
except ImportError:
    # Create dummy classes for testing when prometheus_client is not available
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self): pass
        def labels(self, **kwargs): return self
    
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, value): pass
        def labels(self, **kwargs): return self
    
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, value): pass
        def labels(self, **kwargs): return self
    
    class Summary:
        def __init__(self, *args, **kwargs): pass
        def observe(self, value): pass
        def labels(self, **kwargs): return self
    
    def generate_latest(): return b""
    CONTENT_TYPE_LATEST = "text/plain"

_gauge_lock = threading.Lock()
_counter_lock = threading.Lock()
_histogram_lock = threading.Lock()
_summary_lock = threading.Lock()

_si_engine_running = None
_si_equity = None
_si_daily_pnl = None
_si_drawdown_pct = None
_si_consecutive_losses = None
_si_queue_depth = None
_si_memory_mb = None
_si_peak_memory_mb = None
_si_active_positions = None
_si_portfolio_exposure = None
_si_circuit_breaker_active = None

_si_events_processed_total = None
_si_events_rejected_total = None
_si_trades_total = None
_si_trades_won_total = None
_si_trades_lost_total = None
_si_reconnect_attempts_total = None
_si_alerts_total = None

_si_pipeline_stage_latency_seconds = None
_si_trade_pnl_distribution = None
_si_websocket_message_latency_ms = None

_si_strategy_confidence = None

_instance = None
_instance_lock = threading.Lock()


def _init_metrics():
    global _si_engine_running, _si_equity, _si_daily_pnl, _si_drawdown_pct
    global _si_consecutive_losses, _si_queue_depth, _si_memory_mb, _si_peak_memory_mb
    global _si_active_positions, _si_portfolio_exposure, _si_circuit_breaker_active
    global _si_events_processed_total, _si_events_rejected_total
    global _si_trades_total, _si_trades_won_total, _si_trades_lost_total
    global _si_reconnect_attempts_total, _si_alerts_total
    global _si_pipeline_stage_latency_seconds, _si_trade_pnl_distribution
    global _si_websocket_message_latency_ms
    global _si_strategy_confidence

    _si_engine_running = Gauge(
        "siqe_engine_running",
        "Whether engine is running (0/1)",
    )
    _si_equity = Gauge(
        "siqe_equity",
        "Current equity",
    )
    _si_daily_pnl = Gauge(
        "siqe_daily_pnl",
        "Daily PnL",
    )
    _si_drawdown_pct = Gauge(
        "siqe_drawdown_pct",
        "Current drawdown percentage",
    )
    _si_consecutive_losses = Gauge(
        "siqe_consecutive_losses",
        "Consecutive loss count",
    )
    _si_queue_depth = Gauge(
        "siqe_queue_depth",
        "Event queue depth",
    )
    _si_memory_mb = Gauge(
        "siqe_memory_mb",
        "Current memory usage in MB",
    )
    _si_peak_memory_mb = Gauge(
        "siqe_peak_memory_mb",
        "Peak memory usage in MB",
    )
    _si_active_positions = Gauge(
        "siqe_active_positions",
        "Number of active positions",
    )
    _si_portfolio_exposure = Gauge(
        "siqe_portfolio_exposure",
        "Total portfolio notional exposure",
    )
    _si_circuit_breaker_active = Gauge(
        "siqe_circuit_breaker_active",
        "Whether any circuit breaker is active (0/1)",
    )

    _si_events_processed_total = Counter(
        "siqe_events_processed_total",
        "Total events processed",
    )
    _si_events_rejected_total = Counter(
        "siqe_events_rejected_total",
        "Total events rejected",
    )
    _si_trades_total = Counter(
        "siqe_trades_total",
        "Total trades executed",
    )
    _si_trades_won_total = Counter(
        "siqe_trades_won_total",
        "Total winning trades",
    )
    _si_trades_lost_total = Counter(
        "siqe_trades_lost_total",
        "Total losing trades",
    )
    _si_reconnect_attempts_total = Counter(
        "siqe_reconnect_attempts_total",
        "Total reconnection attempts",
    )
    _si_alerts_total = Counter(
        "siqe_alerts_total",
        "Total alerts fired",
        labelnames=["alert_type"],
    )

    _si_pipeline_stage_latency_seconds = Histogram(
        "siqe_pipeline_stage_latency_seconds",
        "Latency per pipeline stage",
        labelnames=["stage"],
    )
    _si_trade_pnl_distribution = Histogram(
        "siqe_trade_pnl_distribution",
        "PnL distribution of trades",
        labelnames=["symbol"],
    )
    _si_websocket_message_latency_ms = Histogram(
        "siqe_websocket_message_latency_ms",
        "WebSocket message latency",
        labelnames=["exchange"],
    )

    _si_strategy_confidence = Summary(
        "siqe_strategy_confidence",
        "Strategy confidence scores",
        labelnames=["strategy"],
    )


class MetricsRegistry:
    def __init__(self):
        self._gauge_lock = _gauge_lock
        self._counter_lock = _counter_lock
        self._histogram_lock = _histogram_lock
        self._summary_lock = _summary_lock
        self._peak_memory_mb = 0.0
        _init_metrics()

    def record_event_processed(self):
        with self._counter_lock:
            _si_events_processed_total.inc()

    def record_event_rejected(self):
        with self._counter_lock:
            _si_events_rejected_total.inc()

    def record_trade(self, pnl, symbol):
        with self._counter_lock:
            _si_trades_total.inc()
            if pnl > 0:
                _si_trades_won_total.inc()
            elif pnl < 0:
                _si_trades_lost_total.inc()
        with self._histogram_lock:
            _si_trade_pnl_distribution.labels(symbol=symbol).observe(pnl)

    def record_pipeline_latency(self, stage, seconds):
        with self._histogram_lock:
            _si_pipeline_stage_latency_seconds.labels(stage=stage).observe(seconds)

    def record_ws_latency(self, exchange, ms):
        with self._histogram_lock:
            _si_websocket_message_latency_ms.labels(exchange=exchange).observe(ms)

    def record_alert(self, alert_type):
        with self._counter_lock:
            _si_alerts_total.labels(alert_type=alert_type).inc()

    def update_gauges(self, status_dict):
        gauge_map = {
            "engine_running": _si_engine_running,
            "equity": _si_equity,
            "daily_pnl": _si_daily_pnl,
            "drawdown_pct": _si_drawdown_pct,
            "consecutive_losses": _si_consecutive_losses,
            "queue_depth": _si_queue_depth,
            "memory_mb": _si_memory_mb,
            "peak_memory_mb": _si_peak_memory_mb,
            "active_positions": _si_active_positions,
            "portfolio_exposure": _si_portfolio_exposure,
            "circuit_breaker_active": _si_circuit_breaker_active,
        }
        with self._gauge_lock:
            for key, value in status_dict.items():
                if key in gauge_map and gauge_map[key] is not None:
                    if key == "memory_mb":
                        gauge_map[key].set(value)
                        if value > self._peak_memory_mb:
                            self._peak_memory_mb = value
                            gauge_map["peak_memory_mb"].set(self._peak_memory_mb)
                    else:
                        gauge_map[key].set(value)

    def start_http_server(self, port, addr="0.0.0.0"):
        from prometheus_client import start_http_server as _start
        _start(port=port, addr=addr)


def get_metrics():
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MetricsRegistry()
    return _instance


def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
