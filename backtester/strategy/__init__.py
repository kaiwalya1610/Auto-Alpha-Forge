"""
Strategy Package

Contains strategy implementations and signal generation for backtesting framework.
"""

from backtester.strategy.signal import Signal, SignalDirection
from backtester.strategy.market_data import MarketData
from backtester.strategy.position_info import PositionInfo
from backtester.strategy.portfolio_snapshot import PortfolioSnapshot
from backtester.strategy.historical_window import HistoricalWindow
from backtester.strategy.strategy_context import StrategyContext
from backtester.strategy.base_strategy import Strategy

__all__ = [
    'Signal',
    'SignalDirection',
    'MarketData',
    'PositionInfo',
    'PortfolioSnapshot',
    'HistoricalWindow',
    'StrategyContext',
    'Strategy',
]
