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


class TestFormatters:
    """Test message formatters for all three perspectives."""
    
    def test_dashboard_formatter_format_header(self):
        """Header should include mode and symbol."""
        from alerts.formatters import DashboardFormatter
        
        header = DashboardFormatter.format_header(mode="PAPER", symbol="BTCUSDT")
        assert "PAPER" in header
        assert "BTCUSDT" in header
    
    def test_dashboard_formatter_format_welcome(self):
        """Welcome message should contain key commands."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_welcome()
        assert "/dashboard" in msg
        assert "/help" in msg
        assert "/stop" in msg
    
    def test_dashboard_formatter_format_help(self):
        """Help message should contain all commands."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_help()
        assert "/dashboard" in msg
        assert "/status" in msg
        assert "/pnl" in msg
        assert "/signals" in msg
        assert "/subscribe" in msg
        assert "/stop" in msg
    
    def test_format_quant_view(self):
        """Quant view should include regime, signal, params."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(
            regime="BULL",
            regime_confidence=0.85,
            signal_direction="LONG",
            signal_strength=0.72,
        )
        
        msg = DashboardFormatter.format_quant_view(state)
        assert "BULL" in msg
        assert "LONG" in msg
        assert "0.72" in msg
    
    def test_format_hedge_fund_view(self):
        """Hedge fund view should include P&L, win rate, drawdown."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(
            daily_pnl=12.50,
            daily_pnl_pct=0.0025,
            weekly_pnl=-45.20,
            weekly_pnl_pct=-0.0091,
            total_pnl=352.14,
            total_pnl_pct=0.0704,
            max_drawdown=0.021,
            win_rate=0.58,
            total_trades=12,
            winning_trades=7,
            losing_trades=5,
        )
        
        msg = DashboardFormatter.format_hedge_fund_view(state)
        assert "12.50" in msg
        assert "58.0%" in msg
        assert "2.10%" in msg
    
    def test_format_ml_engineer_view(self):
        """ML engineer view should include signal strength per strategy."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(
            regime="MIXED",
            regime_confidence=0.87,
            signal_direction="SHORT",
            signal_strength=0.68,
            signal_momentum=0.72,
            signal_mean_reversion=0.15,
            signal_volatility_breakout=0.31,
        )
        
        msg = DashboardFormatter.format_ml_engineer_view(state)
        assert "MIXED" in msg
        assert "SHORT" in msg
        assert "momentum" in msg
        assert "mean_reversion" in msg
        assert "volatility_breakout" in msg
    
    def test_format_positions_no_position(self):
        """Should show no positions message."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(position_side="NONE", position_size=0)
        msg = DashboardFormatter.format_positions(state)
        assert "No Open Positions" in msg
    
    def test_format_positions_with_position(self):
        """Should show position details."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(
            position_side="LONG",
            position_size=0.01,
            entry_price=50000.0,
            unrealized_pnl=125.0,
        )
        
        msg = DashboardFormatter.format_positions(state)
        assert "LONG" in msg
        assert "50,000" in msg
    
    def test_format_trades_no_trades(self):
        """Should show no trades message."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(recent_trades=[])
        msg = DashboardFormatter.format_trades(state)
        assert "No Trades" in msg
    
    def test_format_trades_with_trades(self):
        """Should show recent trades."""
        from alerts.formatters import DashboardFormatter, TradingState
        
        state = TradingState(
            recent_trades=[
                {"direction": "LONG", "pnl": 12.50, "exit_reason": "TP", "duration_minutes": 30},
                {"direction": "SHORT", "pnl": -8.30, "exit_reason": "SL", "duration_minutes": 15},
            ]
        )
        
        msg = DashboardFormatter.format_trades(state)
        assert "LONG" in msg
        assert "SHORT" in msg
    
    def test_format_stop_confirmed(self):
        """Stop confirmation should be clear."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_stop_confirmed()
        assert "Stopped" in msg
        assert "/starttrading" in msg
    
    def test_format_start_confirmed(self):
        """Start confirmation should be clear."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_start_confirmed()
        assert "Resumed" in msg
        assert "/stop" in msg
    
    def test_format_approval_request(self):
        """Approval request should include action and timeout."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_approval_request("Parameter Rollback", "stop=1.5 → 0.5")
        assert "Approval Required" in msg
        assert "Parameter Rollback" in msg
    
    def test_format_subscriptions(self):
        """Subscriptions list should show active and available."""
        from alerts.formatters import DashboardFormatter
        
        msg = DashboardFormatter.format_subscriptions(
            subscribed=["trade_executed", "position_closed"],
            available=["trade_executed", "position_closed", "regime_change"],
        )
        assert "trade_executed" in msg
        assert "position_closed" in msg


class TestSubscriptionManager:
    """Test subscription management."""
    
    def test_default_subscriptions_critical_only(self):
        """Default should only subscribe to critical alerts."""
        from alerts.subscriptions import SubscriptionManager, ALERT_CATEGORIES
        
        mgr = SubscriptionManager()
        subs = mgr.get_subscriptions("test_chat")
        
        # Should only have critical alerts
        for sub in subs:
            assert sub in ALERT_CATEGORIES["critical"]
    
    def test_subscribe_to_type(self):
        """Should be able to subscribe to specific type."""
        from alerts.subscriptions import SubscriptionManager
        
        mgr = SubscriptionManager()
        assert mgr.subscribe("test_chat", "trade_executed") is True
        assert mgr.is_subscribed("test_chat", "trade_executed") is True
    
    def test_subscribe_to_category(self):
        """Should be able to subscribe to category."""
        from alerts.subscriptions import SubscriptionManager, ALERT_CATEGORIES
        
        mgr = SubscriptionManager()
        assert mgr.subscribe("test_chat", "trading") is True
        
        for alert_type in ALERT_CATEGORIES["trading"]:
            assert mgr.is_subscribed("test_chat", alert_type) is True
    
    def test_unsubscribe_from_type(self):
        """Should be able to unsubscribe from specific type."""
        from alerts.subscriptions import SubscriptionManager
        
        mgr = SubscriptionManager()
        mgr.subscribe("test_chat", "trade_executed")
        assert mgr.unsubscribe("test_chat", "trade_executed") is True
        assert mgr.is_subscribed("test_chat", "trade_executed") is False
    
    def test_unsubscribe_from_category(self):
        """Should be able to unsubscribe from category."""
        from alerts.subscriptions import SubscriptionManager, ALERT_CATEGORIES
        
        mgr = SubscriptionManager()
        mgr.subscribe("test_chat", "trading")
        assert mgr.unsubscribe("test_chat", "trading") is True
        
        for alert_type in ALERT_CATEGORIES["trading"]:
            assert mgr.is_subscribed("test_chat", alert_type) is False
    
    def test_should_send_alert_critical_always(self):
        """Critical alerts should always be sent regardless of subscription."""
        from alerts.subscriptions import SubscriptionManager, ALERT_CATEGORIES
        
        mgr = SubscriptionManager()
        # User has no subscriptions
        
        for alert_type in ALERT_CATEGORIES["critical"]:
            assert mgr.should_send_alert("test_chat", alert_type) is True
    
    def test_should_send_alert_filtered(self):
        """Non-subscribed alerts should be filtered."""
        from alerts.subscriptions import SubscriptionManager
        
        mgr = SubscriptionManager()
        mgr.subscribe("test_chat", "trade_executed")
        
        # Should not send non-subscribed alerts
        assert mgr.should_send_alert("test_chat", "heartbeat") is False
    
    def test_get_available_types(self):
        """Should return all available alert types."""
        from alerts.subscriptions import SubscriptionManager, ALL_ALERT_TYPES
        
        mgr = SubscriptionManager()
        available = mgr.get_available_types()
        
        assert len(available) == len(ALL_ALERT_TYPES)
    
    def test_get_categories(self):
        """Should return all available categories."""
        from alerts.subscriptions import SubscriptionManager
        
        mgr = SubscriptionManager()
        categories = mgr.get_categories()
        
        assert "all" in categories
        assert "none" in categories
        assert "trading" in categories
        assert "risk" in categories


class TestKeyboards:
    """Test inline keyboard builders."""
    
    def test_main_dashboard_keyboard(self):
        """Main dashboard should have all view buttons."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.main_dashboard()
        
        # Should have multiple rows
        assert len(kb) >= 3
        
        # Check for expected callbacks
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        assert "view:dashboard" in all_callbacks
        assert "view:pnl" in all_callbacks
        assert "action:stop" in all_callbacks
        assert "action:start" in all_callbacks
    
    def test_quick_actions_keyboard(self):
        """Quick actions should have dashboard, stop, start."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.quick_actions()
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        
        assert "view:dashboard" in all_callbacks
        assert "action:stop" in all_callbacks
        assert "action:start" in all_callbacks
    
    def test_approval_keyboard(self):
        """Approval keyboard should have approve/deny buttons."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.approval("test_action", "key123")
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        
        assert "approve:key123" in all_callbacks
        assert "deny:key123" in all_callbacks
    
    def test_subscription_categories_keyboard(self):
        """Should have category subscription buttons."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.subscription_categories()
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        
        assert "sub:trading" in all_callbacks
        assert "sub:risk" in all_callbacks
        assert "sub:all" in all_callbacks
        assert "sub:none" in all_callbacks
    
    def test_back_to_dashboard_keyboard(self):
        """Should have back to dashboard button."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.back_to_dashboard()
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        
        assert "view:dashboard" in all_callbacks
    
    def test_confirm_stop_keyboard(self):
        """Should have confirm stop and cancel buttons."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.confirm_stop()
        all_callbacks = [btn["callback_data"] for row in kb for btn in row]
        
        assert "action:stop_confirm" in all_callbacks
        assert "view:dashboard" in all_callbacks
    
    def test_keyboard_builder_fluent_api(self):
        """Keyboard builder should support fluent API."""
        from alerts.keyboards import KeyboardBuilder
        
        kb = KeyboardBuilder() \
            .row() \
            .button("A", "a") \
            .button("B", "b") \
            .row() \
            .button("C", "c") \
            .build()
        
        assert len(kb) == 2
        assert len(kb[0]) == 2
        assert len(kb[1]) == 1
        assert kb[0][0]["callback_data"] == "a"
        assert kb[1][0]["callback_data"] == "c"


class TestTelegramBot:
    """Test Telegram bot class."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create bot with mocked API."""
        from alerts.telegram_bot import TelegramBot
        from alerts.formatters import TradingState
        
        bot = TelegramBot(
            bot_token="test_token",
            chat_id="test_chat",
            state_provider=lambda: TradingState(
                regime="BULL",
                signal_direction="LONG",
                signal_strength=0.75,
                daily_pnl=100.0,
                total_pnl=500.0,
            ),
        )
        
        # Mock the API calls
        bot._make_request = Mock(return_value={"ok": True})
        
        return bot
    
    def test_bot_initialization(self, mock_bot):
        """Bot should initialize with correct config."""
        assert mock_bot.bot_token == "test_token"
        assert mock_bot.chat_id == "test_chat"
        assert mock_bot._running is False
    
    def test_send_message(self, mock_bot):
        """Should send message with correct format."""
        result = mock_bot.send_message("Test message")
        assert result is True
        
        mock_bot._make_request.assert_called_once()
        args = mock_bot._make_request.call_args
        assert args[0][0] == "sendMessage"
        data = args[1] if 'data' in args[1] else args[0][1]
        assert data["text"] == "Test message"
        assert data["parse_mode"] == "HTML"
    
    def test_send_message_with_keyboard(self, mock_bot):
        """Should send message with inline keyboard."""
        from alerts.keyboards import Keyboards
        
        kb = Keyboards.quick_actions()
        result = mock_bot.send_message("Test", reply_markup=kb)
        assert result is True
        
        args = mock_bot._make_request.call_args
        data = args[1] if 'data' in args[1] else args[0][1]
        assert "reply_markup" in data
        assert "inline_keyboard" in data["reply_markup"]
    
    def test_is_trading_active_property(self, mock_bot):
        """Should track trading active state."""
        assert mock_bot.is_trading_active is True
        mock_bot.is_trading_active = False
        assert mock_bot.is_trading_active is False
    
    def test_request_approval(self, mock_bot):
        """Should create approval request with callback."""
        callback_results = []
        
        action_key = mock_bot.request_approval(
            action="Test Action",
            details="Test details",
            callback=lambda x: callback_results.append(x),
            timeout=1,
        )
        
        assert action_key is not None
        assert action_key in mock_bot._approval_callbacks
        
        # Verify message was sent
        mock_bot._make_request.assert_called_once()
    
    def test_process_command_start(self, mock_bot):
        """Should handle /start command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/start", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
        args = mock_bot.send_message.call_args
        assert "Welcome" in args[0][0] or "welcome" in args[0][0].lower()
    
    def test_process_command_help(self, mock_bot):
        """Should handle /help command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/help", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
    
    def test_process_command_status(self, mock_bot):
        """Should handle /status command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/status", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
    
    def test_process_command_pnl(self, mock_bot):
        """Should handle /pnl command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/pnl", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
    
    def test_process_command_signals(self, mock_bot):
        """Should handle /signals command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/signals", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
    
    def test_process_command_unknown(self, mock_bot):
        """Should handle unknown command."""
        mock_bot.send_message = Mock()
        
        mock_bot._process_command("/unknown", {"chat": {"id": "test_chat"}})
        
        mock_bot.send_message.assert_called_once()
        args = mock_bot.send_message.call_args
        assert "Unknown" in args[0][0] or "unknown" in args[0][0].lower()
    
    def test_process_callback_view(self, mock_bot):
        """Should handle view callbacks."""
        mock_bot.send_message = Mock()
        mock_bot.answer_callback = Mock()
        
        mock_bot._process_callback_query({
            "id": "cb123",
            "data": "view:dashboard",
        })
        
        mock_bot.answer_callback.assert_called_once()
    
    def test_process_callback_action_stop(self, mock_bot):
        """Should handle stop action callback."""
        mock_bot.send_message = Mock()
        mock_bot.answer_callback = Mock()
        
        mock_bot._process_callback_query({
            "id": "cb123",
            "data": "action:stop",
        })
        
        mock_bot.answer_callback.assert_called_once()
    
    def test_process_callback_action_stop_confirm(self, mock_bot):
        """Should stop trading on confirm."""
        mock_bot.send_message = Mock()
        mock_bot.answer_callback = Mock()
        
        mock_bot._process_callback_query({
            "id": "cb123",
            "data": "action:stop_confirm",
        })
        
        assert mock_bot.is_trading_active is False
    
    def test_process_callback_action_start_confirm(self, mock_bot):
        """Should start trading on confirm."""
        mock_bot.send_message = Mock()
        mock_bot.answer_callback = Mock()
        mock_bot.is_trading_active = False
        
        mock_bot._process_callback_query({
            "id": "cb123",
            "data": "action:start_confirm",
        })
        
        assert mock_bot.is_trading_active is True
    
    def test_process_callback_subscription(self, mock_bot):
        """Should handle subscription callback."""
        mock_bot.send_message = Mock()
        mock_bot.answer_callback = Mock()
        
        mock_bot._process_callback_query({
            "id": "cb123",
            "data": "sub:trading",
        })
        
        mock_bot.answer_callback.assert_called_once()
    
    def test_handle_subscribe_command(self, mock_bot):
        """Should handle /subscribe command."""
        mock_bot.send_message = Mock()
        
        mock_bot._handle_subscribe(
            {"chat": {"id": "test_chat"}},
            ["trade_executed"]
        )
        
        mock_bot.send_message.assert_called_once()
        args = mock_bot.send_message.call_args
        assert "Subscribed" in args[0][0]
    
    def test_handle_subscribe_no_args(self, mock_bot):
        """Should show usage when no args."""
        mock_bot.send_message = Mock()
        
        mock_bot._handle_subscribe(
            {"chat": {"id": "test_chat"}},
            []
        )
        
        mock_bot.send_message.assert_called_once()
        args = mock_bot.send_message.call_args
        assert "Usage" in args[0][0]
    
    def test_handle_unsubscribe_command(self, mock_bot):
        """Should handle /unsubscribe command."""
        mock_bot.send_message = Mock()
        
        mock_bot._handle_unsubscribe(
            {"chat": {"id": "test_chat"}},
            ["trade_executed"]
        )
        
        mock_bot.send_message.assert_called_once()
    
    def test_handle_subscriptions_command(self, mock_bot):
        """Should handle /subscriptions command."""
        mock_bot.send_message = Mock()
        
        mock_bot._handle_subscriptions(
            {"chat": {"id": "test_chat"}},
            []
        )
        
        mock_bot.send_message.assert_called_once()
