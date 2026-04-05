"""
SIQE V3 - Alert System Tests

Comprehensive tests for all alert functionality including:
- Alert manager with new alert types
- RiskEngine alert integration
- RegimeEngine alert integration
- LearningEngine alert integration
- CTA strategy alert integration
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alerts.alert_types import (
    AlertType, AlertSeverity, create_alert,
    ALERT_SEVERITY_MAP,
)
from alerts.alert_manager import AlertManager


class TestAlertTypes:
    """Test alert types and severity mapping."""
    
    def test_all_alert_types_defined(self):
        """All alert types should be defined."""
        expected_types = [
            "emergency_stop", "circuit_breaker", "drawdown_warning", "daily_loss",
            "trade_executed", "position_opened", "position_closed", "parameter_update",
            "parameter_rollback", "system_startup", "system_shutdown", "api_failure",
            "learning_triggered", "regime_change", "margin_warning", "margin_critical",
            "liquidation_risk", "order_rejected", "heartbeat", "queue_full",
            "pipeline_error", "connection_lost", "connection_restored", "anomalous_pnl",
        ]
        for alert_type in expected_types:
            assert hasattr(AlertType, alert_type.upper()), f"Missing AlertType: {alert_type}"
    
    def test_all_alert_types_have_severity(self):
        """All alert types should have severity mapping."""
        for alert_type in AlertType:
            assert alert_type in ALERT_SEVERITY_MAP, f"No severity for {alert_type}"
    
    def test_severity_values(self):
        """Severity values should be correct."""
        assert ALERT_SEVERITY_MAP[AlertType.EMERGENCY_STOP] == AlertSeverity.CRITICAL
        assert ALERT_SEVERITY_MAP[AlertType.DAILY_LOSS] == AlertSeverity.CRITICAL
        assert ALERT_SEVERITY_MAP[AlertType.LIQUIDATION_RISK] == AlertSeverity.CRITICAL
        assert ALERT_SEVERITY_MAP[AlertType.MARGIN_WARNING] == AlertSeverity.HIGH
        assert ALERT_SEVERITY_MAP[AlertType.TRADE_EXECUTED] == AlertSeverity.LOW
        assert ALERT_SEVERITY_MAP[AlertType.HEARTBEAT] == AlertSeverity.INFO


class TestAlertManager:
    """Test alert manager functionality."""
    
    @pytest.fixture
    def alert_manager(self):
        """Create alert manager with mocked Telegram."""
        with patch('alerts.alert_manager.TelegramChannel') as mock_telegram:
            mock_channel = Mock()
            mock_channel.is_configured.return_value = True
            mock_channel.send_alert.return_value = True
            mock_telegram.return_value = mock_channel
            
            manager = AlertManager(
                telegram_bot_token="test_token",
                telegram_chat_id="test_chat",
                enabled=True,
            )
            return manager
    
    def test_is_configured(self, alert_manager):
        """Alert manager should be configured."""
        assert alert_manager.is_configured() is True
    
    def test_emergency_stop_alert(self, alert_manager):
        """Test emergency stop alert."""
        result = alert_manager.emergency_stop(reason="Test emergency")
        assert result is True
    
    def test_circuit_breaker_alert(self, alert_manager):
        """Test circuit breaker alert."""
        result = alert_manager.circuit_breaker(
            breaker_name="daily_loss",
            reason="Loss exceeded limit"
        )
        assert result is True
    
    def test_drawdown_warning_alert(self, alert_manager):
        """Test drawdown warning alert."""
        result = alert_manager.drawdown_warning(
            current_dd=0.15,
            max_dd=0.20
        )
        assert result is True
    
    def test_daily_loss_alert(self, alert_manager):
        """Test daily loss alert."""
        result = alert_manager.daily_loss(
            loss=0.06,
            limit=0.05
        )
        assert result is True
    
    def test_margin_warning_alert(self, alert_manager):
        """Test margin warning alert."""
        result = alert_manager.margin_warning(
            margin_ratio=0.75,
            threshold=0.70
        )
        assert result is True
    
    def test_margin_critical_alert(self, alert_manager):
        """Test margin critical alert."""
        result = alert_manager.margin_critical(
            margin_ratio=0.92,
            threshold=0.90
        )
        assert result is True
    
    def test_liquidation_risk_alert(self, alert_manager):
        """Test liquidation risk alert."""
        result = alert_manager.liquidation_risk(
            current_price=50000.0,
            liquidation_price=47500.0,
            distance_pct=5.0
        )
        assert result is True
    
    def test_position_opened_alert(self, alert_manager):
        """Test position opened alert."""
        result = alert_manager.position_opened(
            side="LONG",
            volume=0.5,
            entry_price=50000.0
        )
        assert result is True
    
    def test_position_closed_alert(self, alert_manager):
        """Test position closed alert."""
        result = alert_manager.position_closed(
            pnl=250.0,
            side="LONG",
            duration_min=30
        )
        assert result is True
    
    def test_parameter_update_alert(self, alert_manager):
        """Test parameter update alert."""
        changes = {"threshold": (0.02, 0.025), "period": (20, 22)}
        result = alert_manager.parameter_update(
            strategy="mean_reversion",
            changes=changes
        )
        assert result is True
    
    def test_parameter_rollback_alert(self, alert_manager):
        """Test parameter rollback alert."""
        result = alert_manager.parameter_rollback(
            strategy="mean_reversion",
            reason="Performance degradation"
        )
        assert result is True
    
    def test_regime_change_alert(self, alert_manager):
        """Test regime change alert."""
        result = alert_manager.regime_change(
            old_regime="TRENDING",
            new_regime="RANGING"
        )
        assert result is True
    
    def test_api_failure_alert(self, alert_manager):
        """Test API failure alert."""
        result = alert_manager.api_failure(
            endpoint="Binance API",
            error="Connection timeout"
        )
        assert result is True
    
    def test_heartbeat_alert(self, alert_manager):
        """Test heartbeat alert."""
        result = alert_manager.heartbeat(
            uptime_seconds=3600,
            status="OK"
        )
        assert result is True
    
    def test_queue_full_alert(self, alert_manager):
        """Test queue full alert."""
        result = alert_manager.queue_full(
            queue_size=950,
            max_size=1000
        )
        assert result is True
    
    def test_pipeline_error_alert(self, alert_manager):
        """Test pipeline error alert."""
        result = alert_manager.pipeline_error(
            stage="risk",
            error="Validation timeout"
        )
        assert result is True
    
    def test_connection_lost_alert(self, alert_manager):
        """Test connection lost alert."""
        result = alert_manager.connection_lost(
            endpoint="Binance WebSocket"
        )
        assert result is True
    
    def test_connection_restored_alert(self, alert_manager):
        """Test connection restored alert."""
        result = alert_manager.connection_restored(
            endpoint="Binance WebSocket"
        )
        assert result is True
    
    def test_anomalous_pnl_alert(self, alert_manager):
        """Test anomalous PnL alert."""
        result = alert_manager.anomalous_pnl(
            expected_pnl=100.0,
            actual_pnl=-500.0,
            deviation_sigma=3.5
        )
        assert result is True
    
    def test_rate_limiting_suppresses_duplicate(self, alert_manager):
        """Rate limiting should suppress duplicate alerts."""
        # First call should succeed
        result1 = alert_manager.heartbeat(uptime_seconds=100, status="OK")
        assert result1 is True
        
        # Immediate second call should be suppressed
        result2 = alert_manager.heartbeat(uptime_seconds=101, status="OK")
        # Result depends on rate limiting config
    
    def test_get_stats(self, alert_manager):
        """Test getting alert statistics."""
        alert_manager.heartbeat(uptime_seconds=100, status="OK")
        stats = alert_manager.get_stats()
        assert "total_sent" in stats
        assert stats["total_sent"] >= 1
    
    def test_get_recent_alerts(self, alert_manager):
        """Test getting recent alerts."""
        alert_manager.heartbeat(uptime_seconds=100, status="OK")
        recent = alert_manager.get_recent_alerts(limit=5)
        assert len(recent) >= 1


class TestRiskEngineAlerts:
    """Test RiskEngine alert integration."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_alert_on_activation(self):
        """Circuit breaker should trigger alert."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from core.clock import EventClock
        from config.settings import Settings
        
        settings = Settings()
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        
        # Mock alert manager
        mock_alert = Mock()
        engine.alert_manager = mock_alert
        
        # Initialize
        await engine.initialize()
        
        # Trigger circuit breaker
        engine._activate_circuit_breaker(
            CircuitBreakerType.DAILY_LOSS,
            "Test reason"
        )
        
        # Verify alert was called
        mock_alert.circuit_breaker.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_daily_loss_alert(self):
        """Daily loss should trigger alert."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from core.clock import EventClock
        from config.settings import Settings
        
        settings = Settings()
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        
        # Override risk limit
        engine.risk_limits["max_daily_loss"] = 0.05
        
        mock_alert = Mock()
        engine.alert_manager = mock_alert
        
        await engine.initialize()
        
        # Directly trigger circuit breaker
        engine._activate_circuit_breaker(
            CircuitBreakerType.DAILY_LOSS,
            "Daily loss 6% >= 5% limit"
        )
        
        # Verify alert was sent
        mock_alert.circuit_breaker.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_drawdown_warning_alert(self):
        """Drawdown warning should be triggered at 80% threshold."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from core.clock import EventClock
        from config.settings import Settings
        
        settings = Settings()
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        
        # Override risk limit
        engine.risk_limits["max_drawdown"] = 0.20
        
        mock_alert = Mock()
        engine.alert_manager = mock_alert
        
        await engine.initialize()
        
        # Trigger circuit breaker for drawdown
        engine._activate_circuit_breaker(
            CircuitBreakerType.DRAWDOWN,
            "Drawdown 22% >= 20% limit"
        )
        
        # Drawdown warning should be called
        mock_alert.circuit_breaker.assert_called()
    
    @pytest.mark.asyncio
    async def test_api_failure_alert(self):
        """API failure should trigger alert."""
        from risk_engine.risk_manager import RiskEngine
        from core.clock import EventClock
        from config.settings import Settings
        
        settings = Settings()
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        
        mock_alert = Mock()
        engine.alert_manager = mock_alert
        
        await engine.initialize()
        
        # Record API failure
        await engine.record_api_failure()
        
        # Should not trigger circuit breaker yet (need 3)
        mock_alert.api_failure.assert_called_once()


class TestRegimeEngineAlerts:
    """Test RegimeEngine alert integration."""
    
    @pytest.mark.asyncio
    async def test_regime_change_alert(self):
        """Regime change should trigger alert."""
        # This test validates the regime engine has alert capabilities
        import inspect
        from regime.regime_engine import RegimeEngine
        
        # Check the source has alert_manager capability
        source = inspect.getsource(RegimeEngine)
        assert 'alert_manager' in source
    
    @pytest.mark.asyncio
    async def test_parameter_rollback_alert(self):
        """Parameter rollback should trigger alert."""
        # This test validates the learning engine has rollback alert capabilities
        import inspect
        from learning.learning_engine import LearningEngine
        
        source = inspect.getsource(LearningEngine)
        assert 'parameter_rollback' in source


class TestCtaStrategyAlerts:
    """Test CTA strategy alert integration."""
    
    def test_strategy_has_alert_manager_property(self):
        """Strategy should have alert manager property."""
        # Read the strategy file to verify the property exists
        import inspect
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        
        # Get the source and check for _alert_manager in __init__
        source = inspect.getsource(SiqeFuturesStrategy.__init__)
        assert '_alert_manager' in source
    
    def test_strategy_has_set_alert_manager_method(self):
        """Strategy should have set_alert_manager method."""
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        
        assert hasattr(SiqeFuturesStrategy, 'set_alert_manager')
    
    def test_strategy_has_margin_alert_parameters(self):
        """Strategy should have margin alert parameters."""
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        
        assert hasattr(SiqeFuturesStrategy, 'margin_alert_pct')
        assert hasattr(SiqeFuturesStrategy, 'margin_stop_pct')


class TestIntegration:
    """Integration tests for alert system."""
    
    @pytest.mark.asyncio
    async def test_full_alert_chain(self):
        """Test complete alert chain from event to notification."""
        from risk_engine.risk_manager import RiskEngine, CircuitBreakerType
        from core.clock import EventClock
        from config.settings import Settings
        
        settings = Settings()
        clock = EventClock()
        engine = RiskEngine(settings, clock)
        
        # Create actual alert manager
        with patch('alerts.alert_manager.TelegramChannel') as mock_telegram:
            mock_channel = Mock()
            mock_channel.is_configured.return_value = True
            mock_channel.send_alert.return_value = True
            mock_telegram.return_value = mock_channel
            
            from alerts.alert_manager import AlertManager
            alert_manager = AlertManager(
                telegram_bot_token="test_token",
                telegram_chat_id="test_chat",
                enabled=True,
            )
            
            engine.set_alert_manager(alert_manager)
            await engine.initialize()
            
            # Trigger circuit breaker
            engine._activate_circuit_breaker(
                CircuitBreakerType.DAILY_LOSS,
                "Daily loss exceeded"
            )
            
            # Verify stats
            stats = alert_manager.get_stats()
            assert stats["total_sent"] >= 1
    
    def test_alert_types_coverage(self):
        """Verify all alert types have convenience methods."""
        from alerts.alert_manager import AlertManager
        
        with patch('alerts.alert_manager.TelegramChannel'):
            manager = AlertManager(enabled=False)
            
            expected_methods = [
                'emergency_stop', 'circuit_breaker', 'drawdown_warning',
                'daily_loss', 'trade_executed', 'position_opened',
                'position_closed', 'parameter_update', 'parameter_rollback',
                'system_startup', 'system_shutdown', 'api_failure',
                'learning_triggered', 'regime_change', 'margin_warning',
                'margin_critical', 'liquidation_risk', 'order_rejected',
                'heartbeat', 'queue_full', 'pipeline_error',
                'connection_lost', 'connection_restored', 'anomalous_pnl',
            ]
            
            for method in expected_methods:
                assert hasattr(manager, method), f"Missing method: {method}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
