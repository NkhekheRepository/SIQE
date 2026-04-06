#!/usr/bin/env python3
import sys, os, time, threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

from alerts.telegram_bot import create_bot
from alerts.formatters import TradingState, DashboardFormatter

state = TradingState(symbol='BTCUSDT', mode='PAPER')
bot = create_bot(state_provider=lambda: state)

if not bot:
    print("ERROR: Bot not created")
    sys.exit(1)

print(f"Bot created. Chat ID: {bot.chat_id}")

# Test if polling works directly first
print("Testing getUpdates...")
updates = bot._get_updates()
print(f"Initial updates: {len(updates)}")

# Start in background thread
print("Starting thread...")
t = threading.Thread(target=bot.start_polling)
t.start()
print("Thread started, waiting 15s...")

time.sleep(15)

print("Stopping bot...")
bot.stop_polling()
print("Bot stopped")

time.sleep(2)
print("Done!")
