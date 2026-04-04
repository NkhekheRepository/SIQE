#!/usr/bin/env python3
"""
Production Validation Script
Verifies all components are correctly configured for live trading.
Run before enabling USE_MOCK_EXECUTION=false.
"""
import sys
import os
import asyncio
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings, get_settings
from core.clock import EventClock


class ValidationResult:
    def __init__(self, check: str, passed: bool, message: str = "", details: Dict[str, Any] = None):
        self.check = check
        self.passed = passed
        self.message = message
        self.details = details or {}

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.check}: {self.message}"


async def validate_settings_production_mode() -> ValidationResult:
    settings = Settings()
    is_valid, errors = settings.validate()
    if is_valid:
        return ValidationResult("Settings Validation", True, "All settings valid")
    return ValidationResult("Settings Validation", False, f"{len(errors)} errors: {'; '.join(errors)}")


async def validate_environment_mode() -> ValidationResult:
    settings = Settings()
    env = settings.environment
    if env == "development":
        return ValidationResult("Environment Mode", True, f"Running in {env} mode (safe for testing)")
    elif env == "production":
        if not settings.use_mock_execution:
            return ValidationResult("Environment Mode", True, "Production mode with live execution enabled")
        return ValidationResult("Environment Mode", False, "ENVIRONMENT=production but USE_MOCK_EXECUTION=true (inconsistent)")
    return ValidationResult("Environment Mode", False, f"Unknown environment: {env}")


async def validate_execution_mode() -> ValidationResult:
    settings = Settings()
    if settings.use_mock_execution:
        return ValidationResult("Execution Mode", True, "Mock execution enabled (paper trading)")
    return ValidationResult("Execution Mode", True, "Live execution enabled (real trading)")


async def validate_api_keys() -> ValidationResult:
    settings = Settings()
    if settings.use_mock_execution:
        return ValidationResult("API Keys", True, "Not required (mock execution enabled)")
    if not settings.exchange_api_key:
        return ValidationResult("API Keys", False, "EXCHANGE_API_KEY is empty")
    if not settings.exchange_api_secret:
        return ValidationResult("API Keys", False, "EXCHANGE_API_SECRET is empty")
    masked_key = settings.exchange_api_key[:4] + "..." + settings.exchange_api_key[-4:]
    return ValidationResult("API Keys", True, f"API key present: {masked_key}")


async def validate_exchange_server() -> ValidationResult:
    settings = Settings()
    server = settings.exchange_server
    if server == "SIMULATOR":
        return ValidationResult("Exchange Server", True, "Using simulator (paper trading)")
    elif server == "LIVE":
        if not settings.use_mock_execution:
            return ValidationResult("Exchange Server", True, "Using LIVE server (real trading)")
        return ValidationResult("Exchange Server", False, "LIVE server but mock execution enabled (inconsistent)")
    return ValidationResult("Exchange Server", False, f"Unknown exchange server: {server}")


async def validate_gateway() -> ValidationResult:
    settings = Settings()
    gateway = settings.vnpy_gateway.upper()
    supported = ["BINANCE", "CTP"]
    if gateway in supported:
        return ValidationResult("VN.PY Gateway", True, f"Gateway: {gateway}")
    return ValidationResult("VN.PY Gateway", False, f"Unsupported gateway: {gateway}")


async def validate_risk_limits() -> ValidationResult:
    settings = Settings()
    issues = []
    if settings.max_position_size > 0.5:
        issues.append(f"MAX_POSITION_SIZE={settings.max_position_size} is very high")
    if settings.max_daily_loss > 0.10:
        issues.append(f"MAX_DAILY_LOSS={settings.max_daily_loss} is very high")
    if settings.max_drawdown > 0.30:
        issues.append(f"MAX_DRAWDOWN={settings.max_drawdown} is very high")
    if issues:
        return ValidationResult("Risk Limits", True, "Limits configured but aggressive: " + "; ".join(issues))
    return ValidationResult("Risk Limits", True, "Risk limits within reasonable bounds")


async def validate_database() -> ValidationResult:
    settings = Settings()
    db_path = settings.db_path
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            return ValidationResult("Database", True, f"Created directory: {db_dir}")
        except Exception as e:
            return ValidationResult("Database", False, f"Cannot create directory: {e}")
    return ValidationResult("Database", True, f"Database path: {db_path}")


async def validate_log_directory() -> ValidationResult:
    settings = Settings()
    log_file = settings.log_file
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            return ValidationResult("Log Directory", True, f"Created directory: {log_dir}")
        except Exception as e:
            return ValidationResult("Log Directory", False, f"Cannot create directory: {e}")
    return ValidationResult("Log Directory", True, f"Log file: {log_file}")


async def validate_clock() -> ValidationResult:
    try:
        clock = EventClock()
        now = clock.now
        if now >= 0:
            return ValidationResult("Event Clock", True, f"Clock initialized, tick={now}")
        return ValidationResult("Event Clock", False, "Clock tick is negative")
    except Exception as e:
        return ValidationResult("Event Clock", False, f"Clock error: {e}")


async def validate_vnpy_imports() -> ValidationResult:
    if not Settings().use_mock_execution:
        try:
            import vnpy
            import vnpy_binance
            import vnpy_ctp
            return ValidationResult("VN.PY Imports", True, "All VN.PY packages available")
        except ImportError as e:
            return ValidationResult("VN.PY Imports", False, f"Missing package: {e}")
    return ValidationResult("VN.PY Imports", True, "Not required (mock execution enabled)")


async def run_validations() -> List[ValidationResult]:
    validations = [
        validate_settings_production_mode,
        validate_environment_mode,
        validate_execution_mode,
        validate_api_keys,
        validate_exchange_server,
        validate_gateway,
        validate_risk_limits,
        validate_database,
        validate_log_directory,
        validate_clock,
        validate_vnpy_imports,
    ]

    results = []
    for validation in validations:
        try:
            result = await validation()
        except Exception as e:
            result = ValidationResult(validation.__name__.replace("validate_", ""), False, f"Unexpected error: {e}")
        results.append(result)

    return results


def print_report(results: List[ValidationResult]):
    print("=" * 70)
    print("SIQE V3 Production Validation Report")
    print("=" * 70)
    print()

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    for r in results:
        print(f"  {r}")

    print()
    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("-" * 70)

    if failed > 0:
        print()
        print("FAILED CHECKS:")
        for r in results:
            if not r.passed:
                print(f"  - {r.check}: {r.message}")
        print()
        print("ACTION REQUIRED: Fix the above issues before enabling live trading.")
        print("  1. Set USE_MOCK_EXECUTION=false in .env")
        print("  2. Set EXCHANGE_API_KEY and EXCHANGE_API_SECRET in .env")
        print("  3. Set ENVIRONMENT=production in .env")
        print("  4. Set EXCHANGE_SERVER=LIVE in .env (after paper trading validation)")
    else:
        print()
        print("ALL CHECKS PASSED - System is ready for production validation.")

    return failed == 0


async def main():
    print("Running production validation...")
    print()
    results = await run_validations()
    success = print_report(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
