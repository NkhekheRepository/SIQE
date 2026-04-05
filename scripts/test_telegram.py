#!/usr/bin/env python3
"""
Telegram Bot Setup Helper

This script helps verify Telegram configuration and send test messages.

SETUP INSTRUCTIONS:
==================

1. CREATE A BOT:
   - Open Telegram and chat with @BotFather
   - Send: /newbot
   - Follow prompts to name your bot
   - Copy the bot token (format: 123456789:ABCdefGHI...)

2. GET YOUR CHAT ID:
   
   Option A - Direct Message:
   - Start a conversation with your new bot
   - Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   - Look for "chat":{"id":XXXXXXXXX} in the response
   - Copy the id number as your CHAT_ID
   
   Option B - Channel:
   - Create a Telegram channel
   - Add your bot as an admin with "Post Messages" permission
   - Get channel ID (usually starts with -100)
   - Format: -100XXXXXXXXX

3. CONFIGURE .env:
   - Add these lines to your .env file:
   
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ALERT_ENABLED=true

USAGE:
======
python scripts/test_telegram.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests


def test_telegram_config():
    """Test Telegram configuration and send verification message."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    print("=" * 50)
    print("TELEGRAM CONFIGURATION TEST")
    print("=" * 50)
    
    # Check credentials
    print("\n1. CREDENTIALS CHECK")
    print("-" * 30)
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return False
    else:
        print(f"✓ Bot token found: {bot_token[:10]}...{bot_token[-5:]}")
    
    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID not set")
        return False
    else:
        print(f"✓ Chat ID found: {chat_id}")
    
    # Test bot info
    print("\n2. BOT VERIFICATION")
    print("-" * 30)
    
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
                print(f"✓ Bot name: {bot_info.get('first_name', 'N/A')}")
                print(f"✓ Bot username: @{bot_info.get('username', 'N/A')}")
            else:
                print(f"❌ Bot verification failed: {data}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False
    
    # Get updates to find chat_id
    print("\n3. CHAT ID DISCOVERY")
    print("-" * 30)
    print("Send a message to your bot in Telegram, then run this again.")
    print("Or check: https://api.telegram.org/bot{TOKEN}/getUpdates")
    
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("result"):
                updates = data.get("result", [])
                if updates:
                    latest = updates[-1]
                    if "message" in latest:
                        chat = latest["message"].get("chat", {})
                        found_id = chat.get("id")
                        print(f"\n✓ Found chat ID in updates: {found_id}")
                        print(f"  Update this in your .env if different from current")
            else:
                print("  No recent updates found (send a message to your bot first)")
    except Exception as e:
        print(f"  Could not fetch updates: {e}")
    
    # Test message sending
    print("\n4. SEND TEST MESSAGE")
    print("-" * 30)
    
    try:
        test_message = """✅ *SIQE V3 Alert System*

Alert system configured successfully!
You will receive trading alerts here.

_Setup completed at: {time}_""".format(time=os.popen('date').read().strip())
        
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": test_message,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                print("✓ Test message sent successfully!")
                print(f"  Check your Telegram for the message")
                return True
            else:
                print(f"❌ Send failed: {data.get('description', 'Unknown error')}")
                print(f"\n  Common issues:")
                print(f"  - Bot not added to channel/group")
                print(f"  - Chat ID format incorrect (try with -100 prefix for channels)")
                print(f"  - Bot doesn't have permission to post")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Send failed: {e}")
        return False


def create_channel_setup_instructions():
    """Print detailed setup instructions."""
    print("\n" + "=" * 50)
    print("DETAILED SETUP INSTRUCTIONS")
    print("=" * 50)
    print("""
STEP 1: Create a Telegram Bot
------------------------------
1. Open Telegram app
2. Search for @BotFather
3. Send /newbot
4. Give your bot a name (e.g., "SIQE Alerts")
5. Give your bot a username (e.g., "siqe_alerts_bot")
6. BotFather will give you a token like:
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz

STEP 2: Get Your Chat ID
-------------------------
Option A: Direct Chat with Bot
1. Open your new bot in Telegram
2. Send any message (e.g., "hello")
3. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
4. Look for "chat":{"id":123456789} in the JSON
5. The number is your CHAT_ID

Option B: Private Channel
1. Create a new channel in Telegram
2. Add your bot as an admin
3. Get the channel ID (usually shown in channel settings)
4. Format is typically: -100XXXXXXXXX

STEP 3: Update .env
-------------------
Add these to your .env file:

TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
ALERT_ENABLED=true

STEP 4: Test
------------
Run: python scripts/test_telegram.py
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        create_channel_setup_instructions()
    else:
        success = test_telegram_config()
        if not success:
            print("\n" + "=" * 50)
            print("Need help? Run: python scripts/test_telegram.py --help")
            print("=" * 50)
        sys.exit(0 if success else 1)
