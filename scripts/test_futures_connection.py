"""
SIQE V3 - Futures TESTNET Connection Test

Validates authentication and connectivity to Binance USDT-M Futures TESTNET
using BinanceLinearGateway.

Usage:
    python scripts/test_futures_connection.py              # Uses .env defaults
    python scripts/test_futures_connection.py --dry-run    # Validate config only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy_binance import BinanceLinearGateway


def get_config() -> dict:
    """Build configuration from .env."""
    api_key = os.environ.get("FUTURES_API_KEY", "") or os.environ.get("EXCHANGE_API_KEY", "")
    api_secret = os.environ.get("FUTURES_API_SECRET", "") or os.environ.get("EXCHANGE_API_SECRET", "")
    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "server": os.environ.get("EXCHANGE_SERVER", "TESTNET"),
        "proxy_host": os.environ.get("PROXY_HOST", ""),
        "proxy_port": int(os.environ.get("PROXY_PORT", "0")),
    }


def validate_config(config: dict) -> list[str]:
    """Validate futures configuration."""
    errors = []
    if not config["api_key"]:
        errors.append("FUTURES_API_KEY (or EXCHANGE_API_KEY) is not set")
    if not config["api_secret"]:
        errors.append("FUTURES_API_SECRET (or EXCHANGE_API_SECRET) is not set")
    if config["server"] not in ("TESTNET", "SIMULATOR"):
        errors.append(f"EXCHANGE_SERVER should be 'TESTNET' or 'SIMULATOR', got '{config['server']}'")
    return errors


def test_connection(config: dict, timeout: int = 15) -> dict:
    """
    Attempt connection to Binance USDT-M Futures TESTNET.

    Returns dict with status, latency, and any error messages.
    """
    result = {
        "status": "FAIL",
        "server": config["server"],
        "latency_ms": None,
        "error": None,
        "account_info": None,
    }

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceLinearGateway, "BINANCE_LINEAR")
    print("[1/3] BinanceLinearGateway added successfully")

    # Build connection settings - always include proxy fields
    gateway_setting = {
        "API Key": config["api_key"],
        "API Secret": config["api_secret"],
        "Server": config["server"],
        "Kline Stream": True,
        "Proxy Host": config["proxy_host"] or "",
        "Proxy Port": config["proxy_port"] or 0,
    }

    print(f"[2/3] Connecting to {config['server']}...")

    connect_error = [None]
    connected = threading.Event()

    def _connect():
        try:
            start = time.time()
            main_engine.connect(gateway_setting, "BINANCE_LINEAR")
            # Wait for connection to establish
            time.sleep(timeout)
            result["latency_ms"] = round((time.time() - start) * 1000, 0)
            connected.set()
        except Exception as e:
            connect_error[0] = str(e)
            connected.set()

    t = threading.Thread(target=_connect, daemon=True)
    t.start()
    t.join(timeout=timeout + 10)

    if not connected.is_set():
        result["error"] = f"Connection timed out after {timeout + 10}s"
        print(f"[ERROR] {result['error']}")
        main_engine.close()
        event_engine.stop()
        return result

    if connect_error[0]:
        result["error"] = connect_error[0]
        print(f"[ERROR] {result['error']}")
        main_engine.close()
        event_engine.stop()
        return result

    print(f"[3/3] Connection attempt complete ({result['latency_ms']}ms)")

    # Check account data
    accounts = main_engine.get_all_accounts()
    if accounts:
        account = accounts[0]
        result["account_info"] = {
            "account_id": account.accountid,
            "balance": account.balance,
            "frozen": account.frozen,
        }
        print(f"  Account info: balance={account.balance:.2f}, frozen={account.frozen:.2f}")
        result["status"] = "SUCCESS"
    else:
        result["error"] = "No account data received - authentication may have failed"
        print(f"  WARNING: No account data received")
        result["status"] = "WARNING"

    main_engine.close()
    event_engine.stop()

    return result


def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Futures TESTNET Connection Test")
    parser.add_argument("--timeout", type=int, default=15, help="Connection timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Validate config only")
    args = parser.parse_args()

    config = get_config()

    print("SIQE V3 - Futures TESTNET Connection Test")
    print("=" * 60)
    print(f"  Server:       {config['server']}")
    print(f"  API Key:      {config['api_key'][:10]}...{config['api_key'][-4:] if config['api_key'] else 'NOT SET'}")
    print(f"  Proxy:        {config['proxy_host'] or 'None'}")
    print()

    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  [ERROR] {e}")
        print()
        if config["server"] == "TESTNET":
            print("To get TESTNET API keys:")
            print("  1. Go to https://testnet.binancefuture.com")
            print("  2. Log in with your Binance testnet account")
            print("  3. Generate API keys from the API Management page")
            print("  4. Add FUTURES_API_KEY and FUTURES_API_SECRET to .env")
        return 1

    if args.dry_run:
        print("[DRY RUN] Configuration is valid. No connection made.")
        print("Remove --dry-run to test the actual connection.")
        return 0

    # Test connection
    print("Testing connection...")
    result = test_connection(config, timeout=args.timeout)

    print()
    print("=" * 60)
    print("CONNECTION TEST RESULTS")
    print("=" * 60)
    print(f"  Status:   {result['status']}")
    print(f"  Server:   {result['server']}")
    if result["latency_ms"]:
        print(f"  Latency:  {result['latency_ms']}ms")
    else:
        print("  Latency:  N/A")

    if result["account_info"]:
        print(f"  Balance:  {result['account_info']['balance']:.2f} USDT")
        print(f"  Frozen:   {result['account_info']['frozen']:.2f} USDT")

    if result["error"]:
        print(f"  Error:    {result['error']}")

    print()
    if result["status"] == "SUCCESS":
        print("[OK] Connection successful! Ready for futures trading.")
        return 0
    elif result["status"] == "WARNING":
        print("[WARN] Connected but no account data. Check API key permissions.")
        return 0
    else:
        print("[FAIL] Connection failed.")
        err = (result.get("error") or "").lower()
        if "signature" in err or "api" in err or "key" in err:
            print("  Authentication failed. Generate new TESTNET keys from:")
            print("  https://testnet.binancefuture.com")
        return 1


if __name__ == "__main__":
    sys.exit(main())
