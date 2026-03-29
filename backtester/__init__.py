"""
Backtester Package

A comprehensive backtesting framework for algorithmic trading strategies.
"""

# Data loading components
from backtester.data_loader import DataOrchestrator, PyZData, Interval

# Strategy and signal components
from backtester.strategy import (
    Signal,
    SignalDirection,
    MarketData,
    PositionInfo,
    PortfolioSnapshot,
    HistoricalWindow,
    StrategyContext,
    Strategy
)

# Orchestrator and configuration
from backtester.backtest_orchestrator import BacktestOrchestrator
from backtester.config import BacktestConfig
from backtester.results import BacktestResults

__all__ = [
    # Data loader
    'DataOrchestrator',
    'PyZData',
    'Interval',
    # Strategy and signals
    'Signal',
    'SignalDirection',
    # Strategy context
    'MarketData',
    'PositionInfo',
    'PortfolioSnapshot',
    'HistoricalWindow',
    'StrategyContext',
    'Strategy',
    # Orchestrator
    'BacktestOrchestrator',
    'BacktestConfig',
    'BacktestResults',
]
