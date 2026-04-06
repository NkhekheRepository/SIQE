"""
SIQE V3 - Subscription Management

Manages user subscriptions to specific alert types with category support.
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


ALERT_CATEGORIES = {
    "trading": [
        "trade_executed",
        "position_opened", 
        "position_closed",
    ],
    "risk": [
        "drawdown_warning",
        "daily_loss",
        "margin_warning",
        "margin_critical",
        "liquidation_risk",
    ],
    "signals": [
        "regime_change",
        "learning_triggered",
    ],
    "regime": [
        "regime_change",
        "bull_started",
        "bear_started",
        "volatile_regime",
        "ranging_regime",
    ],
    "system": [
        "system_startup",
        "system_shutdown",
        "heartbeat",
        "circuit_breaker",
    ],
    "critical": [
        "emergency_stop",
        "liquidation_risk",
        "connection_lost",
    ],
}

ALL_ALERT_TYPES = [
    "trade_executed",
    "position_opened",
    "position_closed",
    "drawdown_warning",
    "daily_loss",
    "margin_warning",
    "margin_critical",
    "liquidation_risk",
    "regime_change",
    "learning_triggered",
    "system_startup",
    "system_shutdown",
    "heartbeat",
    "circuit_breaker",
    "emergency_stop",
    "connection_lost",
    "connection_restored",
    "order_rejected",
    "api_failure",
    "parameter_update",
    "parameter_rollback",
]

CATEGORY_ALIASES = {
    "all": ALL_ALERT_TYPES,
    "none": [],
    "trading": ALERT_CATEGORIES["trading"],
    "risk": ALERT_CATEGORIES["risk"],
    "signals": ALERT_CATEGORIES["signals"],
    "system": ALERT_CATEGORIES["system"],
    "critical": ALERT_CATEGORIES["critical"],
}


@dataclass
class SubscriptionConfig:
    """Subscription configuration for a user."""
    chat_id: str
    subscribed_types: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Default: subscribe to critical only for safety
    @classmethod
    def create_default(cls, chat_id: str) -> "SubscriptionConfig":
        """Create default subscription (critical alerts only)."""
        return cls(
            chat_id=chat_id,
            subscribed_types=set(ALERT_CATEGORIES["critical"]),
        )


class SubscriptionManager:
    """
    Manages user subscriptions to alert types.
    
    Features:
    - Per-user subscriptions
    - Category-based subscriptions
    - Thread-safe operations
    """
    
    def __init__(self):
        self._subscriptions: Dict[str, SubscriptionConfig] = {}
        self._lock = threading.RLock()  # Reentrant lock to avoid deadlock
        
        # Pending approvals (action -> timestamp)
        self._pending_approvals: Dict[str, datetime] = {}
    
    def _get_or_create(self, chat_id: str) -> SubscriptionConfig:
        """Get or create subscription config for chat_id."""
        with self._lock:
            if chat_id not in self._subscriptions:
                self._subscriptions[chat_id] = SubscriptionConfig.create_default(chat_id)
            return self._subscriptions[chat_id]
    
    def is_subscribed(self, chat_id: str, alert_type: str) -> bool:
        """Check if user is subscribed to alert type."""
        config = self._get_or_create(chat_id)
        return alert_type in config.subscribed_types
    
    def subscribe(self, chat_id: str, alert_type: str) -> bool:
        """
        Subscribe user to an alert type or category.
        
        Args:
            chat_id: User's Telegram chat ID
            alert_type: Alert type or category name
            
        Returns:
            True if subscribed successfully
        """
        alert_type_lower = alert_type.lower()
        
        # Check if it's a category
        if alert_type_lower in CATEGORY_ALIASES:
            types = CATEGORY_ALIASES[alert_type_lower]
            with self._lock:
                config = self._get_or_create(chat_id)
                config.subscribed_types.update(types)
                config.updated_at = datetime.utcnow()
            logger.info(f"User {chat_id} subscribed to category: {alert_type}")
            return True
        
        # Check if it's a valid alert type
        if alert_type_lower in [t.lower() for t in ALL_ALERT_TYPES]:
            # Normalize to the actual type name
            actual_type = next(t for t in ALL_ALERT_TYPES if t.lower() == alert_type_lower)
            with self._lock:
                config = self._get_or_create(chat_id)
                config.subscribed_types.add(actual_type)
                config.updated_at = datetime.utcnow()
            logger.info(f"User {chat_id} subscribed to: {actual_type}")
            return True
        
        logger.warning(f"Unknown alert type: {alert_type}")
        return False
    
    def unsubscribe(self, chat_id: str, alert_type: str) -> bool:
        """
        Unsubscribe user from an alert type or category.
        
        Args:
            chat_id: User's Telegram chat ID
            alert_type: Alert type or category name
            
        Returns:
            True if unsubscribed successfully
        """
        alert_type_lower = alert_type.lower()
        
        # Check if it's a category
        if alert_type_lower in CATEGORY_ALIASES:
            types = CATEGORY_ALIASES[alert_type_lower]
            with self._lock:
                config = self._get_or_create(chat_id)
                config.subscribed_types.difference_update(types)
                config.updated_at = datetime.utcnow()
            logger.info(f"User {chat_id} unsubscribed from category: {alert_type}")
            return True
        
        # Check if it's a valid alert type
        if alert_type_lower in [t.lower() for t in ALL_ALERT_TYPES]:
            actual_type = next(t for t in ALL_ALERT_TYPES if t.lower() == alert_type_lower)
            with self._lock:
                config = self._get_or_create(chat_id)
                config.subscribed_types.discard(actual_type)
                config.updated_at = datetime.utcnow()
            logger.info(f"User {chat_id} unsubscribed from: {actual_type}")
            return True
        
        logger.warning(f"Unknown alert type: {alert_type}")
        return False
    
    def get_subscriptions(self, chat_id: str) -> List[str]:
        """Get list of subscribed alert types."""
        config = self._get_or_create(chat_id)
        return sorted(list(config.subscribed_types))
    
    def get_available_types(self) -> List[str]:
        """Get list of available alert types."""
        return sorted(ALL_ALERT_TYPES)
    
    def get_categories(self) -> List[str]:
        """Get list of available categories."""
        return sorted(list(CATEGORY_ALIASES.keys()))
    
    def should_send_alert(self, chat_id: str, alert_type: str) -> bool:
        """Check if alert should be sent to user based on subscriptions."""
        with self._lock:
            if chat_id not in self._subscriptions:
                return True  # Default allow for new users
            
            config = self._subscriptions[chat_id]
            
            # Always send critical alerts regardless of subscription
            if alert_type.lower() in [t.lower() for t in ALERT_CATEGORIES["critical"]]:
                return True
            
            return alert_type in config.subscribed_types
    
    def add_pending_approval(self, action_key: str) -> None:
        """Add an action to pending approval."""
        with self._lock:
            self._pending_approvals[action_key] = datetime.utcnow()
    
    def remove_pending_approval(self, action_key: str) -> bool:
        """Remove a pending approval. Returns True if it existed."""
        with self._lock:
            if action_key in self._pending_approvals:
                del self._pending_approvals[action_key]
                return True
            return False
    
    def has_pending_approval(self, action_key: str) -> bool:
        """Check if action has pending approval."""
        with self._lock:
            return action_key in self._pending_approvals
    
    def get_pending_approvals(self) -> Dict[str, datetime]:
        """Get all pending approvals."""
        with self._lock:
            return dict(self._pending_approvals)


# Global subscription manager instance
_subscription_manager: Optional[SubscriptionManager] = None


def get_subscription_manager() -> SubscriptionManager:
    """Get or create the global SubscriptionManager."""
    global _subscription_manager
    if _subscription_manager is None:
        _subscription_manager = SubscriptionManager()
    return _subscription_manager
