"""
Multi-Timeframe Trend Following Strategy

A strategy that combines signals from multiple timeframes:
- Higher timeframe (e.g., Daily) for trend direction
- Lower timeframe (e.g., 15-min) for entry timing

This demonstrates how to use the multi-timeframe data access feature
in the backtesting engine.
"""

from typing import List
import logging
import numpy as np

from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext
from backtester.data_loader import Interval

logger = logging.getLogger(__name__)


class MTFTrendFollowing(Strategy):
    """
    Multi-Timeframe Trend Following Strategy.

    This strategy uses a higher timeframe to determine trend direction
    and a lower timeframe for precise entry timing. Only takes trades
    in the direction of the higher timeframe trend.

    Logic:
    1. Calculate SMA on higher timeframe (e.g., Daily) for trend bias
    2. Calculate fast/slow SMA on primary timeframe for entry signals
    3. Only BUY when:
       - Higher TF price > Higher TF SMA (uptrend)
       - Primary TF fast MA crosses above slow MA
    4. Only SELL/CLOSE when:
       - Higher TF price < Higher TF SMA (downtrend) OR
       - Primary TF fast MA crosses below slow MA

    Parameters:
        htf_period: Higher timeframe SMA period (default: 20)
        ltf_fast_period: Primary timeframe fast SMA period (default: 5)
        ltf_slow_period: Primary timeframe slow SMA period (default: 15)
        higher_timeframe: The higher timeframe to use for trend (default: DAY)

    Example:
        ```python
        from backtester.data_loader import Interval

        # Create MTF strategy - uses 15-min bars with daily trend filter
        strategy = MTFTrendFollowing(
            htf_period=20,
            ltf_fast_period=5,
            ltf_slow_period=15,
            higher_timeframe=Interval.DAY
        )

        # Configure and run backtest
        config = BacktestConfig(initial_capital=100000)
        orchestrator = BacktestOrchestrator([strategy], config)

        results = orchestrator.run(
            symbols=['SBIN', 'INFY'],
            start_date='2024-01-01',
            end_date='2024-06-30',
            interval=Interval.MINUTE_15,  # Primary timeframe
            exchange='NSE'
        )

        print(results.summary())
        ```
    """

    def __init__(
        self,
        htf_period: int = 20,
        ltf_fast_period: int = 5,
        ltf_slow_period: int = 15,
        higher_timeframe: Interval = Interval.DAY
    ):
        """
        Initialize Multi-Timeframe Trend Following strategy.

        Args:
            htf_period: Higher timeframe SMA period for trend
            ltf_fast_period: Primary timeframe fast SMA period
            ltf_slow_period: Primary timeframe slow SMA period
            higher_timeframe: The higher timeframe interval to use
        """
        if ltf_fast_period >= ltf_slow_period:
            raise ValueError("ltf_fast_period must be less than ltf_slow_period")

        # Declare required timeframes - the engine will load this data automatically
        super().__init__(
            name=f"MTF_Trend_{higher_timeframe.value}",
            timeframes=[higher_timeframe],  # Request higher timeframe data
            htf_period=htf_period,
            ltf_fast_period=ltf_fast_period,
            ltf_slow_period=ltf_slow_period,
            higher_timeframe=higher_timeframe.value
        )

        self._higher_timeframe = higher_timeframe

        self.description = (
            f"Multi-Timeframe Trend Following: "
            f"HTF {higher_timeframe.value} SMA({htf_period}), "
            f"LTF SMA({ltf_fast_period}/{ltf_slow_period})"
        )

        # Track previous MAs for crossover detection
        self._prev_ltf_fast_ma = {}
        self._prev_ltf_slow_ma = {}

    def init(self, context: StrategyContext):
        """Initialize strategy and validate data availability."""
        logger.info(f"Initializing {self.name}")

        # Log available intervals for each symbol
        for symbol in context.symbols:
            intervals = context.available_intervals(symbol)
            interval_str = ", ".join(i.value for i in intervals)
            logger.info(f"  {symbol}: available intervals [{interval_str}]")

            # Warn if higher timeframe not available
            if self._higher_timeframe not in intervals:
                logger.warning(
                    f"  WARNING: {symbol} missing {self._higher_timeframe.value} data. "
                    f"Trend filter will be disabled for this symbol."
                )

        logger.info(f"  Strategy ready. HTF trend filter: {self._higher_timeframe.value}")

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """
        Generate signals based on multi-timeframe analysis.

        Args:
            context: Strategy context with multi-timeframe data access

        Returns:
            List of trading signals
        """
        signals = []

        for symbol in context.symbols:
            signal = self._analyze_symbol(symbol, context)
            if signal is not None:
                signals.append(signal)

        return signals

    def _analyze_symbol(self, symbol: str, context: StrategyContext) -> Signal | None:
        """
        Analyze a single symbol using multi-timeframe data.

        Args:
            symbol: Trading symbol
            context: Strategy context

        Returns:
            Signal or None
        """
        # Step 1: Get higher timeframe trend bias
        htf_trend = self._get_htf_trend_bias(symbol, context)
        # htf_trend: 1 = uptrend, -1 = downtrend, 0 = neutral/unavailable

        # Step 2: Get primary timeframe data
        ltf_hist = context.history(symbol, self.params['ltf_slow_period'] + 1)
        if ltf_hist is None or len(ltf_hist) < self.params['ltf_slow_period'] + 1:
            return None

        # Step 3: Calculate primary timeframe MAs
        closes = ltf_hist.get_closes()
        ltf_fast_ma = float(np.mean(closes[-self.params['ltf_fast_period']:]))
        ltf_slow_ma = float(np.mean(closes[-self.params['ltf_slow_period']:]))

        # Get previous MAs
        prev_fast = self._prev_ltf_fast_ma.get(symbol)
        prev_slow = self._prev_ltf_slow_ma.get(symbol)

        # Store current for next bar
        self._prev_ltf_fast_ma[symbol] = ltf_fast_ma
        self._prev_ltf_slow_ma[symbol] = ltf_slow_ma

        # Skip if no previous values
        if prev_fast is None or prev_slow is None:
            return None

        # Step 4: Check for entry/exit signals
        current_price = context.current_price(symbol)
        has_position = context.has_position(symbol)

        # Golden cross on LTF
        if prev_fast <= prev_slow and ltf_fast_ma > ltf_slow_ma:
            # Only enter if trend is up or neutral (not down)
            if htf_trend >= 0 and not has_position:
                return Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=0.8 if htf_trend > 0 else 0.6,  # Stronger if with HTF trend
                    confidence=0.7,
                    metadata={
                        'strategy': 'mtf_trend_following',
                        'signal_type': 'buy',
                        'htf_trend': htf_trend,
                        'ltf_fast_ma': ltf_fast_ma,
                        'ltf_slow_ma': ltf_slow_ma,
                        'htf_interval': self._higher_timeframe.value
                    }
                )

        # Death cross on LTF OR HTF downtrend
        elif prev_fast >= prev_slow and ltf_fast_ma < ltf_slow_ma:
            # Exit on LTF death cross
            if has_position:
                position = context.position(symbol)
                return Signal(
                    symbol=symbol,
                    direction=SignalDirection.CLOSE,
                    timestamp=context.current_time,
                    strength=0.8,
                    confidence=0.7,
                    quantity=abs(position.quantity),
                    metadata={
                        'strategy': 'mtf_trend_following',
                        'signal_type': 'close',
                        'reason': 'ltf_death_cross',
                        'htf_trend': htf_trend,
                        'ltf_fast_ma': ltf_fast_ma,
                        'ltf_slow_ma': ltf_slow_ma
                    }
                )

        # Also exit if HTF trend turns negative (trend reversal)
        elif htf_trend < 0 and has_position:
            position = context.position(symbol)
            return Signal(
                symbol=symbol,
                direction=SignalDirection.CLOSE,
                timestamp=context.current_time,
                strength=0.9,
                confidence=0.8,
                quantity=abs(position.quantity),
                metadata={
                    'strategy': 'mtf_trend_following',
                    'signal_type': 'close',
                    'reason': 'htf_trend_reversal',
                    'htf_trend': htf_trend
                }
            )

        return None

    def _get_htf_trend_bias(self, symbol: str, context: StrategyContext) -> int:
        """
        Determine higher timeframe trend bias.

        Args:
            symbol: Trading symbol
            context: Strategy context

        Returns:
            1 for uptrend, -1 for downtrend, 0 for neutral/unavailable
        """
        # Check if HTF data is available
        available_intervals = context.available_intervals(symbol)
        if self._higher_timeframe not in available_intervals:
            return 0  # Neutral if HTF not available

        # Get higher timeframe history
        htf_hist = context.history(
            symbol,
            self.params['htf_period'] + 1,
            interval=self._higher_timeframe
        )

        if htf_hist is None or len(htf_hist) < self.params['htf_period']:
            return 0

        # Calculate HTF SMA
        htf_closes = htf_hist.get_closes()
        htf_sma = float(np.mean(htf_closes[-self.params['htf_period']:]))

        # Get current HTF price (most recent HTF bar)
        htf_bar = context.current_bar(symbol, interval=self._higher_timeframe)
        if htf_bar is None:
            return 0

        htf_price = htf_bar.close

        # Determine trend
        if htf_price > htf_sma * 1.001:  # 0.1% buffer
            return 1  # Uptrend
        elif htf_price < htf_sma * 0.999:  # 0.1% buffer
            return -1  # Downtrend
        else:
            return 0  # Neutral

    def __str__(self) -> str:
        """String representation"""
        return (
            f"MTFTrendFollowing("
            f"HTF={self._higher_timeframe.value} SMA{self.params['htf_period']}, "
            f"LTF SMA{self.params['ltf_fast_period']}/{self.params['ltf_slow_period']})"
        )


class MTFMomentum(Strategy):
    """
    Multi-Timeframe Momentum Strategy - Simpler version for demonstration.

    Uses daily trend direction combined with intraday momentum.

    Logic:
    - Enter LONG when daily trend is up AND intraday price breaks above N-bar high
    - Exit when daily trend reverses OR intraday price breaks below N-bar low

    This is a simpler MTF strategy that demonstrates:
    1. Declaring required timeframes in __init__
    2. Accessing higher timeframe data via context.history(interval=...)
    3. Combining multiple timeframe signals

    Example:
        ```python
        strategy = MTFMomentum(daily_ma_period=10, breakout_period=5)

        results = orchestrator.run(
            symbols=['SBIN'],
            start_date='2024-01-01',
            end_date='2024-03-31',
            interval=Interval.HOUR_1,  # Primary: hourly
            exchange='NSE'
        )
        ```
    """

    def __init__(
        self,
        daily_ma_period: int = 10,
        breakout_period: int = 5
    ):
        """
        Initialize MTF Momentum strategy.

        Args:
            daily_ma_period: Daily SMA period for trend
            breakout_period: Primary timeframe breakout lookback
        """
        super().__init__(
            name="MTF_Momentum",
            timeframes=[Interval.DAY],  # Always need daily data
            daily_ma_period=daily_ma_period,
            breakout_period=breakout_period
        )

        self.description = (
            f"MTF Momentum: Daily SMA({daily_ma_period}), "
            f"Breakout({breakout_period})"
        )

    def init(self, context: StrategyContext):
        """Initialize strategy."""
        logger.info(f"Initialized {self.name}")
        logger.info(f"  Primary interval: {context.primary_interval.value}")

        for symbol in context.symbols:
            intervals = context.available_intervals(symbol)
            logger.info(f"  {symbol}: {[i.value for i in intervals]}")

    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """Generate momentum signals with daily trend filter."""
        signals = []

        for symbol in context.symbols:
            # Get daily trend
            daily_hist = context.history(
                symbol,
                self.params['daily_ma_period'] + 1,
                interval=Interval.DAY
            )

            if daily_hist is None:
                continue

            daily_closes = daily_hist.get_closes()
            daily_sma = np.mean(daily_closes[-self.params['daily_ma_period']:])
            daily_price = daily_closes[-1]

            # Daily trend: up if price > SMA
            daily_uptrend = daily_price > daily_sma

            # Get intraday data for breakout
            intraday_hist = context.history(symbol, self.params['breakout_period'] + 1)
            if intraday_hist is None:
                continue

            highs = intraday_hist.get_highs()
            lows = intraday_hist.get_lows()
            current_price = context.current_price(symbol)

            # Lookback high/low (excluding current bar)
            lookback_high = np.max(highs[:-1])
            lookback_low = np.min(lows[:-1])

            has_position = context.has_position(symbol)

            # Buy: daily uptrend + breakout above N-bar high
            if daily_uptrend and current_price > lookback_high and not has_position:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=0.8,
                    confidence=0.7,
                    metadata={
                        'strategy': 'mtf_momentum',
                        'daily_trend': 'up',
                        'breakout_high': lookback_high
                    }
                ))

            # Sell: downtrend or breakdown below N-bar low
            elif has_position:
                if not daily_uptrend or current_price < lookback_low:
                    position = context.position(symbol)
                    signals.append(Signal(
                        symbol=symbol,
                        direction=SignalDirection.CLOSE,
                        timestamp=context.current_time,
                        strength=0.8,
                        confidence=0.7,
                        quantity=abs(position.quantity),
                        metadata={
                            'strategy': 'mtf_momentum',
                            'reason': 'trend_reversal' if not daily_uptrend else 'breakdown'
                        }
                    ))

        return signals

