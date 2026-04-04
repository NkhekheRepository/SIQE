"""
Validation Script Tests
Tests for the production validation script logic.
"""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.validate_production import (
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
)


class TestValidationScript:
    @pytest.mark.asyncio
    async def test_validation_mock_mode_passes(self):
        with patch("scripts.validate_production.Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.validate.return_value = (True, [])
            mock_settings.environment = "development"
            mock_settings.use_mock_execution = True
            mock_settings.exchange_api_key = ""
            mock_settings.exchange_api_secret = ""
            mock_settings.exchange_server = "SIMULATOR"
            mock_settings.vnpy_gateway = "BINANCE"
            mock_settings.max_position_size = 0.1
            mock_settings.max_daily_loss = 0.05
            mock_settings.max_drawdown = 0.20
            mock_settings.db_path = "./data/siqe.db"
            mock_settings.log_file = "./logs/siqe.log"
            mock_settings_cls.return_value = mock_settings

            result = await validate_settings_production_mode()
            assert result.passed is True

            result = await validate_environment_mode()
            assert result.passed is True

            result = await validate_execution_mode()
            assert result.passed is True

            result = await validate_api_keys()
            assert result.passed is True

            result = await validate_exchange_server()
            assert result.passed is True

            result = await validate_gateway()
            assert result.passed is True

            result = await validate_risk_limits()
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_validation_missing_api_keys_fails(self):
        with patch("scripts.validate_production.Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.validate.return_value = (False, [
                "EXCHANGE_API_KEY is required for live trading",
                "EXCHANGE_API_SECRET is required for live trading",
            ])
            mock_settings.environment = "production"
            mock_settings.use_mock_execution = False
            mock_settings.exchange_api_key = ""
            mock_settings.exchange_api_secret = ""
            mock_settings.exchange_server = "LIVE"
            mock_settings.vnpy_gateway = "BINANCE"
            mock_settings.max_position_size = 0.1
            mock_settings.max_daily_loss = 0.05
            mock_settings.max_drawdown = 0.20
            mock_settings.db_path = "./data/siqe.db"
            mock_settings.log_file = "./logs/siqe.log"
            mock_settings_cls.return_value = mock_settings

            result = await validate_settings_production_mode()
            assert result.passed is False

            result = await validate_api_keys()
            assert result.passed is False

    @pytest.mark.asyncio
    async def test_validation_inconsistent_settings(self):
        with patch("scripts.validate_production.Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.validate.return_value = (False, [
                "ENVIRONMENT should be 'production' when USE_MOCK_EXECUTION=false",
            ])
            mock_settings.environment = "development"
            mock_settings.use_mock_execution = False
            mock_settings.exchange_api_key = "test_key"
            mock_settings.exchange_api_secret = "test_secret"
            mock_settings.exchange_server = "LIVE"
            mock_settings.vnpy_gateway = "BINANCE"
            mock_settings.max_position_size = 0.1
            mock_settings.max_daily_loss = 0.05
            mock_settings.max_drawdown = 0.20
            mock_settings.db_path = "./data/siqe.db"
            mock_settings.log_file = "./logs/siqe.log"
            mock_settings_cls.return_value = mock_settings

            result = await validate_settings_production_mode()
            assert result.passed is False

            result = await validate_environment_mode()
            assert result.passed is True
