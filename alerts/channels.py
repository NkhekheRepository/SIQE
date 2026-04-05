"""
SIQE V3 - Alert Channels

Implements notification channels for alerts (Telegram, etc.).
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BaseChannel(ABC):
    """Abstract base class for alert channels."""
    
    @abstractmethod
    def send(self, message: str, **kwargs) -> bool:
        """Send a message through this channel."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the channel is properly configured."""
        pass


class TelegramChannel(BaseChannel):
    """Telegram notification channel with retry and circuit breaker."""
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage" if bot_token else None
        
        # Retry configuration
        self.max_retries = 3
        self.backoff_factor = 1.0  # 1s, 2s, 4s
        self.circuit_breaker_threshold = 5
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_time = 0
        self.circuit_reset_timeout = 300  # 5 minutes
        
        # Create session with retry adapter
        self._session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
    
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.bot_token and self.chat_id and self.api_url)
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is open."""
        if self._circuit_open:
            if time.time() - self._circuit_open_time > self.circuit_reset_timeout:
                logger.info("Telegram circuit breaker reset after timeout")
                self._circuit_open = False
                self._consecutive_failures = 0
                return False
            return True
        return False
    
    def _record_failure(self):
        """Record a failure and possibly open circuit breaker."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_open_time = time.time()
            logger.warning(f"Telegram circuit breaker OPEN after {self._consecutive_failures} consecutive failures")
    
    def _record_success(self):
        """Record a success and reset failure counter."""
        self._consecutive_failures = 0
    
    def send(self, message: str, **kwargs) -> bool:
        """
        Send message via Telegram Bot API with retry and circuit breaker.
        
        Args:
            message: The message text to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Telegram channel not configured, skipping alert")
            return False
        
        if self._check_circuit_breaker():
            logger.warning("Telegram circuit breaker is open, skipping alert")
            return False
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = self._session.post(
                    self.api_url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=10,
                )
                
                if response.status_code == 200:
                    logger.debug(f"Telegram alert sent: {message[:50]}...")
                    self._record_success()
                    return True
                else:
                    logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                    last_exception = f"API error: {response.status_code}"
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Telegram request timeout (attempt {attempt + 1}/{self.max_retries})")
                last_exception = "Timeout"
            except requests.exceptions.RequestException as e:
                logger.warning(f"Telegram request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                last_exception = str(e)
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                last_exception = str(e)
            
            # Exponential backoff between retries
            if attempt < self.max_retries - 1:
                sleep_time = self.backoff_factor * (2 ** attempt)
                logger.debug(f"Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
        
        # All retries failed
        self._record_failure()
        logger.error(f"Telegram alert failed after {self.max_retries} attempts: {last_exception}")
        return False
    
    def send_alert(self, alert) -> bool:
        """Send an Alert object via Telegram."""
        if hasattr(alert, 'to_telegram'):
            message = alert.to_telegram()
        else:
            message = str(alert)
        return self.send(message)


class MultiChannel(BaseChannel):
    """Multi-channel aggregator that sends to multiple channels."""
    
    def __init__(self, channels: list[BaseChannel] = None):
        self.channels = channels or []
    
    def add_channel(self, channel: BaseChannel) -> None:
        """Add a channel to the list."""
        self.channels.append(channel)
    
    def is_configured(self) -> bool:
        """At least one channel must be configured."""
        return any(c.is_configured() for c in self.channels)
    
    def send(self, message: str, **kwargs) -> bool:
        """Send to all configured channels."""
        results = []
        for channel in self.channels:
            if channel.is_configured():
                result = channel.send(message, **kwargs)
                results.append(result)
        
        return any(results) if results else False


def create_telegram_channel(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> TelegramChannel:
    """Create a Telegram channel from environment or direct config."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    return TelegramChannel(
        bot_token=bot_token or os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=chat_id or os.getenv("TELEGRAM_CHAT_ID"),
    )
