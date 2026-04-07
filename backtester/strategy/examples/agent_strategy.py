"""
Agent Strategy — Iteration 7
Thesis: Take profit at 1% above SMA instead of at SMA captures extra upside per trade.
Mechanism: Same mean reversion entry (3% below SMA), but hold until price overshoots SMA by 1%.
"""

from typing import List
import numpy as np
from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext


class AgentStrategy(Strategy):
    """Mean reversion: buy 3% below SMA, take profit 1% above SMA."""

    def __init__(self):
        super().__init__(name="AgentStrategy")
        self.sma_period = 20        # SMA period for mean
        self.entry_deviation = 0.03  # buy when price is 3% below SMA
        self.exit_deviation = 0.01   # close when price is 1% above SMA

    def init(self, context: StrategyContext):
        pass

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        signals = []

        for symbol in context.symbols:
            if not context.has_data(symbol, self.sma_period):
                continue

            sma = context.simple_moving_average(symbol, self.sma_period)
            price = context.current_price(symbol)
            if sma is None or price is None or sma == 0:
                continue

            deviation = (price - sma) / sma
            has_pos = context.has_position(symbol)

            if deviation < -self.entry_deviation and not has_pos:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=min(abs(deviation) * 10, 1.0),
                    confidence=0.7,
                ))
            elif deviation > self.exit_deviation and has_pos:
                pos = context.position(symbol)
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.CLOSE,
                    timestamp=context.current_time,
                    strength=1.0,
                    confidence=0.8,
                    quantity=abs(pos.quantity),
                ))

        return signals
