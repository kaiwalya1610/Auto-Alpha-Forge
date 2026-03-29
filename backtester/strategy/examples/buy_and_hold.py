"""
Buy and Hold Strategy

Simple benchmark strategy that buys all symbols at the start and holds them
until the end. Useful for benchmarking other strategies against passive investment.
"""

from typing import List
import logging

from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext

logger = logging.getLogger(__name__)


class BuyAndHold(Strategy):
    """
    Buy and Hold Strategy - Benchmark for passive investing.

    This strategy:
    1. Buys equal amounts of all symbols on the first bar
    2. Holds positions until the end
    3. Sells everything on the last bar

    Parameters:
        position_pct: Percentage of portfolio to invest per symbol (default: 0.95 / num_symbols)
        sell_at_end: Whether to sell all positions on last bar (default: False)

    Example:
        ```python
        # Create strategy
        strategy = BuyAndHold(position_pct=0.1)

        # Run backtest
        orchestrator = BacktestOrchestrator(strategies=[strategy])
        results = orchestrator.run(
            symbols=['SBIN', 'INFY', 'TCS'],
            start_date='2024-01-01',
            end_date='2024-12-31',
            interval=Interval.DAY
        )
        ```
    """

    def __init__(self, position_pct: float = None, sell_at_end: bool = False):
        """
        Initialize Buy and Hold strategy.

        Args:
            position_pct: Percentage of portfolio per symbol (auto-calculated if None)
            sell_at_end: Whether to close all positions on last bar
        """
        super().__init__(
            name="BuyAndHold",
            position_pct=position_pct,
            sell_at_end=sell_at_end
        )
        self.description = "Simple buy and hold benchmark strategy"
        self._bought = False

    def init(self, context: StrategyContext):
        """Initialize strategy."""
        num_symbols = len(context.symbols)

        # Auto-calculate position percentage if not provided
        if self.params['position_pct'] is None:
            # Invest 95% of capital, divided equally
            self.params['position_pct'] = 0.95 / num_symbols

        logger.info(
            f"Initialized {self.name}: {num_symbols} symbols, "
            f"{self.params['position_pct']*100:.1f}% per symbol"
        )

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """
        Generate signals: Buy on first bar, hold, optionally sell at end.

        Args:
            context: Strategy context

        Returns:
            List of signals
        """
        signals = []

        # Buy on first bar
        if not self._bought and context.bar_index == 0:
            for symbol in context.symbols:
                # Check if we have price data
                price = context.current_price(symbol)
                if price is None:
                    continue

                # Calculate quantity based on position percentage
                portfolio_val = context.portfolio_value()
                position_value = portfolio_val * self.params['position_pct']
                quantity = int(position_value / price)

                if quantity > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=SignalDirection.BUY,
                        timestamp=context.current_time,
                        strength=1.0,
                        confidence=1.0,
                        quantity=quantity,
                        metadata={'strategy': 'buy_and_hold', 'action': 'initial_buy'}
                    ))

            self._bought = True
            logger.info(f"Generated {len(signals)} buy signals")

        # Optionally sell at end if this is the last bar
        if self.params.get('sell_at_end', False) and context.is_last_bar:
            # Close all positions on the last bar
            for symbol in context.symbols:
                if context.has_position(symbol):
                    position = context.position(symbol)
                    if position is not None:
                        signals.append(Signal(
                            symbol=symbol,
                            direction=SignalDirection.CLOSE,
                            timestamp=context.current_time,
                            strength=1.0,
                            confidence=1.0,
                            quantity=abs(position.quantity),  # Close entire position
                            metadata={'strategy': 'buy_and_hold', 'action': 'sell_at_end'}
                        ))
            
            if signals:
                logger.info(f"Generated {len(signals)} sell signals at end of backtest")

        return signals

    def __str__(self) -> str:
        """String representation"""
        return f"BuyAndHold(position_pct={self.params['position_pct']:.2%})"
