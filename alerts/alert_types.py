"""
SIQE V3 - Alert Types

Defines alert data structures and severity levels.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"  # Emergency stop, system failure
    HIGH = "high"          # Circuit breaker triggered, significant risk
    MEDIUM = "medium"      # Parameter changes, rollbacks
    LOW = "low"            # Trade executed, position changes
    INFO = "info"          # System startup, shutdown, heartbeat


class AlertType(str, Enum):
    """Types of alerts."""
    EMERGENCY_STOP = "emergency_stop"
    CIRCUIT_BREAKER = "circuit_breaker"
    DRAWDOWN_WARNING = "drawdown_warning"
    DAILY_LOSS = "daily_loss"
    TRADE_EXECUTED = "trade_executed"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    PARAMETER_UPDATE = "parameter_update"
    PARAMETER_ROLLBACK = "parameter_rollback"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    API_FAILURE = "api_failure"
    LEARNING_TRIGGERED = "learning_triggered"
    REGIME_CHANGE = "regime_change"
    MARGIN_WARNING = "margin_warning"
    MARGIN_CRITICAL = "margin_critical"
    LIQUIDATION_RISK = "liquidation_risk"
    ORDER_REJECTED = "order_rejected"
    HEARTBEAT = "heartbeat"
    QUEUE_FULL = "queue_full"
    PIPELINE_ERROR = "pipeline_error"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    ANOMALOUS_PNL = "anomalous_pnl"


@dataclass
class Alert:
    """Alert data structure."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Rate limiting
    rate_limit_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    def to_telegram(self) -> str:
        """Format alert for Telegram using HTML."""
        emoji_map = {
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.HIGH: "⚠️",
            AlertSeverity.MEDIUM: "⚡",
            AlertSeverity.LOW: "📊",
            AlertSeverity.INFO: "✅",
        }
        
        emoji = emoji_map.get(self.severity, "📢")
        
        # Use HTML formatting for Telegram
        formatted = f"{emoji} <b>{self.alert_type.value.upper()}</b>\n\n"
        formatted += f"{self.message}\n\n"
        formatted += f"🕐 {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        if self.metadata:
            formatted += "\n\n📋 Details:"
            for key, value in self.metadata.items():
                formatted += f"\n  • {key}: {value}"
        
        return formatted


# Rate limit configuration (seconds)
RATE_LIMITS = {
    AlertSeverity.CRITICAL: 0,      # No limit for emergencies
    AlertSeverity.HIGH: 300,        # 5 min
    AlertSeverity.MEDIUM: 60,       # 1 min
    AlertSeverity.LOW: 10,          # 10 sec
    AlertSeverity.INFO: 60,         # 1 min
}

# Alert type to severity mapping
ALERT_SEVERITY_MAP = {
    AlertType.EMERGENCY_STOP: AlertSeverity.CRITICAL,
    AlertType.CIRCUIT_BREAKER: AlertSeverity.HIGH,
    AlertType.DRAWDOWN_WARNING: AlertSeverity.HIGH,
    AlertType.DAILY_LOSS: AlertSeverity.CRITICAL,
    AlertType.TRADE_EXECUTED: AlertSeverity.LOW,
    AlertType.POSITION_OPENED: AlertSeverity.LOW,
    AlertType.POSITION_CLOSED: AlertSeverity.LOW,
    AlertType.PARAMETER_UPDATE: AlertSeverity.MEDIUM,
    AlertType.PARAMETER_ROLLBACK: AlertSeverity.MEDIUM,
    AlertType.SYSTEM_STARTUP: AlertSeverity.INFO,
    AlertType.SYSTEM_SHUTDOWN: AlertSeverity.INFO,
    AlertType.API_FAILURE: AlertSeverity.HIGH,
    AlertType.LEARNING_TRIGGERED: AlertSeverity.MEDIUM,
    AlertType.REGIME_CHANGE: AlertSeverity.LOW,
    AlertType.MARGIN_WARNING: AlertSeverity.HIGH,
    AlertType.MARGIN_CRITICAL: AlertSeverity.CRITICAL,
    AlertType.LIQUIDATION_RISK: AlertSeverity.CRITICAL,
    AlertType.ORDER_REJECTED: AlertSeverity.HIGH,
    AlertType.HEARTBEAT: AlertSeverity.INFO,
    AlertType.QUEUE_FULL: AlertSeverity.HIGH,
    AlertType.PIPELINE_ERROR: AlertSeverity.HIGH,
    AlertType.CONNECTION_LOST: AlertSeverity.CRITICAL,
    AlertType.CONNECTION_RESTORED: AlertSeverity.MEDIUM,
    AlertType.ANOMALOUS_PNL: AlertSeverity.HIGH,
}


def create_alert(
    alert_type: AlertType,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    severity: Optional[AlertSeverity] = None,
) -> Alert:
    """Factory function to create an alert with automatic severity mapping."""
    if severity is None:
        severity = ALERT_SEVERITY_MAP.get(alert_type, AlertSeverity.INFO)
    
    return Alert(
        alert_type=alert_type,
        severity=severity,
        message=message,
        metadata=metadata or {},
        rate_limit_key=f"{alert_type.value}_{severity.value}",
    )
