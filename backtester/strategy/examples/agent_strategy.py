"""
Agent Strategy — Iteration 2
Thesis: 20-day momentum filtered by 50-day trend reduces whipsaw by only buying in uptrends.
Mechanism: Long only when price > 50 SMA (trend up) AND 20-day return > threshold.
"""

from typing import List
import numpy as np
from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext


class AgentStrategy(Strategy):
    """Momentum + trend filter: buy momentum in confirmed uptrends only."""

    def __init__(self):
        super().__init__(name="AgentStrategy")
        self.momentum_period = 20   # lookback for momentum signal
        self.trend_period = 50      # SMA period for trend filter
        self.threshold = 0.02       # minimum 2% momentum to trigger

    def init(self, context: StrategyContext):
        pass

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        signals = []

        for symbol in context.symbols:
            if not context.has_data(symbol, self.trend_period + 1):
                continue

            hist = context.history(symbol, self.trend_period + 1)
            if hist is None:
                continue

            closes = hist.get_closes()
            current_price = closes[-1]
            trend_sma = np.mean(closes[-self.trend_period:])
            past_price = closes[-self.momentum_period - 1]
            momentum = (current_price - past_price) / past_price

            has_pos = context.has_position(symbol)
            in_uptrend = current_price > trend_sma

            if momentum > self.threshold and in_uptrend and not has_pos:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=min(momentum * 5, 1.0),
                    confidence=0.7,
                ))
            elif has_pos and (not in_uptrend or momentum < -self.threshold):
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
