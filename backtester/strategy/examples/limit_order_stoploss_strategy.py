"""
Limit Order and Stop-Loss Strategy Example

This strategy demonstrates the use of:
1. Limit orders (buy when price drops to specific level)
2. Stop-loss orders (automatic exit when price falls below threshold)
3. Target exits (automatic exit when price reaches profit target)
4. Market orders with stop-loss and targets

This is primarily a demonstration/testing strategy, not a production strategy.
"""

from typing import List
from backtester.strategy.base_strategy import Strategy
from backtester.strategy.strategy_context import StrategyContext
from backtester.strategy.signal import Signal, SignalDirection


class LimitOrderStopLossStrategy(Strategy):
    """
    Strategy to test limit orders, stop-loss, and target exits.

    Behavior:
    - Places a LIMIT buy order 2% below current price on bar 10
    - Places a MARKET buy order with stop-loss and target on bar 30
    - Monitors positions and logs exit events

    Parameters:
        limit_order_pct: Percentage below current price to set limit buy (default: 0.98 = 2% below)
        stop_loss_pct: Percentage below entry for stop-loss (default: 0.95 = 5% stop)
        target_pct: Percentage above entry for target (default: 1.10 = 10% gain)
    """

    def __init__(
        self,
        name: str = None,
        limit_order_pct: float = 0.98,
        stop_loss_pct: float = 0.95,
        target_pct: float = 1.10
    ):
        super().__init__(name=name or "LimitOrderStopLoss")
        self.limit_order_pct = limit_order_pct
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct

        # Track what we've done
        self.limit_order_placed = {}
        self.market_order_placed = {}
        self.exit_detected = {}

    def init(self, context: StrategyContext):
        """Initialize strategy."""
        self.limit_order_placed = {symbol: False for symbol in context.symbols}
        self.market_order_placed = {symbol: False for symbol in context.symbols}
        self.exit_detected = {symbol: False for symbol in context.symbols}

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """Generate signals based on bar index."""
        signals = []

        # Work with first symbol only for simplicity
        if not context.symbols:
            return signals

        symbol = context.symbols[0]
        bar = context.current_bar(symbol)

        if bar is None:
            return signals

        current_price = bar.close
        position = context.position(symbol)

        # Test 1: Place LIMIT order at bar 10
        if context.bar_index == 10 and not self.limit_order_placed[symbol] and position is None:
            limit_price = current_price * self.limit_order_pct
            stop_loss = limit_price * self.stop_loss_pct
            target = limit_price * self.target_pct

            signals.append(Signal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                timestamp=context.current_time,
                strength=1.0,
                confidence=1.0,
                order_type='LIMIT',
                limit_price=limit_price,
                stop_loss=stop_loss,
                target_price=target,
                reasoning=f"LIMIT buy @ Rs {limit_price:.2f} (stop: Rs {stop_loss:.2f}, target: Rs {target:.2f})",
                metadata={
                    'test': 'limit_order',
                    'limit_price': limit_price,
                    'stop_loss': stop_loss,
                    'target_price': target
                }
            ))
            self.limit_order_placed[symbol] = True

        # Test 2: Place MARKET order with stop-loss and target at bar 30
        elif context.bar_index == 30 and not self.market_order_placed[symbol] and position is None:
            stop_loss = current_price * self.stop_loss_pct
            target = current_price * self.target_pct

            signals.append(Signal(
                symbol=symbol,
                direction=SignalDirection.BUY,
                timestamp=context.current_time,
                strength=1.0,
                confidence=1.0,
                order_type='MARKET',
                stop_loss=stop_loss,
                target_price=target,
                reasoning=f"MARKET buy @ Rs {current_price:.2f} (stop: Rs {stop_loss:.2f}, target: Rs {target:.2f})",
                metadata={
                    'test': 'market_order_with_exits',
                    'entry_price': current_price,
                    'stop_loss': stop_loss,
                    'target_price': target
                }
            ))
            self.market_order_placed[symbol] = True

        # Monitor position status (detect exits)
        if position is not None and not self.exit_detected[symbol]:
            # Position exists, keep tracking
            pass
        elif position is None and (self.limit_order_placed[symbol] or self.market_order_placed[symbol]) and not self.exit_detected[symbol]:
            # Position was closed (exit occurred)
            self.exit_detected[symbol] = True

        return signals
