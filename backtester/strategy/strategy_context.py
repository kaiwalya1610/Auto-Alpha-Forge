"""
Strategy Context Module - Read-only abstraction layer for strategies

This module provides the StrategyContext class which enables strategies to access
market data, portfolio state, and historical information without coupling to the
underlying infrastructure.

Design Philosophy: "Tell, Don't Ask" - Context provides rich, pre-processed information
rather than raw data requiring manipulation.

Multi-Timeframe Support: Strategies can access data from multiple timeframes by
specifying the `interval` parameter in methods like `history()` and `current_bar()`.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import numpy as np
import logging
import polars as pl

# Import data structures from separate modules
from .market_data import MarketData
from .position_info import PositionInfo
from .portfolio_snapshot import PortfolioSnapshot
from .historical_window import HistoricalWindow

from backtester.data_loader import Interval

if TYPE_CHECKING:
    from ..data_loader import DataOrchestrator
    from ..portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)


class StrategyContext:
    """
    Read-only abstraction layer for strategy access to market data and portfolio state.

    StrategyContext provides strategies with controlled access to:
    - Current market data for all symbols
    - Historical data windows
    - Portfolio state and positions
    - Helper utilities for common calculations

    Design Philosophy:
    - Immutable from strategy perspective (all returned data is read-only)
    - Performance optimized with intelligent caching
    - Graceful handling of missing data (returns None instead of raising)
    - Clear separation between data access and portfolio management

    A new StrategyContext instance is created for each bar in the backtest,
    ensuring a consistent view of data at that point in time.
    """

    def __init__(
        self,
        data_orchestrator: 'DataOrchestrator',
        portfolio_manager: 'PortfolioManager',
        current_timestamp: datetime,
        bar_index: int,
        symbols: List[str],
        current_data_cache: Dict[str, Dict['Interval', pl.DataFrame]],
        primary_interval: 'Interval',
        total_bars: Optional[int] = None
    ):
        """
        Initialize StrategyContext.

        Args:
            data_orchestrator: DataOrchestrator instance for market data
            portfolio_manager: PortfolioManager instance for portfolio state
            current_timestamp: Current bar timestamp
            bar_index: Current bar index (0-based)
            symbols: List of symbols in the universe
            current_data_cache: Multi-timeframe data cache {symbol: {interval: DataFrame}}
            primary_interval: The interval driving the event loop
            total_bars: Total number of bars in the backtest (optional)
        """
        self._data_orchestrator = data_orchestrator
        self._portfolio_manager = portfolio_manager
        self._current_timestamp = current_timestamp
        self._bar_index = bar_index
        self._symbols = symbols
        self._current_data_cache = current_data_cache
        self._primary_interval = primary_interval
        self._total_bars = total_bars

        # Instance-level cache for expensive operations
        self._cache: Dict[str, Any] = {}
        self._portfolio_snapshot: Optional[PortfolioSnapshot] = None

    def _interval_key(self, interval: 'Interval') -> str:
        """Get string key for an interval (for cache keys and logging)."""
        return interval.value if hasattr(interval, 'value') else str(interval)

    def _get_interval_data(self, symbol: str, interval: 'Interval' = None) -> Optional[pl.DataFrame]:
        """
        Get DataFrame for a symbol at a specific interval.
        
        Args:
            symbol: Trading symbol
            interval: Time interval (defaults to primary_interval if None)
            
        Returns:
            Polars DataFrame if available, None otherwise
        """
        tf = interval if interval is not None else self._primary_interval
        
        if symbol not in self._current_data_cache:
            return None
            
        interval_data = self._current_data_cache[symbol]
        
        if tf not in interval_data:
            logger.debug(f"Interval {self._interval_key(tf)} not available for {symbol}")
            return None
            
        return interval_data[tf]

    def _get_htf_timestamp(self, symbol: str, interval: 'Interval') -> Optional[datetime]:
        """
        Find the appropriate higher-timeframe bar timestamp for current time.
        
        When iterating on a lower timeframe (e.g., 15-min), this finds the
        corresponding bar timestamp for a higher timeframe (e.g., daily).
        
        Example: If current_timestamp is 2024-01-15 10:30 and interval is DAY,
        returns 2024-01-15 00:00 (or the last completed daily bar before that time).
        
        Args:
            symbol: Trading symbol
            interval: Higher timeframe interval to look up
            
        Returns:
            Timestamp of the appropriate HTF bar, or None if not found
        """
        df = self._get_interval_data(symbol, interval)
        if df is None or df.height == 0:
            return None

        # Filter to bars with timestamp <= current timestamp (DataOrchestrator uses 'datetime')
        available = df.filter(pl.col('datetime') <= self._current_timestamp)
        if available.height == 0:
            return None
        return available['datetime'][-1]

    # ========================================================================
    # CURRENT DATA ACCESS
    # ========================================================================

    def current_bar(self, symbol: str, interval: 'Interval' = None) -> Optional[MarketData]:
        """
        Get current bar data for a symbol.

        For the primary interval, returns the bar matching the current timestamp.
        For higher timeframes, returns the most recent bar at or before current timestamp.

        Args:
            symbol: Trading symbol
            interval: Time interval (default: primary interval)

        Returns:
            MarketData object if data exists, None otherwise

        Performance: O(1) lookup with caching

        Example:
            # Get current 15-min bar (primary)
            bar = context.current_bar('SBIN')
            
            # Get current daily bar
            daily_bar = context.current_bar('SBIN', interval=Interval .DAY)
        """
        if symbol not in self._symbols:
            logger.warning(f"Symbol {symbol} not in universe")
            return None

        # Resolve interval
        tf = interval if interval is not None else self._primary_interval
        
        # Build cache key including interval
        tf_key = self._interval_key(tf)
        cache_key = f"bar_{symbol}_{tf_key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        df = self._get_interval_data(symbol, tf)
        if df is None:
            return None

        # Most recent bar at or before current time; for primary interval must match exactly
        matching_rows = df.filter(pl.col('datetime') <= self._current_timestamp).tail(1)
        if matching_rows.height == 0:
            return None
        if tf == self._primary_interval and matching_rows['datetime'][0] != self._current_timestamp:
            return None

        row_dict = matching_rows.row(0, named=True)
        bar_timestamp = row_dict.get('datetime', self._current_timestamp)

        oi_value = row_dict.get('oi')
        open_interest = int(oi_value) if oi_value is not None else None

        market_data = MarketData(
            symbol=symbol,
            timestamp=bar_timestamp,
            open=float(row_dict['open']),
            high=float(row_dict['high']),
            low=float(row_dict['low']),
            close=float(row_dict['close']),
            volume=int(row_dict['volume']),
            open_interest=open_interest,
        )

        self._cache[cache_key] = market_data
        return market_data

    def current_bars(self, interval: 'Interval' = None) -> Dict[str, MarketData]:
        """
        Get current bar data for all symbols with valid data.

        Useful for cross-sectional analysis across the universe.

        Args:
            interval: Time interval (default: primary interval)

        Returns:
            Dictionary {symbol: MarketData} for all symbols with valid current data
        """
        tf = interval if interval is not None else self._primary_interval
        tf_key = self._interval_key(tf)
        cache_key = f"bars_all_{tf_key}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        result = {}
        for symbol in self._symbols:
            bar = self.current_bar(symbol, interval=tf)
            if bar is not None:
                result[symbol] = bar

        self._cache[cache_key] = result
        return result

    def current_price(self, symbol: str) -> Optional[float]:
        """
        Get current close price for a symbol.

        Convenience method equivalent to current_bar(symbol).close

        Args:
            symbol: Trading symbol

        Returns:
            Close price if data exists, None otherwise
        """
        bar = self.current_bar(symbol)
        return bar.close if bar is not None else None

    # ========================================================================
    # HISTORICAL DATA ACCESS
    # ========================================================================

    def history(
        self,
        symbol: str,
        periods: int,
        include_current: bool = True,
        interval: 'Interval' = None
    ) -> Optional[HistoricalWindow]:
        """
        Get historical data window for a symbol at a specific timeframe.

        Retrieves N bars of historical data ending at (or before) the current bar.
        Returns None if insufficient data is available.

        For higher timeframes, the data is filtered up to the most recent bar
        that is at or before the current timestamp.

        Args:
            symbol: Trading symbol
            periods: Number of historical bars to retrieve
            include_current: Whether to include the current bar in the window
            interval: Time interval (default: primary interval)

        Returns:
            HistoricalWindow if sufficient data exists, None otherwise

        Example:
            # Get last 20 bars of primary interval
            hist = context.history('SBIN', 20)
            closes = hist.get_closes()
            ma = closes.mean()

            # Get last 50 daily bars for trend context
            hist_daily = context.history('SBIN', 50, interval=Interval.DAY)
            daily_ma = hist_daily.get_closes().mean()

            # Get last 50 bars excluding current (for indicator calculation)
            hist = context.history('SBIN', 50, include_current=False)
        """
        if symbol not in self._symbols:
            logger.warning(f"Symbol {symbol} not in universe")
            return None

        if periods <= 0:
            raise ValueError(f"periods must be positive, got {periods}")

        tf = interval if interval is not None else self._primary_interval
        tf_key = self._interval_key(tf)
        cache_key = f"history_{symbol}_{periods}_{include_current}_{tf_key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get data for the specified interval (DataOrchestrator uses 'datetime')
        df = self._get_interval_data(symbol, tf)
        if df is None:
            logger.debug(f"No {tf_key} data available for {symbol}")
            return None

        if include_current:
            filtered_df = df.filter(pl.col('datetime') <= self._current_timestamp)
        else:
            filtered_df = df.filter(pl.col('datetime') < self._current_timestamp)

        if filtered_df.height < periods:
            logger.debug(
                f"Insufficient {tf_key} data for {symbol}: requested {periods} bars, "
                f"have {filtered_df.height}"
            )
            return None

        window_df = filtered_df.tail(periods).rename({'datetime': 'date'})

        window = HistoricalWindow(df=window_df, symbol=symbol)
        self._cache[cache_key] = window
        return window

    def history_multi(
        self,
        symbols: List[str],
        periods: int,
        include_current: bool = True,
        interval: 'Interval' = None
    ) -> Dict[str, HistoricalWindow]:
        """
        Get historical data windows for multiple symbols at a specific timeframe.

        Batch retrieval method for multiple symbols. Only returns windows for
        symbols with sufficient data available.

        Args:
            symbols: List of trading symbols
            periods: Number of historical bars to retrieve
            include_current: Whether to include the current bar
            interval: Time interval (default: primary interval)

        Returns:
            Dictionary {symbol: HistoricalWindow} for symbols with sufficient data

        Example:
            # Get 15-min history for multiple symbols
            histories = context.history_multi(['SBIN', 'INFY', 'TCS'], 20)
            
            # Get daily history for multiple symbols
            daily_histories = context.history_multi(
                ['SBIN', 'INFY', 'TCS'], 
                50, 
                interval=Interval.DAY
            )
        """
        result = {}
        for symbol in symbols:
            window = self.history(symbol, periods, include_current, interval=interval)
            if window is not None:
                result[symbol] = window

        return result

    # ========================================================================
    # PORTFOLIO STATE ACCESS
    # ========================================================================

    def portfolio(self) -> PortfolioSnapshot:
        """
        Get complete portfolio state snapshot.

        Returns fresh snapshot with latest prices. Result is cached per
        context instance.

        Returns:
            Immutable PortfolioSnapshot with all portfolio metrics
        """
        if self._portfolio_snapshot is not None:
            return self._portfolio_snapshot

        # Build current prices dictionary from current bars
        current_prices = {}
        for symbol in self._symbols:
            price = self.current_price(symbol)
            if price is not None:
                current_prices[symbol] = price

        self._portfolio_snapshot = PortfolioSnapshot.from_portfolio_manager(
            pm=self._portfolio_manager,
            current_prices=current_prices,
            timestamp=self._current_timestamp
        )

        return self._portfolio_snapshot

    def position(self, symbol: str) -> Optional[PositionInfo]:
        """
        Get position info for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            PositionInfo if position exists, None otherwise
        """
        return self.portfolio().get_position(symbol)

    def positions(self) -> Dict[str, PositionInfo]:
        """
        Get all open positions.

        Returns:
            Dictionary {symbol: PositionInfo} for all open positions
        """
        return self.portfolio().positions

    def cash(self) -> float:
        """
        Get available cash.

        Returns:
            Available cash amount
        """
        return self.portfolio().cash

    def portfolio_value(self) -> float:
        """
        Get total portfolio value (cash + positions).

        Returns:
            Total portfolio value
        """
        return self.portfolio().total_value

    def has_position(self, symbol: str) -> bool:
        """
        Check if portfolio has a position in the given symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if position exists, False otherwise
        """
        return self.portfolio().has_position(symbol)

    def has_data(self, symbol: str, periods: int, interval: 'Interval' = None) -> bool:
        """
        Check if sufficient historical data is available for a symbol at a timeframe.

        Args:
            symbol: Trading symbol
            periods: Number of periods required
            interval: Time interval (default: primary interval)

        Returns:
            True if at least 'periods' bars of data are available, False otherwise

        Example:
            # Check if we have enough data for 50-period MA on primary interval
            if context.has_data('SBIN', 50):
                hist = context.history('SBIN', 50)
                # Safe to calculate 50-period indicator
                
            # Check daily data availability
            if context.has_data('SBIN', 200, interval=Interval.DAY):
                hist_daily = context.history('SBIN', 200, interval=Interval.DAY)
        """
        if symbol not in self._symbols:
            return False

        df = self._get_interval_data(symbol, interval)
        if df is None:
            return False
        return df.filter(pl.col('datetime') <= self._current_timestamp).height >= periods

    # ========================================================================
    # METADATA AND TIMING
    # ========================================================================

    @property
    def current_time(self) -> datetime:
        """Get current timestamp"""
        return self._current_timestamp

    @property
    def bar_index(self) -> int:
        """Get current bar index (0-based)"""
        return self._bar_index

    @property
    def total_bars(self) -> Optional[int]:
        """Get total number of bars in the backtest (None if unknown)"""
        return self._total_bars

    @property
    def is_last_bar(self) -> bool:
        """Check if this is the last bar in the backtest"""
        if self._total_bars is None:
            return False
        return self._bar_index == (self._total_bars - 1)

    @property
    def symbols(self) -> List[str]:
        """Get symbol universe"""
        return self._symbols.copy()  # Return copy to prevent modification

    @property
    def primary_interval(self) -> 'Interval':
        """Get the primary interval driving the event loop"""
        return self._primary_interval

    def available_intervals(self, symbol: str) -> List['Interval']:
        """
        Get list of available intervals for a symbol.
        
        Useful for checking what timeframe data is available before
        attempting to access it.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of Interval enum values available for the symbol
            
        Example:
            intervals = context.available_intervals('SBIN')
            # [Interval.MINUTE_15, Interval.DAY, Interval.HOUR_1]
            
            if Interval.DAY in intervals:
                daily_hist = context.history('SBIN', 50, interval=Interval.DAY)
        """
        if symbol not in self._current_data_cache:
            return []
        return list(self._current_data_cache[symbol].keys())

    # ========================================================================
    # HELPER UTILITIES
    # ========================================================================

    def highest_high(self, symbol: str, periods: int) -> Optional[float]:
        """
        Get highest high price over the last N periods.

        Args:
            symbol: Trading symbol
            periods: Number of periods to look back

        Returns:
            Highest high price if data available, None otherwise

        Example:
            # Get 20-period high
            high_20 = context.highest_high('SBIN', 20)
        """
        window = self.history(symbol, periods, include_current=True)
        if window is None:
            return None

        highs = window.get_highs()
        return float(np.max(highs))

    def lowest_low(self, symbol: str, periods: int) -> Optional[float]:
        """
        Get lowest low price over the last N periods.

        Args:
            symbol: Trading symbol
            periods: Number of periods to look back

        Returns:
            Lowest low price if data available, None otherwise

        Example:
            # Get 20-period low
            low_20 = context.lowest_low('SBIN', 20)
        """
        window = self.history(symbol, periods, include_current=True)
        if window is None:
            return None

        lows = window.get_lows()
        return float(np.min(lows))

    def average_volume(self, symbol: str, periods: int) -> Optional[float]:
        """
        Get average volume over the last N periods.

        Args:
            symbol: Trading symbol
            periods: Number of periods to look back

        Returns:
            Average volume if data available, None otherwise

        Example:
            # Check if current volume is above 20-period average
            avg_vol = context.average_volume('SBIN', 20)
            current_vol = context.current_bar('SBIN').volume
            if current_vol > avg_vol * 1.5:
                # High volume breakout
                pass
        """
        window = self.history(symbol, periods, include_current=True)
        if window is None:
            return None

        volumes = window.get_volumes()
        return float(np.mean(volumes))

    def price_change_percent(self, symbol: str, periods: int) -> Optional[float]:
        """
        Get percentage price change over the last N periods.

        Calculates the percentage change from the close price N periods ago
        to the current close price.

        Args:
            symbol: Trading symbol
            periods: Number of periods to look back

        Returns:
            Percentage change if data available, None otherwise

        Example:
            # Get 5-period percentage change
            change = context.price_change_percent('SBIN', 5)
            if change and change > 5.0:
                # Price up 5% or more
                pass
        """
        window = self.history(symbol, periods + 1, include_current=True)
        if window is None or len(window) < periods + 1:
            return None

        closes = window.get_closes()
        old_price = closes[0]
        new_price = closes[-1]

        if old_price == 0:
            return None

        return float(((new_price - old_price) / old_price) * 100)

    def calculate_position_size(
        self,
        symbol: str,
        risk_percent: float,
        stop_distance: float
    ) -> Optional[float]:
        """
        Calculate position size based on risk parameters.

        Uses the fixed fractional position sizing method:
        Position Size = (Portfolio Value × Risk %) / Stop Distance

        Args:
            symbol: Trading symbol
            risk_percent: Percentage of portfolio to risk (e.g., 1.0 for 1%)
            stop_distance: Distance to stop loss in price units (e.g., 10 for ₹10)

        Returns:
            Number of shares/contracts to buy, None if calculation not possible

        Example:
            # Risk 1% of portfolio with ₹10 stop
            current_price = context.current_price('SBIN')
            stop_price = current_price - 10
            stop_distance = current_price - stop_price

            quantity = context.calculate_position_size('SBIN', 1.0, stop_distance)
            if quantity and quantity > 0:
                # Place order for calculated quantity
                pass
        """
        if risk_percent <= 0 or stop_distance <= 0:
            logger.warning(
                f"Invalid parameters: risk_percent={risk_percent}, "
                f"stop_distance={stop_distance}"
            )
            return None

        current_price = self.current_price(symbol)
        if current_price is None:
            return None

        portfolio_val = self.portfolio_value()
        risk_amount = portfolio_val * (risk_percent / 100)

        # Calculate shares
        shares = risk_amount / stop_distance

        # Round down to avoid over-risking
        return float(np.floor(shares))

    def simple_moving_average(self, symbol: str, periods: int) -> Optional[float]:
        """
        Calculate simple moving average.

        Convenience helper for common indicator calculation.

        Args:
            symbol: Trading symbol
            periods: Number of periods for MA

        Returns:
            SMA value if data available, None otherwise

        Example:
            # Calculate 50-period SMA
            sma_50 = context.simple_moving_average('SBIN', 50)
            current = context.current_price('SBIN')
            if current and sma_50 and current > sma_50:
                # Price above 50-period MA
                pass
        """
        window = self.history(symbol, periods, include_current=True)
        if window is None:
            return None

        closes = window.get_closes()
        return float(np.mean(closes))

    def exponential_moving_average(
        self,
        symbol: str,
        periods: int
    ) -> Optional[float]:
        """
        Calculate exponential moving average.

        Args:
            symbol: Trading symbol
            periods: Number of periods for EMA

        Returns:
            EMA value if data available, None otherwise

        Example:
            # Calculate 20-period EMA
            ema_20 = context.exponential_moving_average('SBIN', 20)
        """
        window = self.history(symbol, periods * 2, include_current=True)
        if window is None:
            return None

        # Use HistoricalWindow's built-in EMA method (Polars-based)
        ema_values = window.ema('close', span=periods)

        return float(ema_values[-1])

    def __repr__(self) -> str:
        """String representation for debugging"""
        primary_tf = self._interval_key(self._primary_interval)
        return (
            f"StrategyContext(timestamp={self._current_timestamp}, "
            f"bar_index={self._bar_index}, "
            f"symbols={len(self._symbols)}, "
            f"primary_interval={primary_tf}, "
            f"portfolio_value={self.portfolio_value():.2f})"
        )