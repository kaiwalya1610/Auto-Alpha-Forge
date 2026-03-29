"""
Agent Strategy — Iteration 3
Thesis: Mean reversion in large-caps — buy dips below SMA, sell when price reverts to mean.
Mechanism: Prices overshoot to downside temporarily; buying oversold conditions captures the snap-back.
"""

from typing import List
import numpy as np
from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext


class AgentStrategy(Strategy):
    """Mean reversion: buy when price dips below SMA, close when it reverts."""

    def __init__(self):
        super().__init__(name="AgentStrategy")
        self.sma_period = 20        # SMA period for mean
        self.entry_deviation = 0.03  # buy when price is 3% below SMA
        self.exit_deviation = 0.0    # close when price returns to SMA

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

            # Buy when price drops significantly below SMA
            if deviation < -self.entry_deviation and not has_pos:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=min(abs(deviation) * 10, 1.0),
                    confidence=0.7,
                ))
            # Close when price reverts back to SMA
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
