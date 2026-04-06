#!/usr/bin/env python3
"""
Test interactive Telegram bot command handlers directly.

Tests the bot's internal handlers without competing with the polling loop.
"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from alerts.telegram_bot import TelegramBot
from alerts.formatters import TradingState


def make_state():
    return TradingState(
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


def test_command_handlers():
    """Test all command handlers directly."""
    import os
    
    bot = TelegramBot(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "test"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", "test"),
        state_provider=make_state,
    )
    
    # Mock send_message
    bot.send_message = Mock()
    bot.answer_callback = Mock()
    
    test_message = {"chat": {"id": bot.chat_id}}
    
    tests = [
        ("/start", "Welcome"),
        ("/help", "Command Reference"),
        ("/dashboard", "SIQE V3"),
        ("/status", "QUANT DEVELOPER"),
        ("/pnl", "HEDGE FUND"),
        ("/signals", "AI/ML ENGINEER"),
        ("/positions", None),  # could be "No Open Positions"
        ("/trades", None),
        ("/regime", "Market Regime"),
        ("/params", "Strategy Parameters"),
        ("/subscribe trading", "Subscribed"),
        ("/unsubscribe trading", "Unsubscribed"),
        ("/subscriptions", "Your Subscriptions"),
        ("/stop", "Confirm Stop"),
        ("/starttrading", "Confirm Start"),
        ("/refresh", "SIQE V3"),
    ]
    
    passed = 0
    failed = 0
    
    for command, expected_text in tests:
        bot.send_message.reset_mock()
        parts = command.split()
        cmd = parts[0]
        args = parts[1:]
        
        handler = bot._command_handlers.get(cmd)
        if handler:
            try:
                handler(test_message, args)
                
                if bot.send_message.called:
                    sent_text = bot.send_message.call_args[0][0]
                    if expected_text is None or expected_text in sent_text:
                        print(f"  ✓ {command}")
                        passed += 1
                    else:
                        print(f"  ✗ {command} - expected '{expected_text}' in response")
                        print(f"    Got: {sent_text[:80]}...")
                        failed += 1
                else:
                    print(f"  ✗ {command} - no message sent")
                    failed += 1
            except Exception as e:
                print(f"  ✗ {command} - error: {e}")
                failed += 1
        else:
            print(f"  ✗ {command} - no handler found")
            failed += 1
    
    return passed, failed


def test_callback_handlers():
    """Test callback query handlers."""
    import os
    
    bot = TelegramBot(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "test"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", "test"),
        state_provider=make_state,
    )
    
    bot.send_message = Mock()
    bot.answer_callback = Mock()
    
    tests = [
        ("view:dashboard", True),
        ("view:pnl", True),
        ("view:signals", True),
        ("action:stop", True),
        ("action:start", True),
        ("action:stop_confirm", True),
        ("action:start_confirm", True),
        ("action:refresh", True),
        ("sub:trading", True),
        ("sub:risk", True),
    ]
    
    passed = 0
    failed = 0
    
    for callback_data, should_respond in tests:
        bot.send_message.reset_mock()
        bot.answer_callback.reset_mock()
        
        try:
            bot._process_callback_query({
                "id": f"cb_{callback_data}",
                "data": callback_data,
            })
            
            if should_respond and bot.send_message.called:
                print(f"  ✓ callback: {callback_data}")
                passed += 1
            elif should_respond:
                print(f"  ✗ callback: {callback_data} - no response")
                failed += 1
            else:
                print(f"  ✓ callback: {callback_data} (expected no response)")
                passed += 1
        except Exception as e:
            print(f"  ✗ callback: {callback_data} - error: {e}")
            failed += 1
    
    return passed, failed


if __name__ == "__main__":
    print("=" * 50)
    print("TELEGRAM BOT HANDLER TESTS")
    print("=" * 50)
    
    print("\n1. Command Handlers:")
    cmd_passed, cmd_failed = test_command_handlers()
    
    print("\n2. Callback Handlers:")
    cb_passed, cb_failed = test_callback_handlers()
    
    total_passed = cmd_passed + cb_passed
    total_failed = cmd_failed + cb_failed
    
    print("\n" + "=" * 50)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print("=" * 50)
    
    sys.exit(0 if total_failed == 0 else 1)
