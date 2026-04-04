"""
API Endpoint Tests
Tests for health, emergency, and execution endpoints.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app, set_engine_instance


class MockExecutionAdapter:
    def __init__(self):
        self.is_initialized = True
        self.is_connected = True
        self.pending_orders = {}
        self.executed_trades = []


class MockRiskEngine:
    def __init__(self):
        self.daily_pnl = 0.0
        self.current_equity = 10000.0
        self.peak_equity = 10000.0
        self.consecutive_losses = 0
        self.risk_limits = {
            "max_daily_loss": 0.05,
            "max_drawdown": 0.20,
            "max_position_size": 0.1,
            "max_consecutive_losses": 5,
            "max_trades_per_hour": 100,
            "volatility_scaling": True,
        }
        self._emergency_stop_reason = ""
        self._api_failure_count = 0
        self._circuit_breaker_history = []
        self._has_active_breaker = False

    async def get_risk_status(self):
        daily_loss_pct = abs(self.daily_pnl) / self.current_equity if self.current_equity > 0 else 0
        current_drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
        return {
            "daily_pnl": self.daily_pnl,
            "daily_loss_pct": daily_loss_pct,
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "current_drawdown": current_drawdown,
            "consecutive_losses": self.consecutive_losses,
            "trades_this_hour": 0,
            "risk_limits": self.risk_limits,
        }

    async def get_circuit_breaker_status(self):
        active_breakers = ["emergency_stop"] if self._has_active_breaker else []
        return {
            "circuit_breakers": {},
            "any_active": self._has_active_breaker,
            "active_breakers": active_breakers,
            "emergency_stop_reason": self._emergency_stop_reason,
            "api_failure_count": self._api_failure_count,
            "recent_triggers": self._circuit_breaker_history[-10:],
        }

    async def emergency_stop(self, reason="Manual emergency stop"):
        self._emergency_stop_reason = reason
        self._has_active_breaker = True
        return {"success": True, "reason": reason, "timestamp": 1}

    async def emergency_resume(self):
        self._emergency_stop_reason = ""
        self._has_active_breaker = False
        return {"success": True, "timestamp": 2}


class MockSettings:
    def __init__(self):
        self.use_mock_execution = True
        self.vnpy_gateway = "BINANCE"
        self.exchange_server = "SIMULATOR"


class MockClock:
    def __init__(self):
        self.now = 100


class MockEngine:
    def __init__(self):
        self.clock = MockClock()
        self.settings = MockSettings()
        self.execution_adapter = MockExecutionAdapter()
        self.risk_engine = MockRiskEngine()

    def get_status(self):
        return {
            "running": True,
            "system_state": "NORMAL",
            "uptime_ticks": 100,
            "total_trades": 5,
            "total_events_processed": 20,
            "total_events_rejected": 0,
            "start_seq": 0,
        }

    def get_metrics(self):
        return {
            "queue_depth": 0,
            "queue_capacity": 1000,
            "active_concurrent": 0,
            "max_concurrent": 4,
            "stage_latencies_avg_ticks": {},
            "throughput_events": 20,
            "rejected_events": 0,
            "memory_mb": 50.0,
            "peak_memory_mb": 75.0,
        }


class TestHealthEndpoints:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        mock_engine = MockEngine()
        set_engine_instance(mock_engine)
        self.engine = mock_engine

    def test_health_returns_200(self):
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "engine_status" in data

    def test_health_detailed_structure(self):
        client = TestClient(app)
        response = client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert "engine" in data
        assert "execution" in data
        assert "queue" in data
        assert "resources" in data
        assert "latencies" in data
        assert data["engine"]["running"] is True
        assert data["execution"]["mode"] == "mock"

    def test_health_execution_circuit_breakers(self):
        client = TestClient(app)
        response = client.get("/health/execution")

        assert response.status_code == 200
        data = response.json()
        assert "circuit_breakers" in data
        assert "initialized" in data
        assert "connected" in data
        assert data["mode"] == "mock"
        assert data["gateway"] == "BINANCE"


class TestEmergencyEndpoints:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        mock_engine = MockEngine()
        set_engine_instance(mock_engine)
        self.engine = mock_engine

    def test_emergency_stop_api(self):
        client = TestClient(app)
        response = client.post("/emergency/stop", params={"reason": "Test stop"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reason"] == "Test stop"

    def test_emergency_resume_api(self):
        client = TestClient(app)
        client.post("/emergency/stop", params={"reason": "Test stop"})
        response = client.post("/emergency/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_emergency_status_api(self):
        client = TestClient(app)
        response = client.get("/emergency/status")

        assert response.status_code == 200
        data = response.json()
        assert "circuit_breakers" in data
        assert "risk_metrics" in data
        assert "daily_pnl" in data["risk_metrics"]
        assert "current_equity" in data["risk_metrics"]
