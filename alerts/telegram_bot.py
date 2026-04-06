"""
SIQE V3 - Interactive Telegram Bot

Long-polling bot with command handling, inline keyboards, and callback processing.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import requests

from alerts.formatters import DashboardFormatter, TradingState
from alerts.keyboards import Keyboards
from alerts.subscriptions import SubscriptionManager, get_subscription_manager

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Interactive Telegram bot with long-polling.
    
    Features:
    - Command handling (/start, /help, /status, etc.)
    - Inline keyboard callbacks
    - Approval workflow
    - Subscription management
    - State-aware responses
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        state_provider: Optional[Callable[[], TradingState]] = None,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.state_provider = state_provider or self._default_state_provider
        self.subscription_manager = get_subscription_manager()
        
        self._api_url = f"https://api.telegram.org/bot{bot_token}"
        self._last_update_id = 0
        self._running = False
        self._poll_interval = 1.0
        self._session = requests.Session()
        
        # State tracking
        self._is_trading_active = True
        self._pending_confirmations: Dict[str, bool] = {}
        self._approval_callbacks: Dict[str, Callable[[bool], None]] = {}
        
        # Command handlers
        self._command_handlers: Dict[str, Callable] = {
            "/start": self._handle_start,
            "/help": self._handle_help,
            "/dashboard": self._handle_dashboard,
            "/status": self._handle_status,
            "/pnl": self._handle_pnl,
            "/signals": self._handle_signals,
            "/positions": self._handle_positions,
            "/trades": self._handle_trades,
            "/regime": self._handle_regime,
            "/params": self._handle_params,
            "/subscribe": self._handle_subscribe,
            "/unsubscribe": self._handle_unsubscribe,
            "/subscriptions": self._handle_subscriptions,
            "/stop": self._handle_stop,
            "/starttrading": self._handle_start_trading,
            "/refresh": self._handle_refresh,
        }
        
        # Callback handlers
        self._callback_handlers: Dict[str, Callable] = {
            "view:": self._handle_view_callback,
            "action:": self._handle_action_callback,
            "sub:": self._handle_subscription_callback,
            "approve:": self._handle_approve_callback,
            "deny:": self._handle_deny_callback,
        }
    
    @staticmethod
    def _default_state_provider() -> TradingState:
        """Default state provider when none is set."""
        return TradingState()
    
    def _make_request(self, method: str, data: Dict[str, Any] = None) -> Optional[Dict]:
        """Make a request to the Telegram Bot API."""
        try:
            response = self._session.post(
                f"{self._api_url}/{method}",
                json=data,
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Telegram API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Telegram API request failed: {e}")
        return None
    
    def send_message(self, text: str, reply_markup: Optional[List] = None) -> bool:
        """Send a message to the configured chat."""
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        
        if reply_markup:
            data["reply_markup"] = {"inline_keyboard": reply_markup}
        
        result = self._make_request("sendMessage", data)
        return result is not None and result.get("ok", False)
    
    def edit_message(self, message_id: int, text: str, reply_markup: Optional[List] = None) -> bool:
        """Edit an existing message."""
        data = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        
        if reply_markup:
            data["reply_markup"] = {"inline_keyboard": reply_markup}
        
        result = self._make_request("editMessageText", data)
        return result is not None and result.get("ok", False)
    
    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        """Answer a callback query."""
        data = {
            "callback_query_id": callback_query_id,
            "text": text,
        }
        result = self._make_request("answerCallbackQuery", data)
        return result is not None and result.get("ok", False)
    
    def _get_updates(self) -> List[Dict]:
        """Get updates from Telegram."""
        data = {
            "offset": self._last_update_id + 1,
            "timeout": 30,
        }
        result = self._make_request("getUpdates", data)
        if result and result.get("ok"):
            return result.get("result", [])
        return []
    
    def _process_update(self, update: Dict) -> None:
        """Process a single update."""
        update_id = update.get("update_id")
        if update_id is not None:
            self._last_update_id = update_id
        
        # Check if it's a callback query
        if "callback_query" in update:
            self._process_callback_query(update["callback_query"])
            return
        
        # Check if it's a message
        if "message" in update:
            message = update["message"]
            
            # Only process messages from the configured chat
            if str(message.get("chat", {}).get("id")) != self.chat_id:
                return
            
            # Check if it has text
            text = message.get("text", "")
            if not text:
                return
            
            # Process commands
            if text.startswith("/"):
                self._process_command(text, message)
    
    def _process_callback_query(self, callback_query: Dict) -> None:
        """Process a callback query from inline keyboard."""
        callback_data = callback_query.get("data", "")
        callback_query_id = callback_query.get("id", "")
        
        logger.debug(f"Callback query: {callback_data}")
        
        # Find matching handler
        for prefix, handler in self._callback_handlers.items():
            if callback_data.startswith(prefix):
                handler(callback_data, callback_query_id)
                return
        
        # No handler found
        self.answer_callback(callback_query_id, "Unknown action")
    
    def _process_command(self, text: str, message: Dict) -> None:
        """Process a command."""
        parts = text.split()
        command = parts[0].lower()
        
        handler = self._command_handlers.get(command)
        if handler:
            handler(message, parts[1:])
        else:
            self.send_message(DashboardFormatter.format_unknown_command())
    
    # Command Handlers
    
    def _handle_start(self, message: Dict, args: List[str]) -> None:
        """Handle /start command."""
        self.send_message(
            DashboardFormatter.format_welcome(),
            reply_markup=Keyboards.welcome(),
        )
    
    def _handle_help(self, message: Dict, args: List[str]) -> None:
        """Handle /help command."""
        self.send_message(
            DashboardFormatter.format_help(),
            reply_markup=Keyboards.views_only(),
        )
    
    def _handle_dashboard(self, message: Dict, args: List[str]) -> None:
        """Handle /dashboard command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_dashboard(state),
            reply_markup=Keyboards.main_dashboard(),
        )
    
    def _handle_status(self, message: Dict, args: List[str]) -> None:
        """Handle /status command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_quant_view(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_pnl(self, message: Dict, args: List[str]) -> None:
        """Handle /pnl command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_hedge_fund_view(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_signals(self, message: Dict, args: List[str]) -> None:
        """Handle /signals command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_ml_engineer_view(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_positions(self, message: Dict, args: List[str]) -> None:
        """Handle /positions command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_positions(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_trades(self, message: Dict, args: List[str]) -> None:
        """Handle /trades command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_trades(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_regime(self, message: Dict, args: List[str]) -> None:
        """Handle /regime command."""
        state = self.state_provider()
        regime_emoji = "🟢" if state.regime == "BULL" else "🔴" if state.regime == "BEAR" else "🟡"
        
        text = f"""🏷️ <b>Market Regime</b>
{"═" * 40}
<b>Current:</b> {regime_emoji} {state.regime}
<b>Confidence:</b> {state.regime_confidence:.0%}
<b>Volatility:</b> {state.current_volatility:.2%}"""
        
        self.send_message(
            text,
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_params(self, message: Dict, args: List[str]) -> None:
        """Handle /params command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_params(state),
            reply_markup=Keyboards.back_to_dashboard(),
        )
    
    def _handle_subscribe(self, message: Dict, args: List[str]) -> None:
        """Handle /subscribe command."""
        if not args:
            self.send_message("Usage: /subscribe <type_or_category>\n\nUse /subscriptions to see available types.")
            return
        
        alert_type = args[0]
        chat_id = str(message.get("chat", {}).get("id", self.chat_id))
        
        success = self.subscription_manager.subscribe(chat_id, alert_type)
        
        if success:
            self.send_message(DashboardFormatter.format_subscribe_success(alert_type))
        else:
            self.send_message(DashboardFormatter.format_error(f"Unknown alert type: {alert_type}"))
    
    def _handle_unsubscribe(self, message: Dict, args: List[str]) -> None:
        """Handle /unsubscribe command."""
        if not args:
            self.send_message("Usage: /unsubscribe <type_or_category>")
            return
        
        alert_type = args[0]
        chat_id = str(message.get("chat", {}).get("id", self.chat_id))
        
        success = self.subscription_manager.unsubscribe(chat_id, alert_type)
        
        if success:
            self.send_message(DashboardFormatter.format_unsubscribe_success(alert_type))
        else:
            self.send_message(DashboardFormatter.format_error(f"Unknown alert type: {alert_type}"))
    
    def _handle_subscriptions(self, message: Dict, args: List[str]) -> None:
        """Handle /subscriptions command."""
        chat_id = str(message.get("chat", {}).get("id", self.chat_id))
        
        subscribed = self.subscription_manager.get_subscriptions(chat_id)
        categories = self.subscription_manager.get_categories()
        
        text = f"""🔔 <b>Your Subscriptions</b>
{"═" * 40}
<b>Active:</b> {", ".join(subscribed) if subscribed else "None"}

<b>Categories:</b>
{", ".join(categories)}

Use /subscribe <type> to add alerts.
"""
        
        self.send_message(
            text,
            reply_markup=Keyboards.subscription_categories(),
        )
    
    def _handle_stop(self, message: Dict, args: List[str]) -> None:
        """Handle /stop command."""
        self.send_message(
            "⏹️ <b>Confirm Stop</b>\n\nAre you sure you want to stop trading?",
            reply_markup=Keyboards.confirm_stop(),
        )
    
    def _handle_start_trading(self, message: Dict, args: List[str]) -> None:
        """Handle /starttrading command."""
        self.send_message(
            "▶️ <b>Confirm Start</b>\n\nAre you sure you want to resume trading?",
            reply_markup=Keyboards.confirm_start(),
        )
    
    def _handle_refresh(self, message: Dict, args: List[str]) -> None:
        """Handle /refresh command."""
        state = self.state_provider()
        self.send_message(
            DashboardFormatter.format_dashboard(state),
            reply_markup=Keyboards.main_dashboard(),
        )
    
    # Callback Handlers
    
    def _handle_view_callback(self, callback_data: str, callback_query_id: str) -> None:
        """Handle view callbacks."""
        self.answer_callback(callback_query_id)
        
        view = callback_data.split(":")[1] if ":" in callback_data else ""
        
        view_handlers = {
            "dashboard": self._handle_dashboard,
            "pnl": self._handle_pnl,
            "signals": self._handle_signals,
            "status": self._handle_status,
            "params": self._handle_params,
            "regime": self._handle_regime,
            "trades": self._handle_trades,
            "help": self._handle_help,
        }
        
        handler = view_handlers.get(view)
        if handler:
            handler({"chat": {"id": self.chat_id}}, [])
    
    def _handle_action_callback(self, callback_data: str, callback_query_id: str) -> None:
        """Handle action callbacks."""
        action = callback_data.split(":")[1] if ":" in callback_data else ""
        
        if action == "stop":
            self.answer_callback(callback_query_id, "Confirm stop")
            self.send_message(
                "⏹️ <b>Confirm Stop</b>\n\nAre you sure?",
                reply_markup=Keyboards.confirm_stop(),
            )
        elif action == "start":
            self.answer_callback(callback_query_id, "Confirm start")
            self.send_message(
                "▶️ <b>Confirm Start</b>\n\nAre you sure?",
                reply_markup=Keyboards.confirm_start(),
            )
        elif action == "stop_confirm":
            self._is_trading_active = False
            self.answer_callback(callback_query_id, "Trading stopped")
            self.send_message(DashboardFormatter.format_stop_confirmed())
        elif action == "start_confirm":
            self._is_trading_active = True
            self.answer_callback(callback_query_id, "Trading started")
            self.send_message(DashboardFormatter.format_start_confirmed())
        elif action == "refresh":
            self.answer_callback(callback_query_id, "Refreshing")
            state = self.state_provider()
            self.send_message(
                DashboardFormatter.format_dashboard(state),
                reply_markup=Keyboards.main_dashboard(),
            )
    
    def _handle_subscription_callback(self, callback_data: str, callback_query_id: str) -> None:
        """Handle subscription callbacks."""
        category = callback_data.split(":")[1] if ":" in callback_data else ""
        
        chat_id = self.chat_id
        success = self.subscription_manager.subscribe(chat_id, category)
        
        if success:
            self.answer_callback(callback_query_id, f"Subscribed to {category}")
            subscribed = self.subscription_manager.get_subscriptions(chat_id)
            available = self.subscription_manager.get_available_types()
            self.send_message(
                DashboardFormatter.format_subscriptions(subscribed, available),
                reply_markup=Keyboards.back_to_dashboard(),
            )
    
    def _handle_approve_callback(self, callback_data: str, callback_query_id: str) -> None:
        """Handle approve callbacks."""
        action_key = callback_data.split(":")[1] if ":" in callback_data else ""
        
        self.answer_callback(callback_query_id, "Approved")
        
        if action_key in self._approval_callbacks:
            self._approval_callbacks[action_key](True)
            del self._approval_callbacks[action_key]
        
        self.send_message(DashboardFormatter.format_approval_confirmed(action_key))
    
    def _handle_deny_callback(self, callback_data: str, callback_query_id: str) -> None:
        """Handle deny callbacks."""
        action_key = callback_data.split(":")[1] if ":" in callback_data else ""
        
        self.answer_callback(callback_query_id, "Denied")
        
        if action_key in self._approval_callbacks:
            self._approval_callbacks[action_key](False)
            del self._approval_callbacks[action_key]
        
        self.send_message(DashboardFormatter.format_approval_denied(action_key))
    
    # Public API
    
    def request_approval(
        self,
        action: str,
        details: str,
        callback: Callable[[bool], None],
        timeout: int = 300,
    ) -> str:
        """
        Request user approval for an action.
        
        Args:
            action: Action name
            details: Action details
            callback: Function to call with True/False result
            timeout: Timeout in seconds
            
        Returns:
            Action key for tracking
        """
        import uuid
        action_key = str(uuid.uuid4())[:8]
        
        self._approval_callbacks[action_key] = callback
        
        self.send_message(
            DashboardFormatter.format_approval_request(action, details, timeout),
            reply_markup=Keyboards.approval(action, action_key),
        )
        
        # Set timeout
        def timeout_check():
            time.sleep(timeout)
            if action_key in self._approval_callbacks:
                self._approval_callbacks[action_key](False)
                del self._approval_callbacks[action_key]
                logger.info(f"Approval {action_key} timed out")
        
        threading.Thread(target=timeout_check, daemon=True).start()
        
        return action_key
    
    @property
    def is_trading_active(self) -> bool:
        """Check if trading is active."""
        return self._is_trading_active
    
    @is_trading_active.setter
    def is_trading_active(self, value: bool) -> None:
        """Set trading active state."""
        self._is_trading_active = value
    
    def start_polling(self) -> None:
        """Start the bot polling loop."""
        self._running = True
        logger.info("Telegram bot polling started")
        
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(5)
            
            time.sleep(self._poll_interval)
    
    def stop_polling(self) -> None:
        """Stop the bot polling loop."""
        self._running = False
        logger.info("Telegram bot polling stopped")
    
    def start_polling_thread(self) -> threading.Thread:
        """Start polling in a background thread."""
        thread = threading.Thread(target=self.start_polling, daemon=True)
        thread.start()
        return thread


def create_bot(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    state_provider: Optional[Callable[[], TradingState]] = None,
) -> Optional[TelegramBot]:
    """Create a Telegram bot from environment or direct config."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat:
        logger.warning("Telegram bot not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return None
    
    return TelegramBot(token, chat, state_provider)
