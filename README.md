# SIQE V3 — Self-Improving Quant Engine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SIQE V3 ARCHITECTURE                           │
│                     Deterministic · Event-Driven · Risk-Constrained          │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Market Data │────▶│  Regime      │────▶│  Strategy    │────▶│  EV          │
│  Feeds       │     │  Engine      │     │  Engine      │     │  Calculator  │
└──────────────┘     │  (detect)    │     │  (signals)   │     │  (score)     │
                     └──────────────┘     └──────────────┘     └──────────────┘
                                                                    │
┌──────────────┐     ┌──────────────┐     ┌──────────────┐          ▼
│  Feedback    │◀────│  Execution   │◀────│  Risk        │◀────┌──────────────┐
│  Loop        │     │  Adapter     │     │  Engine      │     │  Decision    │
│  (learn)     │     │  (VN.PY)     │     │  (validate)  │     │  Engine      │
└──────┬───────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                                                              │
       ▼                                                              ▼
┌──────────────┐                               ┌──────────────┐
│  Learning    │                               │  Meta        │
│  Engine      │                               │  Harness     │
│  (update)    │                               │  (govern)    │
└──────────────┘                               └──────────────┘
       │                                              ▲
       ▼                                              │
┌──────────────┐                               ┌──────────────┐
│  State       │◀──────────────────────────────┘              │
│  Manager     │                                              │
│  (persist)   │                                              │
└──────────────┘                                              │
                                                              │
                     ◀────────────────────────────────────────┘
                     on_market_event(event) — SOLE ENTRY POINT
```

## Pipeline Wiring Diagram

```
EventClock (seq) ─────────────────────────────────────────────────────────┐
    │                                                                     │
    ▼                                                                     ▼
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Regime  │──▶│Strategy │──▶│   EV    │──▶│Decision │──▶│  Meta   │
│ detect  │   │ signals │   │  calc   │   │  pick   │   │approve  │
│ 1 stage │   │ N stages│   │ 1 stage │   │ 1 stage │   │ 1 stage │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
                                                      │
                                    ┌─────────────────┘
                                    ▼
                            ┌───────────────┐   ┌───────────────┐
                            │    Risk       │──▶│  Execution    │
                            │  validate     │   │   adapter     │
                            │  1 stage      │   │   1 stage     │
                            └───────────────┘   └───────┬───────┘
                                                        │
                                                        ▼
                                                ┌───────────────┐
                                                │   Feedback    │
                                                │   Loop        │
                                                └───────┬───────┘
                                                        │
                                                        ▼
                                                ┌───────────────┐
                                                │   Learning    │
                                                │   (every N)   │
                                                └───────────────┘
```

## System State Machine

```
                    ┌──────────────┐
                    │ INITIALIZING │
                    └──────┬───────┘
                           │ initialize()
                           ▼
                    ┌──────────────┐◀──────────────────────┐
              ┌────▶│   NORMAL     │                       │
              │     └──────┬───────┘                       │
              │            │ drawdown >= 15%               │ resume()
              │            ▼                               │
              │     ┌──────────────┐                       │
              │     │  DEGRADED    │───────────────────────┘
              │     └──────┬───────┘
              │            │ kill condition triggered
              │            ▼
              │     ┌──────────────┐
              │     │  CRITICAL    │
              │     └──────┬───────┘
              │            │ manual halt
              │            ▼
              │     ┌──────────────┐
              └─────│   HALTED     │
                    └──────┬───────┘
                           │ shutdown()
                           ▼
                    ┌──────────────┐
                    │  SHUTDOWN    │
                    └──────────────┘
```

---

## Table of Contents

1. [Overview](#overview)
2. [6-Layer Architecture](#6-layer-architecture)
3. [Determinism Guarantees](#determinism-guarantees)
4. [Fault Tolerance](#fault-tolerance-mechanisms)
5. [Data Contracts](#data-contracts)
6. [Configuration (69 Parameters)](#configuration-parameters)
7. [API Endpoints](#api-endpoints)
8. [Backtesting Engine](#backtesting-engine)
9. [Quick Start](#quick-start)
10. [Testing](#testing)
11. [SWOT Analysis](#swot-analysis)
12. [Docker Deployment](#docker-deployment)
13. [Project Structure](#project-structure)

---

## Overview

SIQE V3 is a **deterministic, event-driven, risk-constrained** trading system built for production quantitative trading. It replaces all wall-clock time and UUID dependencies with a monotonic event clock, enforces strict immutability through frozen dataclasses, and guarantees that identical inputs produce identical outputs across runs.

**Key Properties:**
- **Sole entry point**: `async def on_market_event(event: dict)` — no other component may trigger trades
- **Deterministic**: Seeded RNG (`random.seed(0)`, `np.random.seed(0)`), `PYTHONHASHSEED=0`, EventClock replaces `datetime.now()`, IDGenerator replaces `uuid.uuid4()`
- **Risk-constrained**: Hard constraint risk engine + kill switch (drawdown >= 20%, consecutive losses >= 5, PnL anomaly detection)
- **Self-improving**: Learning engine with stability guards, parameter versioning, and rollback capability
- **Event-driven**: Bounded queue with backpressure, semaphore-controlled concurrency, per-stage timeouts and retries

---

## 6-Layer Architecture

### Layer 1: Data & Contracts
Immutable, validated dataclasses that define every object flowing through the pipeline. No `Dict[str, Any]` allowed.

| Component | File | Responsibility |
|-----------|------|----------------|
| Data Contracts | `models/trade.py` | 10 frozen dataclasses + 4 enums |
| Event Clock | `core/clock.py` | Monotonic deterministic sequencing |
| Retry Logic | `core/retry.py` | Bounded exponential backoff |
| Data Engine | `core/data_engine.py` | Market data acquisition (mock/real) |

### Layer 2: Signal Generation
Strategies generate trading signals based on market events and regime context.

| Component | File | Responsibility |
|-----------|------|----------------|
| Strategy Engine | `strategy_engine/strategy_base.py` | Mean reversion, momentum, breakout strategies |
| Regime Engine | `regime/regime_engine.py` | Detects TRENDING/RANGING/VOLATILE/MIXED regimes |

### Layer 3: Evaluation & Decision
Signals are scored for expected value, then the best candidate is selected.

| Component | File | Responsibility |
|-----------|------|----------------|
| EV Engine | `ev_engine/ev_calculator.py` | Expected value calculation with regime scaling |
| Decision Engine | `decision_engine/decision_maker.py` | Selects highest-EV actionable trade |

### Layer 4: Governance & Risk
Meta-governance validates trades; hard risk constraints enforce capital protection.

| Component | File | Responsibility |
|-----------|------|----------------|
| Meta Harness | `meta_harness/meta_governor.py` | System state management, kill switch, override |
| Risk Engine | `risk_engine/risk_manager.py` | Position size, drawdown, daily loss, hourly limits |

### Layer 5: Execution & Feedback
Trades are executed through the VN.PY bridge (mock or real) and results are fed back.

| Component | File | Responsibility |
|-----------|------|----------------|
| Execution Adapter | `execution_adapter/vnpy_bridge.py` | VN.PY bridge with mock fallback, retry, partial fills |
| Feedback Loop | `feedback/feedback_loop.py` | PnL decomposition, performance tracking |

### Layer 6: Learning & State
The system learns from outcomes and persists state for recovery.

| Component | File | Responsibility |
|-----------|------|----------------|
| Learning Engine | `learning/learning_engine.py` | Parameter updates, stability guards, rollback |
| State Manager | `memory/state_manager.py` | Persistent state save/load/restore |
| API Layer | `api/main.py` | FastAPI REST interface for control and observability |

---

## Determinism Guarantees

| Mechanism | Implementation | Guarantee |
|-----------|----------------|-----------|
| Event Clock | `EventClock` replaces all `datetime.now()` | No wall-clock dependency |
| ID Generator | `IDGenerator(prefix, clock)` replaces `uuid.uuid4()` | Reproducible IDs from sequence |
| Seeded RNG | `random.seed(0)`, `np.random.seed(0)` at init | Identical random sequences |
| Hash Seed | `PYTHONHASHSEED=0` in Dockerfile | Deterministic dict ordering |
| Frozen Dataclasses | `@dataclass(frozen=True)` on all contracts | Immutability at construction |
| PnL Invariant | `signal_alpha + execution_alpha + noise == total_pnl` | Validated in `__post_init__` |
| Stage Ordering | Strict 11-stage pipeline (regime -> strategy -> EV -> decision -> meta -> risk -> execution -> feedback) | No out-of-order processing |
| Queue Bounded | `asyncio.Queue(maxsize=max_queue_size)` with backpressure | No unbounded memory growth |
| Concurrency Limited | `asyncio.Semaphore(max_concurrent_events)` | Controlled parallelism |
| Timeout Per Stage | `asyncio.wait_for(..., timeout=stage_timeout)` | No stage hangs indefinitely |

---

## Fault Tolerance Mechanisms

| Mechanism | Trigger | Action |
|-----------|---------|--------|
| Bounded Retry | Stage failure | Exponential backoff (base_delay * 2^attempt), max 3 retries |
| Stage Timeout | Stage exceeds `stage_timeout` | Pipeline aborts, event rejected, logged |
| Queue Backpressure | Queue at capacity | Event rejected, `total_events_rejected` incremented |
| Kill Switch | Drawdown >= 20% | System state -> CRITICAL, override active, all trades blocked |
| Kill Switch | Consecutive losses >= 5 | System state -> CRITICAL, override active |
| Kill Switch | PnL deviation anomaly (>= 50% deviation over 10 trades) | System state -> CRITICAL |
| Degraded State | Drawdown >= 15% | System state -> DEGRADED, trading continues with caution |
| VN.PY Fallback | VN.PY not installed or connection fails | Automatic fallback to MockVNpyBridge |
| State Persistence | Shutdown / periodic | Risk engine + meta harness state saved to disk |
| State Restoration | Startup | Previous state restored to risk engine, strategy engine, meta harness |
| Memory Tracking | `tracemalloc` | Current and peak memory logged at shutdown |
| Structured Logging | All events | JSON-structured logs via loguru intercept |

---

## Data Contracts

All data flowing through the pipeline is typed, validated, and immutable (frozen dataclasses).

### 1. MarketEvent
Incoming market data event.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | str | Unique event identifier |
| `symbol` | str | Trading pair (e.g., BTCUSDT) |
| `bid` | float | Bid price |
| `ask` | float | Ask price |
| `volume` | float | Trading volume |
| `volatility` | float | Current volatility measure |
| `event_seq` | int | Deterministic sequence number |

**Computed property**: `mid_price = (bid + ask) / 2.0`

### 2. Signal
Trading signal generated by a strategy.

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | str | Unique signal identifier |
| `symbol` | str | Trading pair |
| `signal_type` | SignalType | LONG / SHORT / NONE |
| `strength` | float | Signal strength [0.0, 1.0] |
| `price` | float | Reference price (must be > 0) |
| `strategy` | str | Strategy name |
| `reason` | str | Human-readable reason |
| `event_seq` | int | Sequence number |
| `regime` | Optional[str] | Current regime (optional) |
| `regime_confidence` | float | Regime detection confidence |

### 3. EVResult
Expected value calculation for a signal.

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | str | Reference to source signal |
| `symbol` | str | Trading pair |
| `signal_type` | SignalType | LONG / SHORT / NONE |
| `strength` | float | Signal strength |
| `price` | float | Reference price |
| `strategy` | str | Strategy name |
| `ev_score` | float | Calculated expected value |
| `actionable` | bool | Whether EV exceeds threshold |
| `event_seq` | int | Sequence number |
| `regime` | Optional[str] | Current regime |
| `regime_confidence` | float | Regime confidence |

### 4. Decision
Final trading decision after EV evaluation.

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | str | Unique decision identifier |
| `signal_id` | str | Reference to source signal |
| `symbol` | str | Trading pair |
| `signal_type` | SignalType | LONG / SHORT / NONE |
| `strength` | float | Signal strength |
| `price` | float | Reference price |
| `strategy` | str | Strategy name |
| `ev_score` | float | Expected value score |
| `confidence` | float | Decision confidence [0.0, 1.0] |
| `actionable` | bool | Whether trade is actionable |
| `event_seq` | int | Sequence number |
| `reasoning` | str | Human-readable reasoning |
| `regime` | Optional[str] | Current regime |

### 5. Trade
Executed trade record.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Trade identifier |
| `signal` | str | Signal type value |
| `confidence` | float | Decision confidence |
| `ev` | float | EV score |
| `size` | float | Filled quantity |
| `price` | float | Execution price |
| `timestamp` | int | Event clock timestamp |

### 6. ExecutionResult
Result from the execution adapter.

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | str | Execution identifier |
| `trade_id` | str | Trade identifier |
| `symbol` | str | Trading pair |
| `signal_type` | SignalType | LONG / SHORT / NONE |
| `filled_price` | float | Actual fill price |
| `filled_quantity` | float | Actual fill quantity |
| `status` | OrderStatus | PENDING / FILLED / CANCELLED / REJECTED / EXPIRED / PARTIALLY_FILLED |
| `event_seq` | int | Sequence number |
| `strategy` | str | Strategy name |
| `slippage` | float | Execution slippage |
| `error` | str | Error message (if any) |
| `partial_fill_qty` | float | Partial fill quantity |
| `partial_fill_price` | float | Partial fill price |

**Computed property**: `success = status in (FILLED, PARTIALLY_FILLED)`

### 7. PnLDecomposition
Decomposed profit/loss with invariant validation.

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | str | Execution identifier |
| `signal_alpha` | float | Alpha from signal quality |
| `execution_alpha` | float | Alpha from execution quality |
| `noise` | float | Unexplained variance |
| `total_pnl` | float | Total profit/loss |

**Invariant**: `signal_alpha + execution_alpha + noise == total_pnl` (validated at construction, tolerance 1e-6)

### 8. RegimeResult
Market regime detection result.

| Field | Type | Description |
|-------|------|-------------|
| `regime` | RegimeType | TRENDING / RANGING / VOLATILE / MIXED |
| `confidence` | float | Detection confidence |
| `event_seq` | int | Sequence number |
| `risk_scaling` | float | Risk adjustment multiplier (default 1.0) |

### 9. ApprovalResult
Trade approval/rejection from governance layers.

| Field | Type | Description |
|-------|------|-------------|
| `approved` | bool | Whether trade is approved |
| `reason` | str | Reason for decision |
| `event_seq` | int | Sequence number |
| `details` | dict | Additional details |

### 10. (Internal) OrderState
Order lifecycle tracking in execution adapter.

| Field | Type | Description |
|-------|------|-------------|
| `order_id` | str | Order identifier |
| `symbol` | str | Trading pair |
| `status` | OrderStatus | Current order status |
| `requested_qty` | float | Requested quantity |
| `filled_qty` | float | Filled quantity |
| `avg_fill_price` | float | Average fill price |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |
| `retry_count` | int | Number of retries |
| `error` | str | Error message (if any) |

### Enums

| Enum | Values |
|------|--------|
| `SignalType` | LONG, SHORT, NONE |
| `OrderStatus` | PENDING, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED |
| `SystemState` | INITIALIZING, NORMAL, DEGRADED, CRITICAL, SHUTDOWN, HALTED |
| `RegimeType` | TRENDING, RANGING, VOLATILE, MIXED |

---

## Configuration Parameters

All 69 parameters grouped by category. Each can be set via environment variable or `.env` file.

### Environment (3)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `environment` | `ENVIRONMENT` | `development` | Runtime environment |
| `debug` | `DEBUG` | `false` | Enable debug mode |
| `timezone` | `TIMEZONE` | `UTC` | System timezone (pytz-compatible) |

### Trading (5)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `initial_equity` | `INITIAL_EQUITY` | `10000` | Starting capital |
| `max_position_size` | `MAX_POSITION_SIZE` | `0.1` | Max position as fraction of equity |
| `max_daily_loss` | `MAX_DAILY_LOSS` | `0.05` | Max daily loss as fraction of equity |
| `max_drawdown` | `MAX_DRAWDOWN` | `0.20` | Max drawdown before kill switch |
| `min_ev_threshold` | `MIN_EV_THRESHOLD` | `0.01` | Minimum EV score for actionable trades |

### Risk Management (5)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `max_consecutive_losses` | `MAX_CONSECUTIVE_LOSSES` | `5` | Kill switch trigger threshold |
| `max_trades_per_hour` | `MAX_TRADES_PER_HOUR` | `100` | Maximum trades per hour |
| `pnl_deviation_threshold` | `PNL_DEVIATION_THRESHOLD` | `3.0` | PnL anomaly detection threshold |
| `min_trades_for_anomaly_detection` | `MIN_TRADES_FOR_ANOMALY_DETECTION` | `20` | Minimum trades before anomaly detection |
| `volatility_scaling` | `VOLATILITY_SCALING` | `true` | Enable volatility-based position scaling |

### Learning Engine (3)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `min_sample_size` | `MIN_SAMPLE_SIZE` | `50` | Minimum samples for parameter update |
| `max_param_change` | `MAX_PARAM_CHANGE` | `0.1` | Maximum single parameter change (stability guard) |
| `rollback_enabled` | `ROLLBACK_ENABLED` | `true` | Enable parameter rollback |

### Regime Engine (1)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `regime_lookback_period` | `REGIME_LOOKBACK_PERIOD` | `100` | Lookback period for regime detection |

### Database (1)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `db_path` | `DB_PATH` | `./data/siqe.db` | SQLite database path |

### Execution (3)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `use_mock_execution` | `USE_MOCK_EXECUTION` | `true` | Use mock execution (dev mode) |
| `slippage_model` | `SLIPPAGE_MODEL` | `linear` | Slippage simulation model |
| `latency_tolerance_ms` | `LATENCY_TOLERANCE_MS` | `100` | Maximum acceptable latency |

### VN.PY (6)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `vnpy_gateway` | `VNPY_GATEWAY` | `BINANCE` | VN.PY gateway name |
| `exchange_api_key` | `EXCHANGE_API_KEY` | `` | Exchange API key |
| `exchange_api_secret` | `EXCHANGE_API_SECRET` | `` | Exchange API secret |
| `exchange_server` | `EXCHANGE_SERVER` | `SIMULATOR` | Exchange server endpoint |
| `proxy_host` | `PROXY_HOST` | `` | Proxy host |
| `proxy_port` | `PROXY_PORT` | `0` | Proxy port |

### Logging (2)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `log_level` | `LOG_LEVEL` | `INFO` | Logging level |
| `log_file` | `LOG_FILE` | `./logs/siqe.log` | Log file path |

### API (2)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `api_host` | `API_HOST` | `0.0.0.0` | API server bind address |
| `api_port` | `API_PORT` | `8000` | API server port |

### Strategy Restrictions (1)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `restricted_symbols` | `RESTRICTED_SYMBOLS` | `` | Comma-separated list of restricted symbols |

### Feature Flags (4)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `enable_learning` | `ENABLE_LEARNING` | `true` | Enable learning engine |
| `enable_regime_detection` | `ENABLE_REGIME_DETECTION` | `true` | Enable regime detection |
| `enable_meta_override` | `ENABLE_META_OVERRIDE` | `true` | Enable meta harness overrides |
| *(internal)* | — | — | Meta harness can override trading, modify risk, halt system |

### Pipeline / Concurrency (6)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `max_queue_size` | `MAX_QUEUE_SIZE` | `1000` | Maximum event queue size |
| `max_concurrent_events` | `MAX_CONCURRENT_EVENTS` | `4` | Maximum concurrent event processing |
| `stage_timeout` | `STAGE_TIMEOUT` | `5.0` | Per-stage timeout in seconds |
| `max_retries` | `MAX_RETRIES` | `3` | Maximum retries per stage |
| `retry_base_delay` | `RETRY_BASE_DELAY` | `0.1` | Base delay for exponential backoff |
| `initial_equity` | `INITIAL_EQUITY` | `10000` | Starting capital (also used by risk engine) |

---

## API Endpoints

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| `GET` | `/health` | System health check | status, timestamp, engine_status |
| `GET` | `/metrics` | Full system metrics | queue, latency, memory, risk, meta |
| `GET` | `/meta/status` | Meta harness status | system_state, override, kill conditions |
| `POST` | `/halt` | Halt system (kill switch) | success, message, timestamp |
| `POST` | `/resume` | Resume from halted state | success, message, timestamp |
| `POST` | `/risk_adjust` | Adjust risk parameters | success, message, adjustments |
| `POST` | `/disable_strategy` | Disable a strategy | success, message, timestamp |
| `GET` | `/strategies` | Strategy performance status | strategies, regime info |
| `GET` | `/regime` | Current market regime | regime, confidence, risk_scaling |

---

## Backtesting Engine

Deterministic historical replay with free market data. Composes all existing SIQE components — no code duplication.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     BacktestEngine                            │
│                                                               │
│  HistoricalDataProvider  ──▶  MarketEvent iterator            │
│  (yfinance / CCXT / CSV / Parquet)                            │
│                                                               │
│  For each event (synchronous, no async queue):                │
│    Regime → Strategy → EV → Decision → Meta → Risk → Exec     │
│    └─ FeedbackLoop → RiskEngine.update() → EVEngine.update()  │
│                                                               │
│  Every N trades (adaptive mode):                              │
│    └─ LearningEngine.update_parameters()                      │
│                                                               │
│  After all events: PerformanceAnalyzer → BacktestResult        │
└──────────────────────────────────────────────────────────────┘
```

### Data Sources

| Provider | API | Key Required | Timeframes | Use Case |
|----------|-----|-------------|------------|----------|
| **yfinance** | Yahoo Finance | No | 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo | Stocks, ETFs, indices |
| **CCXT** | 100+ crypto exchanges | No (public data) | 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1wk | Crypto (BTC, ETH, etc.) |
| **CSV** | Local files | N/A | Any | Custom data, tick data |
| **Parquet** | Local files | N/A | Any | Large datasets, fast I/O |

### Slippage Models

| Model | Formula | Best For |
|-------|---------|----------|
| **Fixed BPS** | `price ± (bps / 10000) * price` | Liquid markets, small orders |
| **Linear** | `base_bps + size_penalty + volatility_penalty` | Medium orders, varying volatility |
| **Volume Impact** | `sigma * sqrt(size / volume)` | Large orders, square-root market impact |

### Performance Metrics

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| **Sharpe Ratio** | `mean(returns) / std(returns) * sqrt(bars_per_year)` | > 1.0 good, > 2.0 excellent |
| **Sortino Ratio** | `mean(returns) / downside_std * sqrt(bars_per_year)` | Penalizes only downside volatility |
| **Calmar Ratio** | `annualized_return / max_drawdown` | Return per unit of worst drawdown |
| **Max Drawdown** | `(peak - trough) / peak` | Worst peak-to-trough decline |
| **Profit Factor** | `gross_profit / gross_loss` | > 1.0 profitable, > 1.5 strong |
| **Win Rate** | `winning_trades / total_trades` | Context-dependent, needs profit factor |
| **Overfit Ratio** | `(train_sharpe - test_sharpe) / |train_sharpe|` | < 0.3 acceptable, > 0.5 overfitted |

### Usage

#### Basic backtest (yfinance, daily bars)

```python
from backtest import BacktestEngine, BacktestSettings, DataProviderType

settings = BacktestSettings(
    data_provider=DataProviderType.YFINANCE,
    symbols=["SPY", "QQQ"],
    start_date="2023-01-01",
    end_date="2024-01-01",
    timeframe="1d",
    initial_equity=10000.0,
    rng_seed=42,
)

engine = BacktestEngine(settings)
result = engine.run()

print(f"Return: {result.metrics.total_return_pct:.2f}%")
print(f"Sharpe: {result.metrics.sharpe_ratio:.3f}")
print(f"Max DD: {result.metrics.max_drawdown:.2%}")
print(f"Trades: {result.metrics.total_trades}")
```

#### Crypto backtest (CCXT, hourly bars)

```python
from backtest import BacktestSettings, DataProviderType, SlippageModelType

settings = BacktestSettings(
    data_provider=DataProviderType.CCXT,
    ccxt_exchange="binance",
    ccxt_market_type="spot",
    symbols=["BTC/USDT", "ETH/USDT"],
    start_date="2024-01-01",
    end_date="2024-06-01",
    timeframe="1h",
    slippage_model=SlippageModelType.VOLUME_IMPACT,
    volume_impact_factor=0.1,
    rng_seed=42,
)

engine = BacktestEngine(settings)
result = engine.run()
```

#### CSV backtest (custom data)

```python
from backtest import BacktestSettings, DataProviderType

settings = BacktestSettings(
    data_provider=DataProviderType.CSV,
    symbols=["MYSTRATEGY"],
    csv_path="./data/historical/",  # directory of CSV files, or single file path
    timeframe="1d",
    rng_seed=42,
)

engine = BacktestEngine(settings)
result = engine.run()
```

#### Adaptive learning mode (walk-forward)

```python
from backtest import BacktestSettings, LearningMode

settings = BacktestSettings(
    data_provider=DataProviderType.YFINANCE,
    symbols=["SPY"],
    start_date="2020-01-01",
    end_date="2024-01-01",
    timeframe="1d",
    learning_mode=LearningMode.ADAPTIVE,
    learning_interval=50,
    rng_seed=42,
)

engine = BacktestEngine(settings)
result = engine.run()
print(f"Parameter updates: {result.parameter_updates}")
```

#### Walk-forward optimization

```python
from backtest import WalkForwardOptimizer, BacktestSettings

settings = BacktestSettings(
    data_provider=DataProviderType.YFINANCE,
    symbols=["SPY"],
    start_date="2020-01-01",
    end_date="2024-01-01",
    timeframe="1d",
)

optimizer = WalkForwardOptimizer(
    base_settings=settings,
    train_bars=252,   # 1 year of daily bars
    test_bars=63,     # 1 quarter
    step_bars=21,     # Roll forward monthly
)

summary = optimizer.run()
print(f"Avg test Sharpe: {summary.avg_test_sharpe:.3f}")
print(f"Avg overfit ratio: {summary.avg_overfit_ratio:.3f}")
print(f"Consistent windows: {summary.consistent_windows}/{summary.total_windows}")
```

#### Generate reports

```python
from backtest import ReportGenerator

reporter = ReportGenerator(output_dir="./backtest_output")
paths = reporter.generate(result, generate_html=True)

# paths["json"] -> full machine-readable result
# paths["csv"]  -> trade-by-trade log
# paths["html"] -> visual dashboard (equity curve, drawdown, trade table)
```

### Report Output

| Format | Always Generated | Content |
|--------|-----------------|---------|
| **JSON** | Yes | All metrics, equity curve, trade log, settings, metadata |
| **CSV** | Yes | Trade-by-trade: entry/exit, PnL, slippage, strategy, regime |
| **HTML** | Optional (`generate_html=True`) | Visual dashboard: equity curve, drawdown chart, metrics cards, trade table |

---

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
git clone https://github.com/nkhekhe/SIQE.git
cd SIQE
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Run with Determinism Guarantee

```bash
PYTHONHASHSEED=0 python main.py
```

### Run Tests

```bash
python -m pytest tests/ -v
```

### Docker

```bash
docker build -t siqe:v3 .
docker run -p 8000:8000 --memory=8g --cpus=4 siqe:v3
```

### Docker Compose

```bash
docker-compose up -d
```

### API Access

```bash
# Health check
curl http://localhost:8000/health

# Full metrics
curl http://localhost:8000/metrics

# Current regime
curl http://localhost:8000/regime

# Halt system
curl -X POST "http://localhost:8000/halt?reason=Maintenance"

# Resume system
curl -X POST http://localhost:8000/resume
```

---

## Testing

| Test Suite | File | Tests | Coverage |
|------------|------|-------|----------|
| Pipeline | `test_pipeline.py` | End-to-end pipeline flow | Signal generation, EV, decision, execution |
| Determinism | `test_determinism.py` | Reproducibility guarantees | Seeded RNG, EventClock, ID generation |
| Risk | `test_risk.py` | Risk constraint enforcement | Drawdown, daily loss, position size, consecutive losses |
| Failure Handling | `test_failure_handling.py` | Error recovery | Stage failures, retries, timeouts |
| Data Contracts | `test_data_contract.py` | Type validation | Frozen dataclasses, field validation, enums |
| Meta Harness | `test_meta_harness.py` | Governance logic | Kill switch, state transitions, overrides |
| Learning Engine | `test_learning.py` | Parameter learning | Updates, stability guards, rollback |
| **Backtest** | `test_backtest.py` | **Slippage, metrics, data providers, walk-forward** | **22 tests: slippage models, performance analyzer, CSV provider, window generation** |

**Result: 64/64 tests passing, zero failures.**

---

## SWOT Analysis

### Strengths
- **Deterministic by design**: EventClock, seeded RNG, frozen dataclasses — identical inputs produce identical outputs
- **Risk-first architecture**: Hard constraints enforced before every trade, kill switch with multiple triggers
- **Self-improving**: Learning engine with stability guards and rollback capability
- **Clean architecture**: 6 layers, strict separation of concerns, VN.PY abstracted behind bridge
- **Production-ready infrastructure**: Docker, HEALTHCHECK, non-root user, structured JSON logging

### Weaknesses
- **Mock data feeds in live mode**: Currently uses simulated market data for live trading; real exchange integration requires VN.PY installation
- **Strategy logic is placeholder**: Mean reversion, momentum, breakout strategies use random signal generation (stubs for real logic)
- **No distributed architecture**: Single-node only, no horizontal scaling

### Opportunities
- **Real exchange connectivity**: VN.PY supports 100+ gateways (Binance, CTP, IB, etc.)
- **Backtesting engine**: Replay historical data through the deterministic pipeline for strategy validation
- **Distributed architecture**: Split pipeline stages across nodes for throughput scaling
- **CI/CD pipeline**: Automated testing, linting, and deployment on every commit
- **ML integration**: Replace random strategies with trained models (the learning engine is designed for this)

### Threats
- **Exchange API changes**: Gateway interfaces may break with exchange updates
- **Regulatory risk**: Trading automation may require compliance in certain jurisdictions
- **Model drift**: Learned parameters may degrade in unseen market regimes
- **Infrastructure failure**: Single-node deployment has no failover redundancy

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 siqe
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R siqe:siqe /app
USER siqe
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=0
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["python3", "main.py"]
```

### docker-compose.yml

```yaml
version: '3.8'
services:
  siqe:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PYTHONHASHSEED=0
      - PYTHONUNBUFFERED=1
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4'
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

---

## Project Structure

```
siqe/
├── main.py                          # SIQEEngine singleton, event-driven pipeline
├── config/
│   └── settings.py                  # 69 configuration parameters
├── core/
│   ├── clock.py                     # EventClock + IDGenerator
│   ├── retry.py                     # Bounded exponential backoff
│   └── data_engine.py               # Market data acquisition
├── models/
│   ├── trade.py                     # 10 dataclasses + 4 enums
│   └── __init__.py                  # Public API exports
├── strategy_engine/
│   └── strategy_base.py             # MeanReversion, Momentum, Breakout
├── ev_engine/
│   └── ev_calculator.py             # Expected value calculation
├── decision_engine/
│   └── decision_maker.py            # Best-EV trade selection
├── meta_harness/
│   └── meta_governor.py             # System governance, kill switch
├── risk_engine/
│   └── risk_manager.py              # Hard risk constraints
├── execution_adapter/
│   └── vnpy_bridge.py               # VN.PY bridge (mock + real)
├── feedback/
│   └── feedback_loop.py             # PnL decomposition, tracking
├── regime/
│   └── regime_engine.py             # Regime detection
├── learning/
│   └── learning_engine.py           # Parameter learning, rollback
├── memory/
│   └── state_manager.py             # State persistence
├── api/
│   └── main.py                      # FastAPI REST interface
├── infra/
│   └── logger.py                    # Structured JSON logging
├── backtest/
│   ├── __init__.py                  # Public API exports
│   ├── config.py                    # BacktestSettings, enums
│   ├── data_provider.py             # HistoricalDataProvider (yfinance, CCXT, CSV, Parquet)
│   ├── slippage_model.py            # FixedBPS, Linear, VolumeImpact slippage
│   ├── performance.py               # PerformanceAnalyzer (Sharpe, Sortino, Calmar, etc.)
│   ├── engine.py                    # BacktestEngine — main orchestrator
│   ├── walk_forward.py              # WalkForwardOptimizer — train/test windows
│   └── report.py                    # ReportGenerator — JSON, CSV, HTML output
├── tests/
│   ├── test_pipeline.py
│   ├── test_determinism.py
│   ├── test_risk.py
│   ├── test_failure_handling.py
│   ├── test_data_contract.py
│   ├── test_meta_harness.py
│   ├── test_learning.py
│   └── test_backtest.py             # Slippage, metrics, data providers, walk-forward
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
├── .gitignore
└── TODO.md
```

---

## License

Proprietary — All rights reserved.

## Author

nkhekhe — SIQE V3
