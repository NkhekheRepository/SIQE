"""
SIQE V3 Backtesting Engine
Deterministic historical replay with free market data (yfinance, CCXT).
"""
from backtest.config import BacktestSettings
from backtest.data_provider import HistoricalDataProvider, DataProviderType
from backtest.slippage_model import SlippageModel, FixedBPSSlippage, LinearSlippage, VolumeImpactSlippage
from backtest.performance import PerformanceAnalyzer
from backtest.engine import BacktestEngine, BacktestResult
from backtest.walk_forward import WalkForwardOptimizer
from backtest.report import ReportGenerator

__all__ = [
    "BacktestSettings",
    "HistoricalDataProvider",
    "DataProviderType",
    "SlippageModel",
    "FixedBPSSlippage",
    "LinearSlippage",
    "VolumeImpactSlippage",
    "PerformanceAnalyzer",
    "BacktestEngine",
    "BacktestResult",
    "WalkForwardOptimizer",
    "ReportGenerator",
]
