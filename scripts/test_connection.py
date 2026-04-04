#!/usr/bin/env python3
"""
Connection Test Script
Tests VN.PY Binance gateway connection, market data, and paper trading.
Run this before enabling live trading to verify all components work.
"""
import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.clock import EventClock
from execution_adapter.vnpy_bridge import ExecutionAdapter
from core.data_engine import DataEngine
from config.settings import Settings


class ConnectionTestResult:
    def __init__(self, test: str, passed: bool, message: str = "", details: dict = None):
        self.test = test
        self.passed = passed
        self.message = message
        self.details = details or {}

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.test}: {self.message}"


async def test_execution_adapter_initialization() -> ConnectionTestResult:
    try:
        settings = Settings()
        clock = EventClock()
        adapter = ExecutionAdapter(settings, clock)

        success = await adapter.initialize()

        if success:
            mode = "mock" if settings.use_mock_execution else "live"
            return ConnectionTestResult(
                "Execution Adapter Initialization",
                True,
                f"Initialized in {mode} mode",
                {"mode": mode, "gateway": settings.vnpy_gateway},
            )
        else:
            return ConnectionTestResult(
                "Execution Adapter Initialization",
                False,
                "Failed to initialize execution adapter",
            )
    except Exception as e:
        return ConnectionTestResult(
            "Execution Adapter Initialization",
            False,
            f"Exception: {e}",
        )


async def test_market_data_subscription(adapter: ExecutionAdapter) -> ConnectionTestResult:
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        success = await adapter.bridge.subscribe_market_data(symbols)

        if success:
            market_data = await adapter.bridge.get_all_market_data()
            return ConnectionTestResult(
                "Market Data Subscription",
                True,
                f"Subscribed to {len(market_data)} symbols",
                {"symbols": list(market_data.keys()), "data": market_data},
            )
        else:
            return ConnectionTestResult(
                "Market Data Subscription",
                False,
                "Failed to subscribe to market data",
            )
    except Exception as e:
        return ConnectionTestResult(
            "Market Data Subscription",
            False,
            f"Exception: {e}",
        )


async def test_live_price_retrieval(adapter: ExecutionAdapter) -> ConnectionTestResult:
    try:
        symbols = ["BTCUSDT", "ETHUSDT"]
        prices = {}

        for symbol in symbols:
            data = await adapter.bridge.get_market_data(symbol)
            if data.get("bid", 0) > 0 and data.get("ask", 0) > 0:
                prices[symbol] = {
                    "bid": data["bid"],
                    "ask": data["ask"],
                    "spread": data["ask"] - data["bid"],
                    "spread_bps": round((data["ask"] - data["bid"]) / data["bid"] * 10000, 2),
                }

        if prices:
            return ConnectionTestResult(
                "Live Price Retrieval",
                True,
                f"Retrieved prices for {len(prices)} symbols",
                {"prices": prices},
            )
        else:
            return ConnectionTestResult(
                "Live Price Retrieval",
                False,
                "No valid prices received",
            )
    except Exception as e:
        return ConnectionTestResult(
            "Live Price Retrieval",
            False,
            f"Exception: {e}",
        )


async def test_paper_trade_execution(adapter: ExecutionAdapter) -> ConnectionTestResult:
    try:
        result = await adapter.bridge.execute_order(
            symbol="BTCUSDT",
            order_type="long",
            price=50000.0,
            strength=0.5,
            execution_id="test_trade_001",
        )

        if result.get("success"):
            return ConnectionTestResult(
                "Paper Trade Execution",
                True,
                f"Executed {result.get('filled_quantity', 0):.6f} BTCUSDT @ {result.get('filled_price', 0):.2f}",
                {"result": result},
            )
        else:
            return ConnectionTestResult(
                "Paper Trade Execution",
                False,
                f"Trade failed: {result.get('error', 'unknown')}",
                {"result": result},
            )
    except Exception as e:
        return ConnectionTestResult(
            "Paper Trade Execution",
            False,
            f"Exception: {e}",
        )


async def test_account_info(adapter: ExecutionAdapter) -> ConnectionTestResult:
    try:
        account = await adapter.bridge.get_account_info()

        if account.get("success"):
            return ConnectionTestResult(
                "Account Information",
                True,
                f"Balance: {account.get('account_balance', 0):.2f} {account.get('currency', 'USDT')}",
                {"account": account},
            )
        else:
            return ConnectionTestResult(
                "Account Information",
                False,
                f"Failed to get account info: {account.get('error', 'unknown')}",
            )
    except Exception as e:
        return ConnectionTestResult(
            "Account Information",
            False,
            f"Exception: {e}",
        )


async def test_data_engine_integration(adapter: ExecutionAdapter) -> ConnectionTestResult:
    try:
        settings = Settings()
        clock = EventClock()
        data_engine = DataEngine(settings, clock)
        data_engine.set_execution_adapter(adapter)

        success = await data_engine.initialize()

        if success:
            market_data = await data_engine.get_latest_data()
            if market_data:
                return ConnectionTestResult(
                    "Data Engine Integration",
                    True,
                    f"Received market data for {len(market_data)} symbols",
                    {"symbols": list(market_data.keys())},
                )
            else:
                return ConnectionTestResult(
                    "Data Engine Integration",
                    False,
                    "Data engine returned no market data",
                )
        else:
            return ConnectionTestResult(
                "Data Engine Integration",
                False,
                "Failed to initialize data engine",
            )
    except Exception as e:
        return ConnectionTestResult(
            "Data Engine Integration",
            False,
            f"Exception: {e}",
        )


async def run_all_tests() -> list:
    results = []

    print("=" * 70)
    print("SIQE V3 Connection Test")
    print("=" * 70)
    print()

    result = await test_execution_adapter_initialization()
    results.append(result)
    print(str(result))

    if not result.passed:
        print("\nExecution adapter failed - cannot continue tests")
        return results

    adapter_result = result
    settings = Settings()
    clock = EventClock()
    adapter = ExecutionAdapter(settings, clock)
    await adapter.initialize()

    tests = [
        ("Market Data Subscription", test_market_data_subscription),
        ("Live Price Retrieval", test_live_price_retrieval),
        ("Paper Trade Execution", test_paper_trade_execution),
        ("Account Information", test_account_info),
        ("Data Engine Integration", test_data_engine_integration),
    ]

    print()
    for test_name, test_func in tests:
        result = await test_func(adapter)
        results.append(result)
        print(str(result))

    print()
    print("-" * 70)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("-" * 70)

    for r in results:
        if r.passed and r.details:
            if "prices" in r.details:
                print(f"\n  Prices:")
                for symbol, price in r.details["prices"].items():
                    print(f"    {symbol}: bid={price['bid']:.2f}, ask={price['ask']:.2f}, spread={price['spread_bps']}bps")
            if "data" in r.details:
                print(f"\n  Market Data:")
                for symbol, data in r.details["data"].items():
                    print(f"    {symbol}: {data}")
            if "account" in r.details:
                print(f"\n  Account:")
                for key, value in r.details["account"].items():
                    print(f"    {key}: {value}")

    await adapter.shutdown()

    return results


async def main():
    results = await run_all_tests()
    failed = sum(1 for r in results if not r.passed)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
