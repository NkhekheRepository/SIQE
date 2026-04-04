"""
Tests: Data contract validation and immutability
"""
import pytest
import sys
import os
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.trade import (
    MarketEvent, Signal, SignalType, EVResult, Decision,
    Trade, ExecutionResult, OrderStatus, PnLDecomposition,
    RegimeResult, RegimeType, ApprovalResult,
)


def test_market_event_validate_missing_fields():
    with pytest.raises(ValueError, match="missing fields"):
        MarketEvent.validate({"event_id": "1"})


def test_market_event_validate_valid():
    event = MarketEvent.validate({
        "event_id": "evt_1", "symbol": "BTCUSDT", "bid": 42000.0,
        "ask": 42010.0, "volume": 50.0, "volatility": 0.02, "event_seq": 1,
    })
    assert event.symbol == "BTCUSDT"
    assert event.mid_price == 42005.0


def test_signal_validate_missing_fields():
    with pytest.raises(ValueError, match="missing fields"):
        Signal.validate({"signal_id": "1"})


def test_signal_validate_invalid_strength():
    with pytest.raises(ValueError, match="strength"):
        Signal(
            signal_id="sig_1", symbol="BTCUSDT", signal_type=SignalType.LONG,
            strength=1.5, price=42000.0, strategy="test", reason="test", event_seq=1,
        )


def test_signal_validate_invalid_price():
    with pytest.raises(ValueError, match="price"):
        Signal(
            signal_id="sig_1", symbol="BTCUSDT", signal_type=SignalType.LONG,
            strength=0.5, price=-1.0, strategy="test", reason="test", event_seq=1,
        )


def test_decision_validate_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        Decision(
            decision_id="dec_1", signal_id="sig_1", symbol="BTCUSDT",
            signal_type=SignalType.LONG, strength=0.5, price=42000.0,
            strategy="test", ev_score=0.05, confidence=1.5, actionable=True, event_seq=1,
        )


def test_trade_immutability():
    trade = Trade(id="t_1", signal="long", confidence=0.7, ev=0.05, size=1.0, price=42000.0, timestamp=1)

    with pytest.raises(Exception):
        trade.price = 99999.0

    new_trade = replace(trade, price=43000.0)
    assert new_trade.price == 43000.0
    assert trade.price == 42000.0


def test_pnl_decomposition_invariant():
    decomp = PnLDecomposition(
        execution_id="exec_1", signal_alpha=10.0, execution_alpha=-0.5, noise=0.3, total_pnl=9.8,
    )
    assert decomp.total_pnl == 9.8


def test_pnl_decomposition_invalid_sum():
    with pytest.raises(ValueError, match="does not sum"):
        PnLDecomposition(
            execution_id="exec_1", signal_alpha=10.0, execution_alpha=-0.5, noise=0.3, total_pnl=5.0,
        )


def test_execution_result_success_property():
    result = ExecutionResult(
        execution_id="exec_1", trade_id="t_1", symbol="BTCUSDT",
        signal_type=SignalType.LONG, filled_price=42000.0, filled_quantity=1.0,
        status=OrderStatus.FILLED, event_seq=1,
    )
    assert result.success is True

    result2 = ExecutionResult(
        execution_id="exec_2", trade_id="t_2", symbol="BTCUSDT",
        signal_type=SignalType.LONG, filled_price=0.0, filled_quantity=0.0,
        status=OrderStatus.REJECTED, event_seq=2, error="rejected",
    )
    assert result2.success is False


def test_approval_result():
    approved = ApprovalResult(approved=True, reason="OK", event_seq=1)
    assert approved.approved is True

    rejected = ApprovalResult(approved=False, reason="Risk limit", event_seq=2)
    assert rejected.approved is False
