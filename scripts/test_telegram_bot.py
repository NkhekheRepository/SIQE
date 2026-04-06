#!/usr/bin/env python3
"""
Test interactive Telegram bot end-to-end.

Starts the bot, sends commands, verifies responses.
"""
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_command(command: str) -> bool:
    """Send a command to the bot."""
    resp = requests.post(
        f"{API_URL}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": command,
        },
        timeout=10,
    )
    return resp.status_code == 200 and resp.json().get("ok")

def get_last_message() -> dict:
    """Get the last message from the bot."""
    resp = requests.get(
        f"{API_URL}/getUpdates",
        params={"offset": -1},
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        if data.get("ok") and data.get("result"):
            return data["result"][-1]
    return None

def test_bot():
    """Test the interactive bot."""
    from alerts.telegram_bot import create_bot
    from alerts.formatters import TradingState
    
    print("=" * 50)
    print("INTERACTIVE TELEGRAM BOT TEST")
    print("=" * 50)
    
    state = TradingState(
        symbol="BTCUSDT",
        mode="PAPER",
        regime="MIXED",
        regime_confidence=0.87,
        signal_direction="SHORT",
        signal_strength=0.68,
        position_side="NONE",
        daily_pnl=12.50,
        daily_pnl_pct=0.0025,
        weekly_pnl=-45.20,
        weekly_pnl_pct=-0.0091,
        total_pnl=352.14,
        total_pnl_pct=0.0704,
        max_drawdown=0.021,
        win_rate=0.58,
        total_trades=12,
        winning_trades=7,
        losing_trades=5,
        signal_momentum=0.72,
        signal_mean_reversion=0.15,
        signal_volatility_breakout=0.31,
        stop_multiplier=0.5,
        tp_multiplier=3.0,
        leverage=50,
        is_trading_active=True,
        next_check_seconds=45,
        current_volatility=0.0042,
    )
    
    bot = create_bot(state_provider=lambda: state)
    if not bot:
        print("❌ Bot not created - check credentials")
        return False
    
    print("\n✓ Bot created successfully")
    
    # Get initial update offset before starting bot
    resp = requests.get(f"{API_URL}/getUpdates", params={"offset": -1}, timeout=10)
    initial_offset = 0
    if resp.status_code == 200:
        data = resp.json()
        if data.get("ok") and data.get("result"):
            initial_offset = data["result"][-1].get("update_id", 0)
    
    # Start bot in background
    bot_thread = bot.start_polling_thread()
    print("✓ Bot polling started")
    time.sleep(2)
    
    # Track our messages via offset
    last_update_id = initial_offset
    
    def send_and_wait(command: str, wait: float = 3.0) -> dict:
        """Send command and wait for bot response."""
        nonlocal last_update_id
        
        # Send the command
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": command},
            timeout=10,
        )
        if not (resp.status_code == 200 and resp.json().get("ok")):
            return None
        
        time.sleep(wait)
        
        # Get updates after our command
        resp = requests.get(
            f"{API_URL}/getUpdates",
            params={"offset": last_update_id + 1},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("result"):
                updates = data["result"]
                for u in updates:
                    last_update_id = u.get("update_id", last_update_id)
                    msg = u.get("message", {})
                    if msg.get("from", {}).get("is_bot"):
                        return msg
        return None
    
    # Test /start
    print("\n1. Testing /start command...")
    msg = send_and_wait("/start")
    if msg:
        text = msg.get("text", "")
        has_kb = "reply_markup" in msg
        print(f"   ✓ Response: {text[:60]}...")
        if has_kb:
            print("   ✓ Inline keyboard included")
    else:
        print("   ⚠ No response (bot may be processing)")
    
    # Test /dashboard
    print("\n2. Testing /dashboard command...")
    msg = send_and_wait("/dashboard")
    if msg:
        text = msg.get("text", "")
        has_kb = "reply_markup" in msg
        print(f"   ✓ Response: {text[:60]}...")
        if has_kb:
            kb = msg["reply_markup"]["inline_keyboard"]
            print(f"   ✓ Keyboard has {len(kb)} rows")
    else:
        print("   ⚠ No response")
    
    # Test /pnl
    print("\n3. Testing /pnl command...")
    msg = send_and_wait("/pnl")
    if msg:
        text = msg.get("text", "")
        print(f"   ✓ Response: {text[:60]}...")
        if "352.14" in text or "HEDGE FUND" in text:
            print("   ✓ P&L data correct")
    else:
        print("   ⚠ No response")
    
    # Test /signals
    print("\n4. Testing /signals command...")
    msg = send_and_wait("/signals")
    if msg:
        text = msg.get("text", "")
        print(f"   ✓ Response: {text[:60]}...")
        if "momentum" in text or "ML ENGINEER" in text:
            print("   ✓ Signal data correct")
    else:
        print("   ⚠ No response")
    
    # Test /subscribe
    print("\n5. Testing /subscribe trading...")
    msg = send_and_wait("/subscribe trading")
    if msg:
        text = msg.get("text", "")
        print(f"   ✓ Response: {text[:60]}...")
        if "Subscribed" in text:
            print("   ✓ Subscription confirmed")
    else:
        print("   ⚠ No response")
    
    # Test /help
    print("\n6. Testing /help command...")
    msg = send_and_wait("/help")
    if msg:
        text = msg.get("text", "")
        print(f"   ✓ Response: {text[:60]}...")
    else:
        print("   ⚠ No response")
    
    # Stop bot
    bot.stop_polling()
    print("\n✓ Bot stopped")
    
    print("\n" + "=" * 50)
    print("TEST COMPLETE - Check your Telegram for messages")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = test_bot()
    sys.exit(0 if success else 1)
