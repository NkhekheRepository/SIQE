"""
Indicator Configuration Tests

Tests for IndicatorConfig validation, serialization, and integration with BaseStrategy.
Includes property-based tests for robust edge case coverage.
"""
import pytest
import sys
import os
from dataclasses import replace

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_engine.config import IndicatorConfig, IndicatorBounds, IndicatorValidationError


class TestIndicatorConfigDefaults:
    def test_default_values(self):
        config = IndicatorConfig()
        assert config.bollinger_period == 20
        assert config.bollinger_std == 2.0
        assert config.rsi_period == 14
        assert config.macd_fast == 12
        assert config.macd_slow == 26
        assert config.macd_signal == 9
        assert config.atr_period == 14
        assert config.donchian_period == 20
        assert config.adx_period == 14

    def test_to_dict_contains_all_keys(self):
        config = IndicatorConfig()
        d = config.to_dict()
        expected_keys = {
            "bollinger_period", "bollinger_std", "rsi_period",
            "macd_fast", "macd_slow", "macd_signal",
            "atr_period", "donchian_period", "adx_period",
        }
        assert set(d.keys()) == expected_keys

    def test_from_dict_roundtrip(self):
        original = IndicatorConfig(
            bollinger_period=30,
            bollinger_std=2.5,
            rsi_period=21,
            macd_fast=10,
            macd_slow=30,
            macd_signal=8,
            atr_period=20,
            donchian_period=25,
            adx_period=14,
        )
        restored = IndicatorConfig.from_dict(original.to_dict())
        assert original.to_dict() == restored.to_dict()


class TestIndicatorConfigValidation:
    def test_negative_rsi_period_raises(self):
        with pytest.raises(IndicatorValidationError, match="rsi_period"):
            IndicatorConfig(rsi_period=-5)

    def test_zero_rsi_period_raises(self):
        with pytest.raises(IndicatorValidationError, match="rsi_period"):
            IndicatorConfig(rsi_period=0)

    def test_macd_fast_gte_macd_slow_raises(self):
        with pytest.raises(IndicatorValidationError, match="macd_fast.*must be < macd_slow"):
            IndicatorConfig(macd_fast=26, macd_slow=26)

        with pytest.raises(IndicatorValidationError, match="macd_fast.*must be < macd_slow"):
            IndicatorConfig(macd_fast=30, macd_slow=20)

    def test_bollinger_std_out_of_range_raises(self):
        with pytest.raises(IndicatorValidationError, match="bollinger_std"):
            IndicatorConfig(bollinger_std=0.1)

        with pytest.raises(IndicatorValidationError, match="bollinger_std"):
            IndicatorConfig(bollinger_std=5.0)

    def test_multiple_errors_reported(self):
        with pytest.raises(IndicatorValidationError) as exc_info:
            IndicatorConfig(rsi_period=-1, bollinger_period=0)
        error_msg = str(exc_info.value)
        assert "rsi_period" in error_msg
        assert "bollinger_period" in error_msg

    def test_validate_classmethod_returns_errors(self):
        valid, errors = IndicatorConfig.validate({"rsi_period": -1})
        assert valid is False
        assert len(errors) > 0

        valid, errors = IndicatorConfig.validate({"rsi_period": 14})
        assert valid is True
        assert errors == []


class TestIndicatorConfigUpdate:
    def test_update_returns_new_config(self):
        original = IndicatorConfig()
        updated = original.update(rsi_period=21)
        assert original.rsi_period == 14
        assert updated.rsi_period == 21

    def test_update_validates(self):
        config = IndicatorConfig()
        with pytest.raises(IndicatorValidationError):
            config.update(rsi_period=-1)

    def test_from_dict_ignores_extra_keys(self):
        config = IndicatorConfig.from_dict({
            "rsi_period": 21,
            "unknown_key": "value",
            "another_key": 123,
        })
        assert config.rsi_period == 21


class TestIndicatorConfigMerge:
    def test_merge_non_default_values(self):
        base = IndicatorConfig()
        other = IndicatorConfig(rsi_period=21)
        merged = base.merge(other)
        assert merged.rsi_period == 21
        assert merged.bollinger_period == 20

    def test_merge_preserves_base_when_other_is_default(self):
        base = IndicatorConfig(rsi_period=21)
        other = IndicatorConfig()
        merged = base.merge(other)
        assert merged.rsi_period == 21


class TestIndicatorBounds:
    def test_bounds_are_tuples(self):
        assert isinstance(IndicatorBounds.RSI_PERIOD, tuple)
        assert isinstance(IndicatorBounds.BOLLINGER_STD, tuple)

    def test_bounds_min_less_than_max(self):
        for field_name in (
            "BOLLINGER_PERIOD", "BOLLINGER_STD", "RSI_PERIOD",
            "MACD_FAST", "MACD_SLOW", "MACD_SIGNAL",
            "ATR_PERIOD", "DONCHIAN_PERIOD", "ADX_PERIOD",
        ):
            bounds = getattr(IndicatorBounds, field_name)
            assert bounds[0] < bounds[1], f"{field_name} min >= max"


class TestIndicatorConfigPropertyBased:
    @given(st.integers(min_value=5, max_value=50))
    def test_valid_rsi_period_accepted(self, rsi_period):
        config = IndicatorConfig(rsi_period=rsi_period)
        assert config.rsi_period == rsi_period

    @given(st.floats(min_value=0.5, max_value=4.0, allow_nan=False, allow_infinity=False))
    def test_valid_bollinger_std_accepted(self, bollinger_std):
        config = IndicatorConfig(bollinger_std=bollinger_std)
        assert config.bollinger_std == bollinger_std

    @given(
        st.integers(min_value=5, max_value=29),
        st.integers(min_value=20, max_value=100),
    )
    def test_macd_relationship_validated(self, macd_fast, macd_slow):
        assume(macd_fast < macd_slow)
        config = IndicatorConfig(macd_fast=macd_fast, macd_slow=macd_slow)
        assert config.macd_fast < config.macd_slow

    @given(st.integers(max_value=0))
    def test_non_positive_rsi_rejected(self, rsi_period):
        with pytest.raises(IndicatorValidationError):
            IndicatorConfig(rsi_period=rsi_period)

    @given(st.floats(max_value=0.0, allow_nan=False, allow_infinity=False))
    def test_non_positive_bollinger_std_rejected(self, bollinger_std):
        with pytest.raises(IndicatorValidationError):
            IndicatorConfig(bollinger_std=bollinger_std)

    @settings(max_examples=100)
    @given(
        st.integers(min_value=5, max_value=100),
        st.floats(min_value=0.5, max_value=4.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=5, max_value=50),
        st.integers(min_value=5, max_value=29),
        st.integers(min_value=30, max_value=100),
        st.integers(min_value=5, max_value=20),
        st.integers(min_value=5, max_value=50),
        st.integers(min_value=10, max_value=100),
        st.integers(min_value=7, max_value=30),
    )
    def test_all_valid_ranges_produce_consistent_configs(
        self, bollinger_period, bollinger_std, rsi_period,
        macd_fast, macd_slow, macd_signal,
        atr_period, donchian_period, adx_period,
    ):
        assume(macd_fast < macd_slow)
        config = IndicatorConfig(
            bollinger_period=bollinger_period,
            bollinger_std=bollinger_std,
            rsi_period=rsi_period,
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            atr_period=atr_period,
            donchian_period=donchian_period,
            adx_period=adx_period,
        )
        d = config.to_dict()
        assert d["bollinger_period"] == bollinger_period
        assert d["bollinger_std"] == bollinger_std
        assert d["rsi_period"] == rsi_period
        assert d["macd_fast"] == macd_fast
        assert d["macd_slow"] == macd_slow
        assert d["macd_signal"] == macd_signal
        assert d["atr_period"] == atr_period
        assert d["donchian_period"] == donchian_period
        assert d["adx_period"] == adx_period
