#!/usr/bin/env python3
"""
Simple test: create bot and verify it can receive updates.
Uses simple loop without threading complications.
"""
import sys, os, time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

print(f"Bot token: {BOT_TOKEN[:8]}...")
print(f"Chat ID: {CHAT_ID}")

# Clear old updates
print("Clearing old updates...")
resp = requests.get(f"{API_URL}/getUpdates?offset=999999999", timeout=5)
print(f"Clear result: {resp.json()}")

# Start simple test
print("\n--- Starting poll test ---")

from alerts.telegram_bot import TelegramBot
from alerts.formatters import TradingState

state = TradingState(symbol='BTCUSDT', mode='PAPER')

# Create bot directly
bot = TelegramBot(BOT_TOKEN, CHAT_ID, state_provider=lambda: state)

# Override to see what's happening
orig_get = bot._get_updates
def debug_get():
    result = orig_get()
    if result:
        print(f">>> GOT UPDATES: {result}")
    return result
bot._get_updates = debug_get

# Run a few iterations manually
print("\nRunning manual polling iterations...")
for i in range(5):
    print(f"\nIteration {i+1}:")
    updates = bot._get_updates()
    if updates:
        print(f"Got {len(updates)} updates!")
        for u in updates:
            bot._process_update(u)
    else:
        print("No updates")
    time.sleep(2)

print("\n--- Test complete ---")
