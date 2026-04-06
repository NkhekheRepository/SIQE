#!/usr/bin/env python3
"""
SIQE V3 - Persistent Telegram Bot Runner

Runs the Telegram bot indefinitely with proper shutdown handling.
"""
import sys
import os
import time
import signal
import threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

from alerts.telegram_bot import create_bot
from alerts.formatters import TradingState, DashboardFormatter


class PersistentBot:
    """Bot runner with persistent operation and graceful shutdown."""
    
    def __init__(self):
        self.bot = None
        self.running = False
        self.poll_thread = None
        
    def start(self):
        """Start the bot."""
        state = TradingState(symbol='BTCUSDT', mode='PAPER')
        self.bot = create_bot(state_provider=lambda: state)
        
        if not self.bot:
            logger.error("Bot not created - check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            return False
        
        logger.info(f"Bot created. Chat ID: {self.bot.chat_id}")
        
        self.running = True
        self.poll_thread = threading.Thread(target=self.bot.start_polling, daemon=True)
        self.poll_thread.start()
        logger.info("Bot polling started")
        
        return True
    
    def stop(self):
        """Stop the bot gracefully."""
        logger.info("Stopping bot...")
        self.running = False
        if self.bot:
            self.bot.stop_polling()
        logger.info("Bot stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}")
    if runner:
        runner.stop()
    sys.exit(0)


if __name__ == "__main__":
    runner = PersistentBot()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if runner.start():
        logger.info("Bot is running. Press Ctrl+C to stop.")
        try:
            while runner.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        runner.stop()
    else:
        sys.exit(1)
