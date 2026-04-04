"""
SIQE V3 - Futures Paper Trading Launcher

Launches the SiqeFuturesStrategy in paper trading mode using VN.PY's
Binance USDT-M Futures gateway with TESTNET server.

Usage:
    python scripts/paper_trade_futures.py                     # Uses .env defaults (BTC, 50x)
    python scripts/paper_trade_futures.py --symbol ETH        # Trade ETH
    python scripts/paper_trade_futures.py --leverage 75       # 75x leverage
    python scripts/paper_trade_futures.py --dry-run           # Validate config only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPPORTED_SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt", "dogeusdt"]


def validate_config(config: dict) -> list[str]:
    """Validate futures paper trading configuration."""
    errors = []
    if not config["api_key"]:
        errors.append("FUTURES_API_KEY (or EXCHANGE_API_KEY) is not set")
    if not config["api_secret"]:
        errors.append("FUTURES_API_SECRET (or EXCHANGE_API_SECRET) is not set")
    if config["symbol"] not in SUPPORTED_SYMBOLS:
        errors.append(f"Symbol '{config['symbol']}' not in supported list: {SUPPORTED_SYMBOLS}")
    if not (35 <= config["leverage"] <= 75):
        errors.append(f"Leverage {config['leverage']}x out of range (35-75x)")
    if config["server"] not in ("TESTNET", "SIMULATOR"):
        errors.append(f"Server '{config['server']}' should be 'TESTNET' or 'SIMULATOR'")
    return errors


def get_config(args) -> dict:
    """Build configuration from .env and command-line overrides."""
    symbol = (args.symbol or os.environ.get("FUTURES_SYMBOL", "btcusdt")).lower()
    leverage = int(args.leverage or os.environ.get("FUTURES_LEVERAGE", "50"))
    server = os.environ.get("EXCHANGE_SERVER", "TESTNET")

    api_key = os.environ.get("FUTURES_API_KEY", "") or os.environ.get("EXCHANGE_API_KEY", "")
    api_secret = os.environ.get("FUTURES_API_SECRET", "") or os.environ.get("EXCHANGE_API_SECRET", "")

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "server": server,
        "symbol": symbol,
        "leverage": leverage,
        "risk_pct": float(os.environ.get("FUTURES_RISK_PCT", "0.02")),
        "strategy_name": args.name or "siqe_futures_paper",
        "strategy_params": {
            "leverage": leverage,
            "risk_pct": float(os.environ.get("FUTURES_RISK_PCT", "0.02")),
            "margin_alert_pct": float(os.environ.get("FUTURES_MARGIN_ALERT_PCT", "0.70")),
            "margin_stop_pct": float(os.environ.get("FUTURES_MARGIN_STOP_PCT", "0.90")),
            "atr_stop_multiplier": float(os.environ.get("FUTURES_ATR_STOP", "1.0")),
            "atr_trailing_multiplier": float(os.environ.get("FUTURES_ATR_TRAILING", "0.75")),
            "mr_boll_period": int(os.environ.get("MR_BOLL_PERIOD", "20")),
            "mr_boll_dev": float(os.environ.get("MR_BOLL_DEV", "2.0")),
            "mr_rsi_period": int(os.environ.get("MR_RSI_PERIOD", "14")),
            "mom_fast_period": int(os.environ.get("MOM_FAST_PERIOD", "10")),
            "mom_slow_period": int(os.environ.get("MOM_SLOW_PERIOD", "30")),
            "bo_donchian_period": int(os.environ.get("BO_DONCHIAN_PERIOD", "20")),
            "bo_atr_period": int(os.environ.get("BO_ATR_PERIOD", "14")),
            "bo_atr_multiplier": float(os.environ.get("BO_ATR_MULTIPLIER", "2.0")),
        },
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
    }


def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Futures Paper Trading")
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        choices=SUPPORTED_SYMBOLS,
        help="Futures pair to trade",
    )
    parser.add_argument(
        "--leverage",
        type=str,
        default=None,
        help="Leverage (35-75x, default 50x)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Strategy instance name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config only, don't connect",
    )
    args = parser.parse_args()

    config = get_config(args)

    print("SIQE V3 - Futures Paper Trading Configuration")
    print("=" * 60)
    print(f"  Server:         {config['server']}")
    print(f"  Symbol:         {config['symbol']}")
    print(f"  Leverage:       {config['leverage']}x")
    print(f"  Risk Pct:       {config['risk_pct']:.1%}")
    print(f"  Strategy:       {config['strategy_name']}")
    print(f"  Margin Alert:   {config['strategy_params']['margin_alert_pct']:.0%}")
    print(f"  Margin Stop:    {config['strategy_params']['margin_stop_pct']:.0%}")
    print(f"  ATR Stop:       {config['strategy_params']['atr_stop_multiplier']}x")
    print(f"  ATR Trailing:   {config['strategy_params']['atr_trailing_multiplier']}x")
    key = config["api_key"]
    print(f"  API Key:        {key[:10]}...{key[-4:] if key else 'NOT SET'}")
    print(f"  Log Level:      {config['log_level']}")
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
        print("Remove --dry-run to start paper trading.")
        return 0

    # Launch paper trading
    print("Starting futures paper trading...")
    print("Press Ctrl+C to stop.\n")

    from vnpy_native.live_runner import SiqeLiveRunner

    runner = SiqeLiveRunner(
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        server=config["server"],
        symbol=config["symbol"],
        market_type="futures",
        strategy_name=config["strategy_name"],
        strategy_params=config["strategy_params"],
        log_level=config["log_level"],
    )
    runner.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
