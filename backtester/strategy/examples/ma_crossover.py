"""
Moving Average Crossover Strategy

Classic trend-following strategy that generates signals when fast and slow
moving averages cross. Buys when fast MA crosses above slow MA, sells when
fast MA crosses below slow MA.
"""

from typing import List
import logging
import numpy as np

from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext

logger = logging.getLogger(__name__)


class MovingAverageCrossover(Strategy):
    """
    Moving Average Crossover Strategy - Classic trend following.

    This strategy:
    1. Calculates fast and slow moving averages for each symbol
    2. Generates BUY signal when fast MA crosses above slow MA (golden cross)
    3. Generates SELL signal when fast MA crosses below slow MA (death cross)
    4. Only trades when not already in a position (no pyramiding)

    Parameters:
        fast_period: Period for fast moving average (default: 10)
        slow_period: Period for slow moving average (default: 50)
        ma_type: Type of moving average ('SMA' or 'EMA', default: 'SMA')
        min_cross_strength: Minimum percentage difference for valid cross (default: 0.5%)

    Example:
        ```python
        # Create strategy with custom parameters
        strategy = MovingAverageCrossover(fast_period=20, slow_period=100)

        # Run backtest
        orchestrator = BacktestOrchestrator(strategies=[strategy])
        results = orchestrator.run(
            symbols=['SBIN', 'INFY', 'TCS'],
            start_date='2024-01-01',
            end_date='2024-12-31',
            interval=Interval.DAY
        )

        print(results.summary())
        ```
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 50,
        ma_type: str = 'SMA',
        min_cross_strength: float = 0.5
    ):
        """
        Initialize Moving Average Crossover strategy.

        Args:
            fast_period: Fast MA period
            slow_period: Slow MA period
            ma_type: Type of MA ('SMA' or 'EMA')
            min_cross_strength: Minimum cross percentage for signal
        """
        if fast_period >= slow_period:
            raise ValueError("Fast period must be less than slow period")

        if fast_period < 2 or slow_period < 2:
            raise ValueError("MA periods must be at least 2")

        super().__init__(
            name=f"MA_Cross_{fast_period}_{slow_period}",
            fast_period=fast_period,
            slow_period=slow_period,
            ma_type=ma_type.upper(),
            min_cross_strength=min_cross_strength
        )

        self.description = (
            f"Moving Average Crossover: {ma_type.upper()} "
            f"{fast_period}/{slow_period}"
        )

        # Track previous MAs to detect crossovers
        self._prev_fast_ma = {}
        self._prev_slow_ma = {}

    def init(self, context: StrategyContext):
        """Initialize strategy."""
        logger.info(
            f"Initialized {self.name}: {self.params['ma_type']} "
            f"{self.params['fast_period']}/{self.params['slow_period']}"
        )

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """
        Generate signals based on MA crossovers.

        Args:
            context: Strategy context

        Returns:
            List of signals
        """
        signals = []

        for symbol in context.symbols:
            # Get historical data (need slow_period + 1 for previous MA)
            hist = context.history(symbol, self.params['slow_period'] + 1)
            if hist is None or len(hist) < self.params['slow_period'] + 1:
                continue

            # Calculate moving averages
            fast_ma, slow_ma = self._calculate_mas(hist)
            if fast_ma is None or slow_ma is None:
                continue

            # Get previous MAs
            prev_fast = self._prev_fast_ma.get(symbol)
            prev_slow = self._prev_slow_ma.get(symbol)

            # Store current MAs for next bar
            self._prev_fast_ma[symbol] = fast_ma
            self._prev_slow_ma[symbol] = slow_ma

            # Skip if no previous values (first valid bar)
            if prev_fast is None or prev_slow is None:
                continue

            # Check for crossover
            signal = self._check_crossover(
                symbol=symbol,
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                prev_fast=prev_fast,
                prev_slow=prev_slow,
                context=context
            )

            if signal is not None:
                signals.append(signal)

        return signals

    def _calculate_mas(self, hist) -> tuple:
        """
        Calculate fast and slow moving averages.

        Args:
            hist: Historical window

        Returns:
            Tuple of (fast_ma, slow_ma) or (None, None) if insufficient data
        """
        closes = hist.get_closes()

        if len(closes) < self.params['slow_period']:
            return None, None

        # Calculate based on MA type
        if self.params['ma_type'] == 'SMA':
            # Simple Moving Average
            fast_ma = np.mean(closes[-self.params['fast_period']:])
            slow_ma = np.mean(closes[-self.params['slow_period']:])
        elif self.params['ma_type'] == 'EMA':
            # Exponential Moving Average
            fast_ma = self._calculate_ema(closes, self.params['fast_period'])
            slow_ma = self._calculate_ema(closes, self.params['slow_period'])
        else:
            logger.warning(f"Unknown MA type: {self.params['ma_type']}, using SMA")
            fast_ma = np.mean(closes[-self.params['fast_period']:])
            slow_ma = np.mean(closes[-self.params['slow_period']:])

        return float(fast_ma), float(slow_ma)

    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """
        Calculate exponential moving average.

        Args:
            prices: Price array
            period: EMA period

        Returns:
            EMA value
        """
        multiplier = 2.0 / (period + 1)
        ema = prices[0]  # Start with first price

        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return float(ema)

    def _check_crossover(
        self,
        symbol: str,
        fast_ma: float,
        slow_ma: float,
        prev_fast: float,
        prev_slow: float,
        context: StrategyContext
    ) -> Signal | None:
        """
        Check for MA crossover and generate signal.

        Args:
            symbol: Trading symbol
            fast_ma: Current fast MA
            slow_ma: Current slow MA
            prev_fast: Previous fast MA
            prev_slow: Previous slow MA
            context: Strategy context

        Returns:
            Signal or None
        """
        # Calculate crossover strength (percentage difference)
        cross_strength = abs(fast_ma - slow_ma) / slow_ma * 100

        # Check minimum cross strength
        if cross_strength < self.params['min_cross_strength']:
            return None

        # Check for golden cross (bullish)
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            # Only buy if not already holding
            if not context.has_position(symbol):
                return Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=min(cross_strength / 5.0, 1.0),  # Normalize to 0-1
                    confidence=0.7,
                    metadata={
                        'strategy': 'ma_crossover',
                        'signal_type': 'golden_cross',
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'cross_strength': cross_strength
                    }
                )

        # Check for death cross (bearish)
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            # Only sell if holding position
            if context.has_position(symbol):
                position = context.position(symbol)
                return Signal(
                    symbol=symbol,
                    direction=SignalDirection.CLOSE,
                    timestamp=context.current_time,
                    strength=min(cross_strength / 5.0, 1.0),
                    confidence=0.7,
                    quantity=abs(position.quantity),
                    metadata={
                        'strategy': 'ma_crossover',
                        'signal_type': 'death_cross',
                        'fast_ma': fast_ma,
                        'slow_ma': slow_ma,
                        'cross_strength': cross_strength
                    }
                )

        return None

    def __str__(self) -> str:
        """String representation"""
        return (
            f"MovingAverageCrossover("
            f"{self.params['ma_type']} "
            f"{self.params['fast_period']}/{self.params['slow_period']})"
        )
