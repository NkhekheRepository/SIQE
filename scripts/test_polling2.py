#!/usr/bin/env python3
"""
Test: Bot should receive updates when user sends message.
This test runs the bot, then we send a message from the user.
"""
import sys, os, time, threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("Step 1: Clear any stale updates")
resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset=999999999", timeout=5)
print(f"Clear: {resp.json()}")

print("\nStep 2: Start bot polling in thread")
from alerts.telegram_bot import TelegramBot
from alerts.formatters import TradingState

state = TradingState(symbol='BTCUSDT')
bot = TelegramBot(BOT_TOKEN, CHAT_ID, state_provider=lambda: state)

def run():
    print("[Polling thread] Starting...")
    bot.start_polling()
    print("[Polling thread] Stopped")

t = threading.Thread(target=run)
t.start()

time.sleep(3)

print("\nStep 3: User sends /start now!")
print("Waiting 10 seconds for user message...")

for i in range(10):
    time.sleep(1)
    print(f"  Waited {i+1}s...")

print("\nStep 4: Stop bot")
bot.stop_polling()
t.join(timeout=2)

print("\nDone - check if bot sent response")
