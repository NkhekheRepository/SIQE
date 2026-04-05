#!/usr/bin/env python3
"""
SIQE V3 Binance Futures Backtest Runner
========================================
Fetches historical data from Binance Futures testnet, runs backtests,
and generates comprehensive reports.

Usage:
    python scripts/run_binance_backtest.py                    # Default: 1 year 15m
    python scripts/run_binance_backtest.py --timeframe 4h    # 4h timeframe
    python scripts/run_binance_backtest.py --days 180         # 6 months
    python scripts/run_binance_backtest.py --walk-forward     # Walk-forward analysis
    python scripts/run_binance_backtest.py --symbol ETHUSDT    # Different symbol
"""
import argparse
import asyncio
import logging
import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from backtest.config import BacktestSettings, DataProviderType, SlippageModelType, LearningMode
from backtest.engine import BacktestEngine
from backtest.walk_forward import WalkForwardOptimizer
from backtest.report import ReportGenerator
from backtest.data_provider import CCXTProvider, ParquetProvider
from config.settings import Settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """Fetches and caches Binance Futures historical data."""
    
    BASE_URL = "https://data.binance.vision/data/futures/um"

    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
    }

    def __init__(self, data_dir: str = "./data/binance_futures"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "parquet"
        self.cache_dir.mkdir(exist_ok=True)

    def fetch_binance_futures(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        start_str: Optional[str] = None,
        end_str: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch Binance USDT-M Futures klines via public API.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1m', '5m', '15m', '1h', '4h')
            start_str: Start date string (e.g., '2023-01-01')
            end_str: End date string (e.g., '2024-01-01')
            use_cache: Use cached parquet files if available
        """
        import ccxt
        
        symbol = symbol.upper()
        interval = self.TIMEFRAME_MAP.get(interval, "15m")
        
        cache_file = self.cache_dir / f"{symbol.lower()}_{interval}.parquet"
        
        if use_cache and cache_file.exists():
            logger.info(f"Loading cached data from {cache_file}")
            df = pd.read_parquet(cache_file)
            # Convert datetime column to datetime type for comparison
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
            if start_str:
                start_date = pd.to_datetime(start_str)
                df = df[df['datetime'] >= start_date]
            if end_str:
                end_date = pd.to_datetime(end_str)
                df = df[df['datetime'] <= end_date]
            return df
        
        logger.info(f"Fetching {symbol} {interval} from Binance Futures API")
        
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        })
        
        start_time = None
        end_time = None
        
        if start_str:
            start_time = int(pd.Timestamp(start_str).timestamp() * 1000)
        if end_str:
            end_time = int(pd.Timestamp(end_str).timestamp() * 1000)
        
        all_klines = []
        current_start = start_time
        max_total_bars = 50000
        consecutive_empty = 0
        
        while len(all_klines) < max_total_bars:
            try:
                klines = exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=interval,
                    since=current_start,
                    limit=1500,
                )
                
                if not klines:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info("No data in 3 consecutive requests, stopping")
                        break
                    time.sleep(1)
                    continue
                
                consecutive_empty = 0
                all_klines.extend(klines)
                last_ts = klines[-1][0]
                
                logger.info(f"Total: {len(all_klines)} bars up to {pd.to_datetime(last_ts, unit='ms')}")
                
                if end_time and last_ts >= end_time:
                    logger.info(f"Reached end date")
                    break
                
                current_start = last_ts + 1
                
            except Exception as e:
                logger.warning(f"Rate limit or error ({e}), waiting...")
                time.sleep(2)
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                continue
        
        if not all_klines:
            raise ValueError(f"No data fetched for {symbol} {interval}")
        
        df = pd.DataFrame(
            all_klines,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['datetime'] = df['datetime'].dt.tz_localize(None)
        
        if end_time:
            df = df[df['timestamp'] <= end_time]
        
        df = df.drop(columns=['timestamp'])
        df = df.reset_index(drop=True)
        
        logger.info(f"Fetched {len(df)} bars: {df['datetime'].min()} to {df['datetime'].max()}")
        
        df.to_parquet(cache_file, index=False)
        logger.info(f"Cached to {cache_file}")
        
        return df

    def get_multi_timeframe(
        self,
        symbol: str = "BTCUSDT",
        primary_interval: str = "15m",
        confirmation_interval: str = "4h",
        start_str: Optional[str] = None,
        end_str: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch data at multiple timeframes for multi-timeframe analysis."""
        data = {}
        
        data[primary_interval] = self.fetch_binance_futures(
            symbol=symbol,
            interval=primary_interval,
            start_str=start_str,
            end_str=end_str,
        )
        
        if confirmation_interval != primary_interval:
            data[confirmation_interval] = self.fetch_binance_futures(
                symbol=symbol,
                interval=confirmation_interval,
                start_str=start_str,
                end_str=end_str,
            )
        
        return data


class BacktestRunner:
    """Orchestrates backtest execution with Binance Futures data."""

    def __init__(self, settings: Settings = None):
        self.settings = settings if settings is not None else Settings()
        self.settings.use_mock_execution = True
        self.settings.vnpy_gateway = "BINANCE"
        self.settings.min_ev_threshold = 0.0
        self.settings.max_position_size = 0.15
        self.settings.max_drawdown = 0.15
        self.settings.max_daily_loss = 0.05
        self.settings.leverage = 35
        self.settings.stop_multiplier = 1.5
        self.settings.tp_multiplier = 2.5
        self.settings.max_bars_held = 8
        self.fetcher = BinanceDataFetcher()
        self.report_gen = ReportGenerator(output_dir="./backtest_output/binance_futures")

    def run_single_backtest(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        start_date: str = None,
        end_date: str = None,
        initial_equity: float = 10000,
        learning_mode: LearningMode = LearningMode.FIXED,
        use_binance_api: bool = True,
        fetch_confirmation_tf: bool = False,
    ) -> Dict[str, Any]:
        """
        Run a single backtest with Binance Futures data.
        
        Returns:
            Dict with 'result', 'report_paths', 'data_info'
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        logger.info(f"=" * 60)
        logger.info(f"BACKTEST: {symbol} {interval}")
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Initial Equity: ${initial_equity:,.2f}")
        logger.info(f"Learning: {learning_mode.value}")
        logger.info(f"=" * 60)
        
        if use_binance_api:
            df = self.fetcher.fetch_binance_futures(
                symbol=symbol,
                interval=interval,
                start_str=start_date,
                end_str=end_date,
            )
            data_source = DataProviderType.PARQUET
        else:
            df = None
            data_source = DataProviderType.CCXT
        
        bt_settings = BacktestSettings(
            data_provider=data_source,
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            timeframe=interval,
            initial_equity=initial_equity,
            slippage_model=SlippageModelType.LINEAR,
            slippage_bps=5.0,
            learning_mode=learning_mode,
            learning_interval=25,
            rng_seed=42,
            output_dir=str(self.report_gen.output_dir),
            ccxt_exchange="binance",
            ccxt_market_type="future",
            parquet_path=str(self.fetcher.cache_dir) if df is not None else None,
            max_bars=0,
        )
        
        if df is not None:
            from core.clock import EventClock
            from backtest.data_provider import CSVProvider
            from backtest.enhanced_engine import EnhancedBacktestEngine
            
            clock = EventClock()
            
            df_dict = {symbol: df}
            bt_settings.parquet_path = str(self.fetcher.cache_dir)
            
            engine = EnhancedBacktestEngine(bt_settings, self.settings)
            
            from backtest.engine import BacktestEngine
            base_engine = BacktestEngine(bt_settings, self.settings)
            components = base_engine._init_components()
            
            logger.info(f"Running enhanced backtest with: leverage={engine.leverage}x, "
                       f"stop={engine.stop_multiplier}x ATR, tp={engine.tp_multiplier}x ATR, "
                       f"max_bars={engine.max_bars}")
            
            result = engine.run(df_dict, components)
        else:
            engine = BacktestEngine(bt_settings, self.settings)
            result = engine.run()
        
        logger.info(f"Backtest complete: {result.metrics.total_trades} trades, "
                   f"return={result.metrics.total_return_pct:.2f}%, "
                   f"Sharpe={result.metrics.sharpe_ratio:.3f}")
        
        report_paths = self.report_gen.generate(result)
        
        return {
            'result': result,
            'report_paths': report_paths,
            'data_info': {
                'symbol': symbol,
                'interval': interval,
                'start_date': start_date,
                'end_date': end_date,
                'bars': result.bars_analyzed,
                'source': 'binance_futures',
            }
        }

    def run_walk_forward(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        start_date: str = None,
        end_date: str = None,
        train_bars: int = 2000,
        test_bars: int = 500,
        step_bars: int = 100,
    ) -> Dict[str, Any]:
        """Run walk-forward analysis for parameter stability validation."""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        
        logger.info(f"=" * 60)
        logger.info(f"WALK-FORWARD ANALYSIS: {symbol} {interval}")
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Train: {train_bars} bars, Test: {test_bars} bars, Step: {step_bars} bars")
        logger.info(f"=" * 60)
        
        df = self.fetcher.fetch_binance_futures(
            symbol=symbol,
            interval=interval,
            start_str=start_date,
            end_str=end_date,
        )
        
        base_settings = BacktestSettings(
            data_provider=DataProviderType.PARQUET,
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            timeframe=interval,
            initial_equity=10000,
            slippage_model=SlippageModelType.LINEAR,
            slippage_bps=5.0,
            learning_mode=LearningMode.ADAPTIVE,
            learning_interval=25,
            rng_seed=42,
            parquet_path=str(self.fetcher.cache_dir),
        )
        
        optimizer = WalkForwardOptimizer(
            base_settings=base_settings,
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
        )
        
        summary = optimizer.run()
        
        logger.info(f"Walk-forward complete: {summary.total_windows} windows, "
                   f"avg test Sharpe={summary.avg_test_sharpe:.3f}, "
                   f"avg overfit={summary.avg_overfit_ratio:.1%}")
        
        wf_summary_dict = {
            'avg_test_sharpe': summary.avg_test_sharpe,
            'avg_test_return': summary.avg_test_return,
            'avg_overfit_ratio': summary.avg_overfit_ratio,
            'consistent_windows': summary.consistent_windows,
            'total_windows': summary.total_windows,
            'windows': [
                {
                    'window_id': w.window_id,
                    'train_sharpe': w.train_result.metrics.sharpe_ratio if w.train_result else None,
                    'test_sharpe': w.test_result.metrics.sharpe_ratio if w.test_result else None,
                    'overfit_ratio': w.overfit_ratio,
                }
                for w in summary.windows
            ]
        }
        
        output_file = self.report_gen.output_dir / f"walk_forward_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(wf_summary_dict, f, indent=2, default=str)
        
        return {
            'summary': summary,
            'output_file': str(output_file),
            'data_info': {
                'symbol': symbol,
                'interval': interval,
                'start_date': start_date,
                'end_date': end_date,
                'train_bars': train_bars,
                'test_bars': test_bars,
            }
        }

    def run_regime_analysis(
        self,
        symbol: str = "BTCUSDT",
        intervals: list = None,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict[str, Any]:
        """Analyze market regimes across different timeframes."""
        if intervals is None:
            intervals = ["15m", "1h", "4h", "1d"]
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        logger.info(f"=" * 60)
        logger.info(f"REGIME ANALYSIS: {symbol}")
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Timeframes: {intervals}")
        logger.info(f"=" * 60)
        
        from regime.regime_engine import RegimeEngine
        from core.clock import EventClock
        
        regime_stats = {}
        
        for interval in intervals:
            logger.info(f"Analyzing {interval} timeframe...")
            
            df = self.fetcher.fetch_binance_futures(
                symbol=symbol,
                interval=interval,
                start_str=start_date,
                end_str=end_date,
            )
            
            settings_copy = Settings()
            clock = EventClock()
            regime_engine = RegimeEngine(settings_copy, clock)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(regime_engine.initialize())
            
            regimes = []
            for _, row in df.iterrows():
                event = type('Event', (), {
                    'symbol': symbol,
                    'bid': row['close'] * 0.9999,
                    'ask': row['close'] * 1.0001,
                    'volume': row['volume'],
                    'volatility': (row['high'] - row['low']) / row['low'] if row['low'] > 0 else 0,
                    'event_seq': 0,
                })()
                
                regime = loop.run_until_complete(regime_engine.detect_regime(event))
                regimes.append(regime.regime.value if hasattr(regime.regime, 'value') else str(regime.regime))
            
            regime_counts = pd.Series(regimes).value_counts()
            regime_pct = (regime_counts / len(regimes) * 100).to_dict()
            
            regime_stats[interval] = {
                'total_bars': len(df),
                'regime_distribution': regime_pct,
                'most_common': max(regime_pct, key=regime_pct.get),
            }
            
            logger.info(f"  {interval}: {regime_pct}")
        
        return {
            'regime_stats': regime_stats,
            'symbol': symbol,
            'period': f"{start_date} to {end_date}",
        }


def parse_args():
    parser = argparse.ArgumentParser(description='SIQE V3 Binance Futures Backtest Runner')
    
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair')
    parser.add_argument('--interval', type=str, default='15m', 
                       choices=['1m', '5m', '15m', '30m', '1h', '4h', '6h', '8h', '12h', '1d'],
                       help='Timeframe')
    parser.add_argument('--days', type=int, default=365, help='Days of historical data')
    parser.add_argument('--start-date', type=str, default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--equity', type=float, default=10000, help='Initial equity')
    parser.add_argument('--mode', type=str, default='fixed', choices=['fixed', 'adaptive'],
                       help='Learning mode')
    
    parser.add_argument('--walk-forward', action='store_true', help='Run walk-forward analysis')
    parser.add_argument('--regime-analysis', action='store_true', help='Run regime analysis')
    parser.add_argument('--train-bars', type=int, default=2000, help='Walk-forward train bars')
    parser.add_argument('--test-bars', type=int, default=500, help='Walk-forward test bars')
    parser.add_argument('--step-bars', type=int, default=100, help='Walk-forward step')
    
    parser.add_argument('--no-cache', action='store_true', help='Force fresh data fetch')
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory')
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    settings = Settings()
    
    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"./backtest_output/binance_futures/{args.symbol}_{args.interval}_{timestamp}"
    
    runner = BacktestRunner(settings)
    
    if args.no_cache:
        runner.fetcher.cache_dir = runner.fetcher.cache_dir / f"fresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        runner.fetcher.cache_dir.mkdir(exist_ok=True)
    
    if args.regime_analysis:
        result = runner.run_regime_analysis(
            symbol=args.symbol,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        output_file = Path(output_dir) / "regime_analysis.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Regime analysis saved to {output_file}")
        return
    
    if args.walk_forward:
        result = runner.run_walk_forward(
            symbol=args.symbol,
            interval=args.interval,
            start_date=args.start_date,
            end_date=args.end_date,
            train_bars=args.train_bars,
            test_bars=args.test_bars,
            step_bars=args.step_bars,
        )
        logger.info(f"Walk-forward results saved to {result['output_file']}")
        return
    
    start_date = args.start_date
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    
    end_date = args.end_date
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    learning_mode = LearningMode.ADAPTIVE if args.mode == 'adaptive' else LearningMode.FIXED
    
    result = runner.run_single_backtest(
        symbol=args.symbol,
        interval=args.interval,
        start_date=start_date,
        end_date=end_date,
        initial_equity=args.equity,
        learning_mode=learning_mode,
    )
    
    logger.info(f"Results:")
    logger.info(f"  Total Trades: {result['result'].metrics.total_trades}")
    logger.info(f"  Total Return: {result['result'].metrics.total_return_pct:.2f}%")
    logger.info(f"  Sharpe Ratio: {result['result'].metrics.sharpe_ratio:.3f}")
    logger.info(f"  Max Drawdown: {result['result'].metrics.max_drawdown:.2%}")
    logger.info(f"  Win Rate: {result['result'].metrics.win_rate:.1%}")
    logger.info(f"  Reports: {result['report_paths']}")


if __name__ == "__main__":
    main()
