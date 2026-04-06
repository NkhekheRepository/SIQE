"""
SIQE V3 - Keyboard Builders

Inline keyboard builders for Telegram bot interactions.
"""
from typing import Any, Dict, List, Optional, Tuple


class KeyboardBuilder:
    """Fluent API for building Telegram inline keyboards."""
    
    def __init__(self):
        self._keyboard: List[List[Dict[str, str]]] = []
        self._current_row: List[Dict[str, str]] = []
    
    def row(self) -> "KeyboardBuilder":
        """Start a new row."""
        if self._current_row:
            self._keyboard.append(self._current_row)
            self._current_row = []
        return self
    
    def button(
        self,
        text: str,
        callback_data: Optional[str] = None,
        url: Optional[str] = None,
    ) -> "KeyboardBuilder":
        """Add a button to the current row."""
        button: Dict[str, str] = {"text": text}
        
        if callback_data:
            button["callback_data"] = callback_data
        elif url:
            button["url"] = url
        
        self._current_row.append(button)
        return self
    
    def build(self) -> List[List[Dict[str, str]]]:
        """Build and return the keyboard."""
        if self._current_row:
            self._keyboard.append(self._current_row)
        return self._keyboard
    
    def reset(self) -> "KeyboardBuilder":
        """Reset the keyboard."""
        self._keyboard = []
        self._current_row = []
        return self


class Keyboards:
    """Pre-built keyboard layouts."""
    
    @staticmethod
    def main_dashboard() -> List[List[Dict[str, str]]]:
        """Main dashboard keyboard with views."""
        return KeyboardBuilder() \
            .row() \
            .button("📊 Dashboard", "view:dashboard") \
            .button("💰 P&L", "view:pnl") \
            .button("⚙️ Config", "view:params") \
            .row() \
            .button("📉 Signals", "view:signals") \
            .button("🏷️ Regime", "view:regime") \
            .button("📋 Trades", "view:trades") \
            .row() \
            .button("⏹️ STOP", "action:stop") \
            .button("▶️ START", "action:start") \
            .button("🔄 REFRESH", "action:refresh") \
            .build()
    
    @staticmethod
    def quick_actions() -> List[List[Dict[str, str]]]:
        """Quick action buttons."""
        return KeyboardBuilder() \
            .row() \
            .button("📊 Dashboard", "view:dashboard") \
            .button("⏹️ STOP", "action:stop") \
            .button("▶️ START", "action:start") \
            .build()
    
    @staticmethod
    def views_only() -> List[List[Dict[str, str]]]:
        """View-only keyboard."""
        return KeyboardBuilder() \
            .row() \
            .button("📊 Status", "view:status") \
            .button("💰 P&L", "view:pnl") \
            .button("📉 Signals", "view:signals") \
            .row() \
            .button("📋 Trades", "view:trades") \
            .button("🏷️ Regime", "view:regime") \
            .button("⚙️ Params", "view:params") \
            .build()
    
    @staticmethod
    def approval(action: str, action_key: str) -> List[List[Dict[str, str]]]:
        """Approval keyboard with Approve/Deny buttons."""
        return KeyboardBuilder() \
            .row() \
            .button("✅ Approve", f"approve:{action_key}") \
            .button("❌ Deny", f"deny:{action_key}") \
            .build()
    
    @staticmethod
    def subscription_categories() -> List[List[Dict[str, str]]]:
        """Subscription category keyboard."""
        return KeyboardBuilder() \
            .row() \
            .button("📈 Trading", "sub:trading") \
            .button("⚠️ Risk", "sub:risk") \
            .button("📊 Signals", "sub:signals") \
            .row() \
            .button("🔔 System", "sub:system") \
            .button("🚨 Critical", "sub:critical") \
            .row() \
            .button("✅ All", "sub:all") \
            .button("❌ None", "sub:none") \
            .build()
    
    @staticmethod
    def back_to_dashboard() -> List[List[Dict[str, str]]]:
        """Back to dashboard button."""
        return KeyboardBuilder() \
            .row() \
            .button("🔙 Dashboard", "view:dashboard") \
            .build()
    
    @staticmethod
    def confirm_stop() -> List[List[Dict[str, str]]]:
        """Confirmation keyboard for stop action."""
        return KeyboardBuilder() \
            .row() \
            .button("⏹️ Confirm STOP", "action:stop_confirm") \
            .button("❌ Cancel", "view:dashboard") \
            .build()
    
    @staticmethod
    def confirm_start() -> List[List[Dict[str, str]]]:
        """Confirmation keyboard for start action."""
        return KeyboardBuilder() \
            .row() \
            .button("▶️ Confirm START", "action:start_confirm") \
            .button("❌ Cancel", "view:dashboard") \
            .build()
    
    @staticmethod
    def with_help() -> List[List[Dict[str, str]]]:
        """Main keyboard with help button."""
        return KeyboardBuilder() \
            .row() \
            .button("📊 Dashboard", "view:dashboard") \
            .button("💰 P&L", "view:pnl") \
            .button("⚙️ Config", "view:params") \
            .row() \
            .button("📉 Signals", "view:signals") \
            .button("🏷️ Regime", "view:regime") \
            .button("📋 Trades", "view:trades") \
            .row() \
            .button("⏹️ STOP", "action:stop") \
            .button("▶️ START", "action:start") \
            .button("🔄 REFRESH", "action:refresh") \
            .row() \
            .button("❓ Help", "view:help") \
            .build()
    
    @staticmethod
    def welcome() -> List[List[Dict[str, str]]]:
        """Welcome keyboard with start button."""
        return KeyboardBuilder() \
            .row() \
            .button("🚀 Get Started", "view:dashboard") \
            .build()


def build_keyboard(callback_data: str) -> List[List[Dict[str, str]]]:
    """Build a keyboard from callback data prefix."""
    parts = callback_data.split(":")
    prefix = parts[0] if parts else ""
    
    keyboards = {
        "view": Keyboards.views_only,
        "action": Keyboards.quick_actions,
        "sub": Keyboards.subscription_categories,
        "approve": lambda: Keyboards.approval("", ""),
        "deny": lambda: Keyboards.approval("", ""),
    }
    
    builder_func = keyboards.get(prefix, Keyboards.views_only)
    return builder_func()
