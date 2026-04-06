#!/usr/bin/env python3
"""Persistent bot runner with real-time data from existing infrastructure"""
import sys
import os
import time
import threading
import signal

sys.path.insert(0, '.')
os.chdir('.')

from dotenv import load_dotenv
load_dotenv('.env')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from alerts.telegram_bot import create_bot
from alerts.state_provider import get_state_provider

db_path = os.getenv('DB_PATH', './data/siqe.db')

state_provider = get_state_provider(db_path=db_path)
print(f"StateProvider initialized: {state_provider._initialized}")

def state_provider_callback():
    """Callback for telegram bot to get fresh state."""
    return state_provider.get_state()

bot = create_bot(state_provider=state_provider_callback)

if not bot:
    print("ERROR: Bot not created - check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    sys.exit(1)

print(f"Bot started. Chat ID: {bot.chat_id}")
print("Using real-time data from DuckDB")

def shutdown(sig, frame):
    print("Shutting down...")
    bot.stop_polling()
    state_provider.close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

bot.start_polling()
