"""
SIQE V3 Data Contracts
Strict frozen dataclass types for all data flowing through the pipeline.
No Dict[str, Any] allowed — every object is typed and validated.
"""
import hashlib
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class SignalType(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class OrderStatus(Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SystemState(Enum):
    INITIALIZING = "INITIALIZING"
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    SHUTDOWN = "SHUTDOWN"
    HALTED = "HALTED"


class RegimeType(Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    MIXED = "MIXED"


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    symbol: str
    bid: float
    ask: float
    volume: float
    volatility: float
    event_seq: int

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0

    @classmethod
    def validate(cls, data: dict) -> "MarketEvent":
        required = {"event_id", "symbol", "bid", "ask", "volume", "volatility", "event_seq"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"MarketEvent missing fields: {missing}")
        return cls(
            event_id=str(data["event_id"]),
            symbol=str(data["symbol"]),
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            volume=float(data["volume"]),
            volatility=float(data["volatility"]),
            event_seq=int(data["event_seq"]),
        )


@dataclass(frozen=True)
class Signal:
    signal_id: str
    symbol: str
    signal_type: SignalType
    strength: float
    price: float
    strategy: str
    reason: str
    event_seq: int
    regime: Optional[str] = None
    regime_confidence: float = 0.0

    def __post_init__(self):
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"Signal strength must be in [0, 1], got {self.strength}")
        if self.price <= 0:
            raise ValueError(f"Signal price must be positive, got {self.price}")

    @classmethod
    def validate(cls, data: dict) -> "Signal":
        required = {"signal_id", "symbol", "signal_type", "strength", "price", "strategy", "reason", "event_seq"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Signal missing fields: {missing}")
        st = data["signal_type"]
        if isinstance(st, str):
            st = SignalType(st.lower())
        return cls(
            signal_id=str(data["signal_id"]),
            symbol=str(data["symbol"]),
            signal_type=st,
            strength=float(data["strength"]),
            price=float(data["price"]),
            strategy=str(data["strategy"]),
            reason=str(data["reason"]),
            event_seq=int(data["event_seq"]),
            regime=data.get("regime"),
            regime_confidence=float(data.get("regime_confidence", 0.0)),
        )


@dataclass(frozen=True)
class EVResult:
    signal_id: str
    symbol: str
    signal_type: SignalType
    strength: float
    price: float
    strategy: str
    ev_score: float
    actionable: bool
    event_seq: int
    regime: Optional[str] = None
    regime_confidence: float = 0.0

    @classmethod
    def from_signal(cls, signal: Signal, ev_score: float, actionable: bool) -> "EVResult":
        return cls(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            strength=signal.strength,
            price=signal.price,
            strategy=signal.strategy,
            ev_score=ev_score,
            actionable=actionable,
            event_seq=signal.event_seq,
            regime=signal.regime,
            regime_confidence=signal.regime_confidence,
        )


@dataclass(frozen=True)
class Decision:
    decision_id: str
    signal_id: str
    symbol: str
    signal_type: SignalType
    strength: float
    price: float
    strategy: str
    ev_score: float
    confidence: float
    actionable: bool
    event_seq: int
    reasoning: str = ""
    regime: Optional[str] = None

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Decision confidence must be in [0, 1], got {self.confidence}")

    @classmethod
    def from_ev(cls, ev: EVResult, decision_id: str, confidence: float, reasoning: str = "") -> "Decision":
        return cls(
            decision_id=decision_id,
            signal_id=ev.signal_id,
            symbol=ev.symbol,
            signal_type=ev.signal_type,
            strength=ev.strength,
            price=ev.price,
            strategy=ev.strategy,
            ev_score=ev.ev_score,
            confidence=confidence,
            actionable=ev.actionable,
            event_seq=ev.event_seq,
            reasoning=reasoning,
            regime=ev.regime,
        )


@dataclass(frozen=True)
class Trade:
    id: str
    signal: str
    confidence: float
    ev: float
    size: float
    price: float
    timestamp: int

    @classmethod
    def from_decision(cls, decision: Decision, trade_id: str, size: float, event_clock: int) -> "Trade":
        return cls(
            id=trade_id,
            signal=decision.signal_type.value,
            confidence=decision.confidence,
            ev=decision.ev_score,
            size=size,
            price=decision.price,
            timestamp=event_clock,
        )


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    trade_id: str
    symbol: str
    signal_type: SignalType
    filled_price: float
    filled_quantity: float
    status: OrderStatus
    event_seq: int
    strategy: str = ""
    slippage: float = 0.0
    error: str = ""
    partial_fill_qty: float = 0.0
    partial_fill_price: float = 0.0

    @property
    def success(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)


@dataclass(frozen=True)
class PnLDecomposition:
    execution_id: str
    signal_alpha: float
    execution_alpha: float
    noise: float
    total_pnl: float

    def __post_init__(self):
        expected = self.signal_alpha + self.execution_alpha + self.noise
        if abs(expected - self.total_pnl) > 1e-6:
            raise ValueError(
                f"PnL decomposition does not sum: {self.signal_alpha} + "
                f"{self.execution_alpha} + {self.noise} = {expected} != {self.total_pnl}"
            )


@dataclass(frozen=True)
class RegimeResult:
    regime: RegimeType
    confidence: float
    event_seq: int
    risk_scaling: float = 1.0


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    reason: str
    event_seq: int
    details: dict = field(default_factory=dict)
