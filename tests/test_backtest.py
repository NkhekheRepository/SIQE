"""
Backtest Engine Tests
Tests for deterministic replay, metrics accuracy, slippage models, and walk-forward windows.
"""
import pytest
import numpy as np
import pandas as pd

from core.clock import EventClock
from models.trade import SignalType, MarketEvent
from backtest.config import BacktestSettings, DataProviderType, SlippageModelType, LearningMode
from backtest.slippage_model import FixedBPSSlippage, LinearSlippage, VolumeImpactSlippage, create_slippage_model
from backtest.performance import PerformanceAnalyzer, TradeRecord
from backtest.data_provider import CSVProvider, BaseDataProvider
from backtest.engine import BacktestEngine
from backtest.walk_forward import WalkForwardOptimizer


@pytest.fixture
def clock():
    return EventClock()


@pytest.fixture
def bt_settings():
    return BacktestSettings(
        data_provider=DataProviderType.YFINANCE,
        symbols=["SPY"],
        start_date="2023-01-01",
        end_date="2023-03-01",
        timeframe="1d",
        initial_equity=10000.0,
        slippage_model=SlippageModelType.LINEAR,
        slippage_bps=10.0,
        learning_mode=LearningMode.FIXED,
        rng_seed=42,
    )


class TestSlippageModels:
    def test_fixed_bps_long(self):
        model = FixedBPSSlippage(bps=10.0)
        price = 100.0
        fill = model.apply(price, SignalType.LONG, 1.0)
        assert fill == 100.10

    def test_fixed_bps_short(self):
        model = FixedBPSSlippage(bps=10.0)
        price = 100.0
        fill = model.apply(price, SignalType.SHORT, 1.0)
        assert fill == 99.90

    def test_linear_slippage_positive(self):
        model = LinearSlippage(base_bps=5.0, size_factor=0.5)
        price = 100.0
        fill = model.apply(price, SignalType.LONG, 1.0, volume=1000.0, volatility=0.02)
        assert fill > price

    def test_linear_slippage_negative(self):
        model = LinearSlippage(base_bps=5.0, size_factor=0.5)
        price = 100.0
        fill = model.apply(price, SignalType.SHORT, 1.0, volume=1000.0, volatility=0.02)
        assert fill < price

    def test_volume_impact_slippage(self):
        model = VolumeImpactSlippage(impact_factor=0.1)
        price = 100.0
        fill = model.apply(price, SignalType.LONG, 100.0, volume=10000.0, volatility=0.02)
        assert fill > price
        assert fill < price * 1.01

    def test_volume_impact_zero_volume(self):
        model = VolumeImpactSlippage(impact_factor=0.1)
        price = 100.0
        fill = model.apply(price, SignalType.LONG, 100.0, volume=0.0, volatility=0.02)
        assert fill > price

    def test_create_slippage_model_factory(self):
        model = create_slippage_model("fixed_bps", bps=5.0)
        assert isinstance(model, FixedBPSSlippage)

        model = create_slippage_model("linear", base_bps=3.0)
        assert isinstance(model, LinearSlippage)

        model = create_slippage_model("volume_impact", impact_factor=0.2)
        assert isinstance(model, VolumeImpactSlippage)

    def test_create_slippage_model_invalid(self):
        with pytest.raises(ValueError):
            create_slippage_model("invalid_model")


class TestPerformanceAnalyzer:
    def test_empty_backtest(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        analyzer.record_equity(10000.0)
        analyzer.record_equity(10000.0)
        metrics = analyzer.compute()
        assert metrics.total_trades == 0
        assert metrics.total_return_pct == 0.0

    def test_single_winning_trade(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        analyzer.record_equity(10000.0)
        analyzer.record_equity(10100.0)
        analyzer.add_trade(TradeRecord(
            trade_id="t1", symbol="SPY", signal_type="long",
            entry_price=100.0, exit_price=101.0, size=100.0,
            pnl=100.0, pnl_pct=1.0, slippage=0.01,
            entry_seq=1, exit_seq=2, strategy="momentum", regime="TRENDING",
        ))
        metrics = analyzer.compute()
        assert metrics.total_trades == 1
        assert metrics.winning_trades == 1
        assert metrics.win_rate == 1.0
        assert metrics.total_pnl == 100.0

    def test_mixed_trades(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        analyzer.record_equity(10000.0)
        analyzer.record_equity(10100.0)
        analyzer.record_equity(10050.0)
        analyzer.record_equity(10200.0)

        for i, (pnl, stype) in enumerate([(100.0, "long"), (-50.0, "short"), (150.0, "long")]):
            analyzer.add_trade(TradeRecord(
                trade_id=f"t{i+1}", symbol="SPY", signal_type=stype,
                entry_price=100.0, exit_price=100.0, size=1.0,
                pnl=pnl, pnl_pct=0.0, slippage=0.0,
                entry_seq=i+1, exit_seq=i+2, strategy="momentum", regime="TRENDING",
            ))

        metrics = analyzer.compute()
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(2/3, abs=0.01)
        assert metrics.total_pnl == 200.0
        assert metrics.profit_factor > 1.0

    def test_max_drawdown(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        equity_points = [10000, 10500, 11000, 10000, 9000, 9500, 10500]
        for eq in equity_points:
            analyzer.record_equity(float(eq))
        metrics = analyzer.compute()
        assert metrics.max_drawdown == pytest.approx(0.1818, abs=0.01)

    def test_max_consecutive(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        analyzer.record_equity(10000.0)
        analyzer.record_equity(10050.0)

        pnls = [100, 100, 100, -50, -50, 100, -50, -50, -50, -50, 100]
        for i, pnl in enumerate(pnls):
            analyzer.record_equity(10000.0 + sum(pnls[:i+1]))
            analyzer.add_trade(TradeRecord(
                trade_id=f"t{i+1}", symbol="SPY", signal_type="long",
                entry_price=100.0, exit_price=100.0, size=1.0,
                pnl=pnl, pnl_pct=0.0, slippage=0.0,
                entry_seq=i+1, exit_seq=i+2, strategy="momentum",
            ))

        metrics = analyzer.compute()
        assert metrics.max_consecutive_wins == 3
        assert metrics.max_consecutive_losses == 4

    def test_pnl_by_symbol(self):
        analyzer = PerformanceAnalyzer(initial_equity=10000.0)
        analyzer.record_equity(10000.0)
        analyzer.record_equity(10100.0)

        for sym, pnl in [("AAPL", 50.0), ("GOOGL", 50.0), ("AAPL", -20.0)]:
            analyzer.add_trade(TradeRecord(
                trade_id=f"t_{sym}", symbol=sym, signal_type="long",
                entry_price=100.0, exit_price=100.0, size=1.0,
                pnl=pnl, pnl_pct=0.0, slippage=0.0,
                entry_seq=1, exit_seq=2, strategy="momentum",
            ))

        metrics = analyzer.compute()
        assert metrics.pnl_by_symbol["AAPL"] == pytest.approx(30.0)
        assert metrics.pnl_by_symbol["GOOGL"] == pytest.approx(50.0)


class TestCSVProvider:
    def test_csv_provider_from_dataframe(self, tmp_path):
        csv_file = tmp_path / "SPY.csv"
        data = {
            "date": ["2023-01-02", "2023-01-03", "2023-01-04"],
            "open": [380.0, 382.0, 384.0],
            "high": [383.0, 385.0, 387.0],
            "low": [379.0, 381.0, 383.0],
            "close": [382.0, 384.0, 386.0],
            "volume": [1000000, 1100000, 1200000],
        }
        pd.DataFrame(data).to_csv(csv_file, index=False)

        settings = BacktestSettings(
            data_provider=DataProviderType.CSV,
            symbols=["SPY"],
            csv_path=str(csv_file),
        )
        provider = CSVProvider()
        result = provider.fetch(settings)
        assert "SPY" in result
        assert len(result["SPY"]) == 3
        assert list(result["SPY"].columns) == ["open", "high", "low", "close", "volume"]

    def test_csv_provider_missing_columns(self, tmp_path):
        csv_file = tmp_path / "BAD.csv"
        pd.DataFrame({"date": ["2023-01-01"], "close": [100.0]}).to_csv(csv_file, index=False)

        settings = BacktestSettings(
            data_provider=DataProviderType.CSV,
            symbols=["BAD"],
            csv_path=str(csv_file),
        )
        provider = CSVProvider()
        with pytest.raises(ValueError, match="missing columns"):
            provider.fetch(settings)


class TestDataConversion:
    def test_ohlcv_to_market_events(self):
        df = pd.DataFrame({
            "datetime": pd.to_datetime(["2023-01-02", "2023-01-03"]),
            "open": [380.0, 382.0],
            "high": [383.0, 385.0],
            "low": [379.0, 381.0],
            "close": [382.0, 384.0],
            "volume": [1000000, 1100000],
        })
        data = {"SPY": df}

        settings = BacktestSettings(
            data_provider=DataProviderType.CSV,
            symbols=["SPY"],
        )
        clock = EventClock()
        provider = CSVProvider()
        events = provider.to_market_events(data, clock, settings)

        assert len(events) == 2
        assert events[0].symbol == "SPY"
        assert events[0].bid < events[0].ask
        assert events[0].event_seq == 1
        assert events[1].event_seq == 2
        assert events[0].volatility > 0

    def test_market_event_mid_price(self):
        df = pd.DataFrame({
            "datetime": pd.to_datetime(["2023-01-02"]),
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.0], "volume": [1000],
        })
        data = {"TEST": df}
        settings = BacktestSettings(data_provider=DataProviderType.CSV, symbols=["TEST"])
        clock = EventClock()
        events = CSVProvider().to_market_events(data, clock, settings)
        assert events[0].mid_price == pytest.approx(100.0, abs=0.01)


class TestBacktestSettings:
    def test_defaults(self):
        settings = BacktestSettings()
        assert settings.data_provider == DataProviderType.YFINANCE
        assert settings.symbols == ["SPY"]
        assert settings.initial_equity == 10000.0
        assert settings.learning_mode == LearningMode.FIXED
        assert settings.rng_seed == 42

    def test_custom_settings(self):
        settings = BacktestSettings(
            symbols=["AAPL", "GOOGL"],
            timeframe="1h",
            initial_equity=50000.0,
            slippage_model=SlippageModelType.VOLUME_IMPACT,
            learning_mode=LearningMode.ADAPTIVE,
            rng_seed=123,
        )
        assert settings.symbols == ["AAPL", "GOOGL"]
        assert settings.timeframe == "1h"
        assert settings.initial_equity == 50000.0
        assert settings.learning_mode == LearningMode.ADAPTIVE


class TestWalkForwardWindows:
    def test_window_generation(self):
        df = pd.DataFrame({
            "datetime": pd.date_range("2023-01-01", periods=500, freq="D"),
            "open": np.random.randn(500).cumsum() + 400,
            "high": np.random.randn(500).cumsum() + 405,
            "low": np.random.randn(500).cumsum() + 395,
            "close": np.random.randn(500).cumsum() + 400,
            "volume": np.random.randint(1000, 5000, 500),
        })
        data = {"SPY": df}

        settings = BacktestSettings(
            data_provider=DataProviderType.CSV,
            symbols=["SPY"],
        )
        optimizer = WalkForwardOptimizer(
            base_settings=settings,
            train_bars=100,
            test_bars=50,
            step_bars=25,
        )
        windows = optimizer._generate_windows(data)
        assert len(windows) > 0

        train_data, test_data = windows[0]
        assert len(train_data["SPY"]) == 100
        assert len(test_data["SPY"]) == 50

    def test_insufficient_data(self):
        df = pd.DataFrame({
            "datetime": pd.date_range("2023-01-01", periods=50, freq="D"),
            "open": np.random.randn(50).cumsum() + 400,
            "high": np.random.randn(50).cumsum() + 405,
            "low": np.random.randn(50).cumsum() + 395,
            "close": np.random.randn(50).cumsum() + 400,
            "volume": np.random.randint(1000, 5000, 50),
        })
        data = {"SPY": df}

        settings = BacktestSettings(data_provider=DataProviderType.CSV, symbols=["SPY"])
        optimizer = WalkForwardOptimizer(
            base_settings=settings,
            train_bars=100,
            test_bars=50,
            step_bars=25,
        )
        windows = optimizer._generate_windows(data)
        assert len(windows) == 0
