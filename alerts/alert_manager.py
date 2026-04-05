"""
SIQE V3 - Alert Manager

Centralized alert dispatch with rate limiting and multi-channel support.
"""
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from alerts.alert_types import (
    Alert,
    AlertSeverity,
    AlertType,
    RATE_LIMITS,
    create_alert,
)
from alerts.channels import BaseChannel, TelegramChannel, create_telegram_channel

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Centralized alert management with rate limiting.
    
    Features:
    - Multiple notification channels (Telegram, etc.)
    - Rate limiting per alert type
    - Severity-based filtering
    - Async and sync sending
    """
    
    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        enabled: bool = True,
        default_rate_limit: int = 60,
    ):
        self.enabled = enabled
        self.default_rate_limit = default_rate_limit
        
        # Rate limiting state
        self._last_alert_time: Dict[str, float] = {}
        self._lock = threading.Lock()
        
        # Channels
        self._channels: list[BaseChannel] = []
        
        # Initialize Telegram if configured
        if telegram_bot_token and telegram_chat_id:
            self.telegram = TelegramChannel(telegram_bot_token, telegram_chat_id)
            if self.telegram.is_configured():
                self._channels.append(self.telegram)
                logger.info("Telegram channel configured and added")
            else:
                logger.warning("Telegram channel not properly configured")
        else:
            self.telegram = create_telegram_channel()
            if self.telegram.is_configured():
                self._channels.append(self.telegram)
                logger.info("Telegram channel configured from environment")
        
        # Alert history
        self._alert_history: list[Alert] = []
        self._max_history = 1000
        
        # Statistics
        self._stats = {
            "total_sent": 0,
            "total_suppressed": 0,
            "by_type": defaultdict(int),
            "by_severity": defaultdict(int),
        }
    
    @property
    def channels(self) -> list[BaseChannel]:
        """Get configured channels."""
        return self._channels
    
    def is_configured(self) -> bool:
        """Check if at least one channel is configured."""
        return any(c.is_configured() for c in self._channels)
    
    def _should_suppress(self, alert: Alert) -> bool:
        """Check if alert should be suppressed due to rate limiting."""
        if alert.severity == AlertSeverity.CRITICAL:
            return False  # Never suppress critical alerts
        
        key = alert.rate_limit_key or f"{alert.alert_type.value}_{alert.severity.value}"
        rate_limit = RATE_LIMITS.get(alert.severity, self.default_rate_limit)
        
        if rate_limit <= 0:
            return False
        
        with self._lock:
            last_time = self._last_alert_time.get(key, 0)
            current_time = time.time()
            
            if current_time - last_time < rate_limit:
                return True
            
            self._last_alert_time[key] = current_time
            return False
    
    def _record_alert(self, alert: Alert, sent: bool) -> None:
        """Record alert in history and stats."""
        with self._lock:
            self._alert_history.append(alert)
            if len(self._alert_history) > self._max_history:
                self._alert_history = self._alert_history[-self._max_history:]
            
            if sent:
                self._stats["total_sent"] += 1
            else:
                self._stats["total_suppressed"] += 1
            
            self._stats["by_type"][alert.alert_type.value] += 1
            self._stats["by_severity"][alert.severity.value] += 1
    
    def send(self, alert: Alert) -> bool:
        """
        Send an alert through all configured channels.
        
        Args:
            alert: The Alert object to send
            
        Returns:
            True if at least one channel sent successfully
        """
        if not self.enabled:
            return False
        
        if not self.is_configured():
            logger.debug("No channels configured, skipping alert")
            return False
        
        # Check rate limiting
        if self._should_suppress(alert):
            logger.debug(f"Alert suppressed (rate limit): {alert.alert_type.value}")
            self._record_alert(alert, sent=False)
            return False
        
        # Send to all channels
        results = []
        for channel in self._channels:
            if channel.is_configured():
                try:
                    if hasattr(channel, 'send_alert'):
                        result = channel.send_alert(alert)
                    else:
                        result = channel.send(alert.message)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Channel send error: {e}")
        
        success = any(results)
        self._record_alert(alert, sent=success)
        
        return success
    
    def dispatch(
        self,
        alert_type: AlertType,
        message: str,
        severity: Optional[AlertSeverity] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Convenience method to create and send an alert.
        
        Args:
            alert_type: Type of alert
            message: Alert message
            severity: Override auto-detected severity
            metadata: Additional data to include
            
        Returns:
            True if sent successfully
        """
        alert = create_alert(alert_type, message, metadata, severity)
        return self.send(alert)
    
    # Convenience methods for common alerts
    
    def emergency_stop(self, reason: str, **metadata) -> bool:
        """Send emergency stop alert."""
        return self.dispatch(
            AlertType.EMERGENCY_STOP,
            f"🚨 EMERGENCY STOP ACTIVATED\n\nReason: {reason}",
            AlertSeverity.CRITICAL,
            metadata,
        )
    
    def circuit_breaker(self, breaker_name: str, reason: str, **metadata) -> bool:
        """Send circuit breaker triggered alert."""
        return self.dispatch(
            AlertType.CIRCUIT_BREAKER,
            f"⚠️ Circuit breaker triggered: {breaker_name}\n\nReason: {reason}",
            AlertSeverity.HIGH,
            {**metadata, "breaker": breaker_name},
        )
    
    def drawdown_warning(self, current_dd: float, max_dd: float, **metadata) -> bool:
        """Send drawdown warning."""
        return self.dispatch(
            AlertType.DRAWDOWN_WARNING,
            f"⚠️ Drawdown Warning\n\nCurrent: {current_dd:.2%}\nLimit: {max_dd:.2%}",
            AlertSeverity.HIGH if current_dd < max_dd else AlertSeverity.CRITICAL,
            {**metadata, "current_dd": current_dd, "max_dd": max_dd},
        )
    
    def daily_loss(self, loss: float, limit: float, **metadata) -> bool:
        """Send daily loss alert."""
        return self.dispatch(
            AlertType.DAILY_LOSS,
            f"🚨 Daily Loss Limit Exceeded\n\nLoss: {loss:.2%}\nLimit: {limit:.2%}",
            AlertSeverity.CRITICAL,
            {**metadata, "loss": loss, "limit": limit},
        )
    
    def trade_executed(
        self,
        direction: str,
        volume: float,
        price: float,
        symbol: str = "BTCUSDT",
        **metadata
    ) -> bool:
        """Send trade executed alert."""
        emoji = "📈" if direction.upper() == "LONG" else "📉"
        return self.dispatch(
            AlertType.TRADE_EXECUTED,
            f"{emoji} Trade Executed\n\n{direction.upper()} {volume} {symbol}\nPrice: ${price:,.2f}",
            AlertSeverity.LOW,
            {**metadata, "direction": direction, "volume": volume, "price": price},
        )
    
    def position_opened(self, side: str, volume: float, entry_price: float, **metadata) -> bool:
        """Send position opened alert."""
        return self.dispatch(
            AlertType.POSITION_OPENED,
            f"📊 Position Opened\n\n{side.upper()} {volume} BTC\nEntry: ${entry_price:,.2f}",
            AlertSeverity.LOW,
            {**metadata, "side": side, "volume": volume, "entry_price": entry_price},
        )
    
    def position_closed(self, pnl: float, side: str, duration_min: int, **metadata) -> bool:
        """Send position closed alert."""
        emoji = "✅" if pnl >= 0 else "❌"
        return self.dispatch(
            AlertType.POSITION_CLOSED,
            f"{emoji} Position Closed\n\nPnL: ${pnl:.2f}\nDuration: {duration_min} min",
            AlertSeverity.LOW,
            {**metadata, "pnl": pnl, "duration": duration_min},
        )
    
    def parameter_update(self, strategy: str, changes: Dict[str, Any], **metadata) -> bool:
        """Send parameter update alert."""
        change_str = "\n".join([f"  • {k}: {v[0]:.4f} → {v[1]:.4f}" if isinstance(v, tuple) else f"  • {k}: {v}" for k, v in changes.items()])
        return self.dispatch(
            AlertType.PARAMETER_UPDATE,
            f"⚡ Parameter Update\n\nStrategy: {strategy}\n\nChanges:\n{change_str}",
            AlertSeverity.MEDIUM,
            {**metadata, "strategy": strategy, "changes": changes},
        )
    
    def parameter_rollback(self, strategy: str, reason: str, **metadata) -> bool:
        """Send parameter rollback alert."""
        return self.dispatch(
            AlertType.PARAMETER_ROLLBACK,
            f"🔄 Parameter Rollback\n\nStrategy: {strategy}\nReason: {reason}",
            AlertSeverity.MEDIUM,
            {**metadata, "strategy": strategy, "reason": reason},
        )
    
    def system_startup(self, symbol: str, leverage: int, **metadata) -> bool:
        """Send system startup alert."""
        return self.dispatch(
            AlertType.SYSTEM_STARTUP,
            f"✅ SIQE V3 Started\n\nSymbol: {symbol}\nLeverage: {leverage}x\nServer: TESTNET",
            AlertSeverity.INFO,
            {**metadata, "symbol": symbol, "leverage": leverage},
        )
    
    def system_shutdown(self, reason: str = "Manual", **metadata) -> bool:
        """Send system shutdown alert."""
        return self.dispatch(
            AlertType.SYSTEM_SHUTDOWN,
            f"🛑 SIQE V3 Stopped\n\nReason: {reason}",
            AlertSeverity.INFO,
            {**metadata, "reason": reason},
        )
    
    def api_failure(self, endpoint: str, error: str, **metadata) -> bool:
        """Send API failure alert."""
        return self.dispatch(
            AlertType.API_FAILURE,
            f"⚠️ API Failure\n\nEndpoint: {endpoint}\nError: {error}",
            AlertSeverity.HIGH,
            {**metadata, "endpoint": endpoint, "error": error},
        )
    
    def learning_triggered(self, strategy: str, interval: int, **metadata) -> bool:
        """Send learning triggered alert."""
        return self.dispatch(
            AlertType.LEARNING_TRIGGERED,
            f"⚡ Learning Triggered\n\nStrategy: {strategy}\nInterval: {interval} trades",
            AlertSeverity.MEDIUM,
            {**metadata, "strategy": strategy, "interval": interval},
        )
    
    def regime_change(self, old_regime: str, new_regime: str, **metadata) -> bool:
        """Send regime change alert."""
        return self.dispatch(
            AlertType.REGIME_CHANGE,
            f"🔄 Regime Change\n\n{old_regime} → {new_regime}",
            AlertSeverity.LOW,
            {**metadata, "old_regime": old_regime, "new_regime": new_regime},
        )
    
    def margin_warning(self, margin_ratio: float, threshold: float, **metadata) -> bool:
        """Send margin warning alert."""
        return self.dispatch(
            AlertType.MARGIN_WARNING,
            f"⚠️ Margin Warning\n\nRatio: {margin_ratio:.1%}\nThreshold: {threshold:.1%}",
            AlertSeverity.HIGH,
            {**metadata, "margin_ratio": margin_ratio, "threshold": threshold},
        )
    
    def margin_critical(self, margin_ratio: float, threshold: float, **metadata) -> bool:
        """Send critical margin alert - imminent liquidation."""
        return self.dispatch(
            AlertType.MARGIN_CRITICAL,
            f"🚨 MARGIN CRITICAL\n\nRatio: {margin_ratio:.1%}\nThreshold: {threshold:.1%}\nLIQUIDATION IMMINENT!",
            AlertSeverity.CRITICAL,
            {**metadata, "margin_ratio": margin_ratio, "threshold": threshold},
        )
    
    def liquidation_risk(self, current_price: float, liquidation_price: float, distance_pct: float, **metadata) -> bool:
        """Send liquidation risk alert."""
        return self.dispatch(
            AlertType.LIQUIDATION_RISK,
            f"🚨 LIQUIDATION RISK\n\nCurrent: ${current_price:,.2f}\nLiquidation: ${liquidation_price:,.2f}\nDistance: {distance_pct:.1f}%",
            AlertSeverity.CRITICAL,
            {**metadata, "current_price": current_price, "liquidation_price": liquidation_price, "distance_pct": distance_pct},
        )
    
    def order_rejected(self, reason: str, symbol: str = "BTCUSDT", **metadata) -> bool:
        """Send order rejected alert."""
        return self.dispatch(
            AlertType.ORDER_REJECTED,
            f"⚠️ Order Rejected\n\n{symbol}\nReason: {reason}",
            AlertSeverity.HIGH,
            {**metadata, "reason": reason, "symbol": symbol},
        )
    
    def heartbeat(self, uptime_seconds: int, status: str = "OK", **metadata) -> bool:
        """Send heartbeat alert."""
        return self.dispatch(
            AlertType.HEARTBEAT,
            f"💓 Heartbeat\n\nUptime: {uptime_seconds}s\nStatus: {status}",
            AlertSeverity.INFO,
            {**metadata, "uptime_seconds": uptime_seconds, "status": status},
        )
    
    def queue_full(self, queue_size: int, max_size: int, **metadata) -> bool:
        """Send queue full alert."""
        return self.dispatch(
            AlertType.QUEUE_FULL,
            f"⚠️ Queue Full\n\nSize: {queue_size}/{max_size}\nEvents being dropped!",
            AlertSeverity.HIGH,
            {**metadata, "queue_size": queue_size, "max_size": max_size},
        )
    
    def pipeline_error(self, stage: str, error: str, **metadata) -> bool:
        """Send pipeline error alert."""
        return self.dispatch(
            AlertType.PIPELINE_ERROR,
            f"⚠️ Pipeline Error\n\nStage: {stage}\nError: {error}",
            AlertSeverity.HIGH,
            {**metadata, "stage": stage, "error": error},
        )
    
    def connection_lost(self, endpoint: str, **metadata) -> bool:
        """Send connection lost alert."""
        return self.dispatch(
            AlertType.CONNECTION_LOST,
            f"🚨 Connection Lost\n\nEndpoint: {endpoint}",
            AlertSeverity.CRITICAL,
            {**metadata, "endpoint": endpoint},
        )
    
    def connection_restored(self, endpoint: str, **metadata) -> bool:
        """Send connection restored alert."""
        return self.dispatch(
            AlertType.CONNECTION_RESTORED,
            f"✅ Connection Restored\n\nEndpoint: {endpoint}",
            AlertSeverity.MEDIUM,
            {**metadata, "endpoint": endpoint},
        )
    
    def anomalous_pnl(self, expected_pnl: float, actual_pnl: float, deviation_sigma: float, **metadata) -> bool:
        """Send anomalous PnL alert."""
        return self.dispatch(
            AlertType.ANOMALOUS_PNL,
            f"⚠️ Anomalous PnL\n\nExpected: ${expected_pnl:.2f}\nActual: ${actual_pnl:.2f}\nDeviation: {deviation_sigma:.1f}σ",
            AlertSeverity.HIGH,
            {**metadata, "expected_pnl": expected_pnl, "actual_pnl": actual_pnl, "deviation_sigma": deviation_sigma},
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        with self._lock:
            return {
                **self._stats,
                "channels_configured": len([c for c in self._channels if c.is_configured()]),
                "history_size": len(self._alert_history),
                "rate_limits_active": len(self._last_alert_time),
            }
    
    def get_recent_alerts(self, limit: int = 10) -> list[Dict[str, Any]]:
        """Get recent alerts."""
        with self._lock:
            return [a.to_dict() for a in self._alert_history[-limit:]]


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global AlertManager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def init_alert_manager(
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    enabled: bool = True,
) -> AlertManager:
    """Initialize the global AlertManager."""
    global _alert_manager
    _alert_manager = AlertManager(
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        enabled=enabled,
    )
    return _alert_manager
