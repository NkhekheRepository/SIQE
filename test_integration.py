#!/usr/bin/env python3
"""
SIQE V3 - Quick Integration Test

Tests that all components import and initialize correctly.
"""
import sys
from pathlib import Path

# Add project root to path
siqe_root = Path(__file__).resolve().parent
sys.path.insert(0, str(siqe_root))

def test_imports():
    """Test that all key modules can be imported."""
    print("Testing imports...")
    
    try:
        # Test strategy imports
        from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        print("  ✓ Strategy imports successful")
    except Exception as e:
        print(f"  ✗ Strategy import failed: {e}")
        return False
    
    try:
        # Test runner imports
        from vnpy_native.live_runner import SiqeLiveRunner, run_live
        print("  ✓ Live runner imports successful")
    except Exception as e:
        print(f"  ✗ Live runner import failed: {e}")
        return False
        
    try:
        # Test gateway imports
        from vnpy_binance import BinanceSpotGateway, BinanceLinearGateway
        print("  ✓ Gateway imports successful")
    except Exception as e:
        print(f"  ✗ Gateway import failed: {e}")
        return False
        
    try:
        # Test backtesting imports
        from vnpy_ctastrategy.backtesting import BacktestingEngine
        from vnpy_ctastrategy.base import BacktestingMode
        print("  ✓ Backtesting imports successful")
    except Exception as e:
        print(f"  ✗ Backtesting import failed: {e}")
        return False
    
    return True

def test_strategy_instantiation():
    """Test that strategies can be instantiated."""
    print("\nTesting strategy instantiation...")
    
    try:
        from vnpy_native.strategies.siqe_cta_strategy import SiqeCtaStrategy
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        
        # Mock CTA engine
        class MockEngine:
            capital = 10000
            
        engine = MockEngine()
        
        # Test spot strategy
        spot_strategy = SiqeCtaStrategy(engine, "test_spot", "btcusdt.GLOBAL", {})
        print("  ✓ SiqeCtaStrategy instantiated")
        
        # Test futures strategy
        futures_strategy = SiqeFuturesStrategy(engine, "test_futures", "btcusdt.GLOBAL", {
            "leverage": 50,
            "risk_pct": 0.02
        })
        print("  ✓ SiqeFuturesStrategy instantiated")
        
        return True
    except Exception as e:
        print(f"  ✗ Strategy instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration():
    """Test that configuration loads correctly."""
    print("\nTesting configuration...")
    
    try:
        from dotenv import load_dotenv
        import os
        
        env_path = siqe_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            futures_key = os.environ.get("FUTURES_API_KEY", "") or os.environ.get("EXCHANGE_API_KEY", "")
            futures_secret = os.environ.get("FUTURES_API_SECRET", "") or os.environ.get("EXCHANGE_API_SECRET", "")
            
            if futures_key and futures_secret:
                print("  ✓ API credentials found in .env")
                print(f"    Key: {futures_key[:8]}...{futures_key[-4:] if len(futures_key) > 12 else ''}")
                return True
            else:
                print("  ⚠ API credentials not found (expected for fresh setup)")
                print("    To test: generate TESTNET keys from https://testnet.binancefuture.com")
                return True  # Not a failure - expected in initial state
        else:
            print("  ⚠ .env file not found")
            return False
    except Exception as e:
        print(f"  ✗ Configuration test failed: {e}")
        return False


def test_hybrid_integration():
    """Test hybrid architecture: SIQEEngine + VN.PY integration."""
    print("\nTesting hybrid architecture integration...")
    
    try:
        from vnpy_native.live_runner import SiqeLiveRunner
        from core.clock import EventClock
        from config.settings import Settings
        
        runner = SiqeLiveRunner(
            api_key="",
            api_secret="",
            server="SIMULATOR",
            symbol="btcusdt",
            market_type="spot",
            strategy_name="test_hybrid",
            strategy_params={"leverage": 35},
        )
        print("  ✓ SiqeLiveRunner instantiated")
        
        assert hasattr(runner, 'siqe_engine'), "Missing siqe_engine attribute"
        assert hasattr(runner, 'set_siqe_engine'), "Missing set_siqe_engine method"
        assert hasattr(runner, 'register_strategy_callbacks'), "Missing register_strategy_callbacks"
        assert hasattr(runner, 'get_risk_status'), "Missing get_risk_status method"
        assert hasattr(runner, '_on_trade'), "Missing _on_trade callback"
        print("  ✓ SIQEEngine integration methods present")
        
        return True
    except Exception as e:
        print(f"  ✗ Hybrid integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_siqe_engine_standalone_apis():
    """Test SIQEEngine standalone APIs for hybrid mode."""
    print("\nTesting SIQEEngine standalone APIs...")
    
    try:
        import asyncio
        from main import SIQEEngine
        
        engine = SIQEEngine()
        
        assert hasattr(engine, 'validate_signal'), "Missing validate_signal method"
        assert hasattr(engine, 'process_trade_result'), "Missing process_trade_result method"
        assert hasattr(engine, 'get_risk_status'), "Missing get_risk_status method"
        assert hasattr(engine, 'get_learning_status'), "Missing get_learning_status method"
        print("  ✓ SIQEEngine standalone methods present")
        
        risk_status = engine.get_risk_status()
        assert 'daily_pnl' in risk_status, "Risk status missing daily_pnl"
        assert 'consecutive_losses' in risk_status, "Risk status missing consecutive_losses"
        print("  ✓ get_risk_status returns correct structure")
        
        return True
    except Exception as e:
        print(f"  ✗ SIQEEngine standalone API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strategy_callbacks():
    """Test that strategy has callback integration."""
    print("\nTesting strategy callbacks...")
    
    try:
        from vnpy_native.strategies.siqe_futures_strategy import SiqeFuturesStrategy
        
        class MockEngine:
            capital = 10000
            def __init__(self):
                self.capital = 10000
            def write_log(self, msg, strategy=None):
                pass
        
        engine = MockEngine()
        strategy = SiqeFuturesStrategy(engine, "test_cb", "btcusdt.GLOBAL", {
            "leverage": 35
        })
        
        assert hasattr(strategy, '_trade_callback'), "Missing _trade_callback attribute"
        assert hasattr(strategy, 'set_trade_callback'), "Missing set_trade_callback method"
        assert hasattr(strategy, '_async_risk_check'), "Missing _async_risk_check method"
        assert hasattr(strategy, 'set_risk_check_callback'), "Missing set_risk_check_callback method"
        print("  ✓ Strategy callback methods present")
        
        callback_called = []
        def test_callback(trade):
            callback_called.append(trade)
        
        strategy.set_trade_callback(test_callback)
        assert strategy._trade_callback is test_callback, "Callback not set correctly"
        print("  ✓ set_trade_callback works")
        
        return True
    except Exception as e:
        print(f"  ✗ Strategy callback test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 50)
    print("SIQE V3 - Integration Test")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_strategy_instantiation,
        test_configuration,
        test_hybrid_integration,
        test_siqe_engine_standalone_apis,
        test_strategy_callbacks,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All integration tests passed!")
        print("  SIQE V3 futures components are ready for use.")
        return 0
    else:
        print("✗ Some integration tests failed.")
        print("  Please check the error messages above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())