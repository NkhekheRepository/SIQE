"""
SIQE V3 - Paper Trading Launcher

Launches the SIQE CTA strategy in paper trading mode using VN.PY's
Binance Spot gateway with testnet/simulator server.

Usage:
    python scripts/paper_trade.py              # Uses .env defaults
    python scripts/paper_trade.py --symbol ethusdt  # Trade ETH instead
    python scripts/paper_trade.py --dry-run   # Validate config only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def validate_config(config: dict) -> list[str]:
    """Validate paper trading configuration."""
    errors = []
    if not config["api_key"]:
        errors.append("EXCHANGE_API_KEY is not set")
    if not config["api_secret"]:
        errors.append("EXCHANGE_API_SECRET is not set")
    if config["symbol"] and not config["symbol"].lower().endswith("usdt"):
        errors.append(f"Symbol '{config['symbol']}' should end with 'usdt'")
    return errors


def get_config(args) -> dict:
    """Build configuration from .env and command-line overrides."""
    symbol = args.symbol or os.environ.get("EXCHANGE_SYMBOL", "btcusdt")
    # Ensure lowercase
    symbol = symbol.lower()

    return {
        "api_key": os.environ.get("EXCHANGE_API_KEY", ""),
        "api_secret": os.environ.get("EXCHANGE_API_SECRET", ""),
        "server": os.environ.get("EXCHANGE_SERVER", "SIMULATOR"),
        "symbol": symbol,
        "strategy_name": args.name or "siqe_paper",
        "strategy_params": {
            "fixed_volume": float(args.volume or 0.01),
            "mr_boll_period": int(os.environ.get("MR_BOLL_PERIOD", 20)),
            "mr_boll_dev": float(os.environ.get("MR_BOLL_DEV", 2.0)),
            "mr_rsi_period": int(os.environ.get("MR_RSI_PERIOD", 14)),
            "mom_fast_period": int(os.environ.get("MOM_FAST_PERIOD", 10)),
            "mom_slow_period": int(os.environ.get("MOM_SLOW_PERIOD", 30)),
            "bo_donchian_period": int(os.environ.get("BO_DONCHIAN_PERIOD", 20)),
            "bo_atr_period": int(os.environ.get("BO_ATR_PERIOD", 14)),
            "bo_atr_multiplier": float(os.environ.get("BO_ATR_MULTIPLIER", 2.0)),
            "atr_stop_multiplier": float(os.environ.get("ATR_STOP_MULTIPLIER", 2.0)),
            "atr_trailing_multiplier": float(os.environ.get("ATR_TRAILING_MULTIPLIER", 1.5)),
        },
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
    }


def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Paper Trading")
    parser.add_argument("--symbol", type=str, default=None, help="Trading symbol (e.g. btcusdt, ethusdt)")
    parser.add_argument("--name", type=str, default=None, help="Strategy instance name")
    parser.add_argument("--volume", type=str, default=None, help="Trade volume per order (e.g. 0.01)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config only, don't connect")
    args = parser.parse_args()

    config = get_config(args)

    print("SIQE V3 - Paper Trading Configuration")
    print("=" * 60)
    print(f"  Server:       {config['server']}")
    print(f"  Symbol:       {config['symbol']}")
    print(f"  Strategy:     {config['strategy_name']}")
    print(f"  Volume:       {config['strategy_params']['fixed_volume']}")
    print(f"  API Key:      {config['api_key'][:10]}...{config['api_key'][-4:] if config['api_key'] else 'NOT SET'}")
    print(f"  Log Level:    {config['log_level']}")
    print()

    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  [ERROR] {e}")
        print("\nPlease fix the errors above before running paper trading.")
        return 1

    if args.dry_run:
        print("[DRY RUN] Configuration is valid. No connection made.")
        print("Remove --dry-run to start paper trading.")
        return 0

    # Launch paper trading
    print("Starting paper trading...")
    print("Press Ctrl+C to stop.\n")

    from vnpy_native.live_runner import SiqeLiveRunner

    runner = SiqeLiveRunner(**config)
    runner.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
