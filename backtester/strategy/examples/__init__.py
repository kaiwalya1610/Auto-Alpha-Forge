"""
Example Strategies

This package contains reference implementations of common trading strategies
to demonstrate the backtesting framework's capabilities.
"""

from backtester.strategy.examples.ma_crossover import MovingAverageCrossover
from backtester.strategy.examples.buy_and_hold import BuyAndHold
from backtester.strategy.examples.limit_order_stoploss_strategy import LimitOrderStopLossStrategy
from backtester.strategy.examples.mtf_trend_following import MTFTrendFollowing, MTFMomentum

__all__ = [
    'MovingAverageCrossover',
    'BuyAndHold',
    'LimitOrderStopLossStrategy',
    'MTFTrendFollowing',
    'MTFMomentum',
]
