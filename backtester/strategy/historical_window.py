"""
Historical Window Module - Efficient historical data access for strategies

This module provides the HistoricalWindow class which offers convenient access
to historical OHLCV data through both array-based and DataFrame-based interfaces.

Performance optimized with Polars for 5-20x faster operations compared to Pandas.
"""

from datetime import datetime
import numpy as np
import polars as pl


class HistoricalWindow:
    """
    Efficient container for accessing historical bars.

    Provides convenient access to historical OHLCV data through both
    array-based and DataFrame-based interfaces. Designed for use in
    indicator calculations and historical analysis.

    Internal storage uses Polars DataFrame for 5-20× performance improvement
    over Pandas. All operations are optimized for speed and memory efficiency.

    Performance Target: <1ms for 200-bar window access
    """

    def __init__(self, df: pl.DataFrame, symbol: str):
        """
        Initialize HistoricalWindow.

        Args:
            df: Polars DataFrame with OHLCV data (columns: date, open, high, low, close, volume)
            symbol: Trading symbol
        """
        if df is None or df.height == 0:
            raise ValueError(f"Cannot create HistoricalWindow for {symbol} with empty data")

        self._df = df
        self._symbol = symbol

        # Sort by date to ensure chronological order
        if 'date' in self._df.columns:
            self._df = self._df.sort('date')

    def get_closes(self) -> np.ndarray:
        """
        Get array of close prices.

        Returns:
            Numpy array of close prices (oldest to newest)
        """
        return self._df['close'].to_numpy()

    def get_opens(self) -> np.ndarray:
        """
        Get array of open prices.

        Returns:
            Numpy array of open prices (oldest to newest)
        """
        return self._df['open'].to_numpy()

    def get_highs(self) -> np.ndarray:
        """
        Get array of high prices.

        Returns:
            Numpy array of high prices (oldest to newest)
        """
        return self._df['high'].to_numpy()

    def get_lows(self) -> np.ndarray:
        """
        Get array of low prices.

        Returns:
            Numpy array of low prices (oldest to newest)
        """
        return self._df['low'].to_numpy()

    def get_volumes(self) -> np.ndarray:
        """
        Get array of volumes.

        Returns:
            Numpy array of volumes (oldest to newest)
        """
        return self._df['volume'].to_numpy()

    def get_timestamps(self) -> np.ndarray:
        """
        Get array of timestamps.

        Returns:
            Numpy array of datetime objects (oldest to newest)
        """
        return self._df['date'].to_numpy()

    def get_field(self, field: str) -> np.ndarray:
        """
        Get array for any field in the DataFrame.

        Args:
            field: Column name (e.g., 'close', 'volume', 'oi')

        Returns:
            Numpy array of values

        Raises:
            KeyError: If field doesn't exist
        """
        if field not in self._df.columns:
            raise KeyError(f"Field '{field}' not found in historical data for {self._symbol}")
        return self._df[field].to_numpy()

    def __len__(self) -> int:
        """
        Get number of bars in the window.

        Returns:
            Number of historical bars
        """
        return self._df.height

    def __getitem__(self, index: int) -> dict:
        """
        Get a specific bar by index.

        Args:
            index: Bar index (0 = oldest, -1 = newest)

        Returns:
            Dictionary with OHLCV data for the bar
        """
        # Convert single row to dictionary for easy access
        return self._df[index].to_dicts()[0]

    @property
    def symbol(self) -> str:
        """Get symbol for this window"""
        return self._symbol

    @property
    def data(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

    @property
    def is_empty(self) -> bool:
        """Check if window is empty"""
        return self._df.height == 0

    @property
    def start_time(self) -> datetime:
        """Get timestamp of first bar."""
        return self._df['date'][0]

    @property
    def end_time(self) -> datetime:
        """Get timestamp of last bar."""
        return self._df['date'][-1]

    # Helper methods for common operations

    def rolling_mean(self, column: str, window: int) -> np.ndarray:
        """
        Calculate rolling mean for a column.

        Args:
            column: Column name (e.g., 'close', 'volume')
            window: Rolling window size

        Returns:
            Numpy array of rolling mean values
        """
        return self._df.select(
            pl.col(column).rolling_mean(window_size=window)
        ).to_numpy().flatten()

    def rolling_std(self, column: str, window: int) -> np.ndarray:
        """
        Calculate rolling standard deviation for a column.

        Args:
            column: Column name (e.g., 'close', 'volume')
            window: Rolling window size

        Returns:
            Numpy array of rolling std values
        """
        return self._df.select(
            pl.col(column).rolling_std(window_size=window)
        ).to_numpy().flatten()

    def pct_change(self, column: str = 'close') -> np.ndarray:
        """
        Calculate percentage change for a column.

        Args:
            column: Column name (default: 'close')

        Returns:
            Numpy array of percentage changes
        """
        return self._df.select(
            pl.col(column).pct_change()
        ).to_numpy().flatten()

    def ema(self, column: str, span: int) -> np.ndarray:
        """
        Calculate exponential moving average for a column.

        Args:
            column: Column name (e.g., 'close')
            span: EMA span (periods)

        Returns:
            Numpy array of EMA values
        """
        # Polars EMA using ewm_mean
        return self._df.select(
            pl.col(column).ewm_mean(span=span, adjust=False)
        ).to_numpy().flatten()

    def tail(self, n: int) -> 'HistoricalWindow':
        """
        Get last n bars as a new HistoricalWindow.

        Args:
            n: Number of bars to return

        Returns:
            New HistoricalWindow with last n bars
        """
        return HistoricalWindow(self._df.tail(n), self._symbol)

    def head(self, n: int) -> 'HistoricalWindow':
        """
        Get first n bars as a new HistoricalWindow.

        Args:
            n: Number of bars to return

        Returns:
            New HistoricalWindow with first n bars
        """
        return HistoricalWindow(self._df.head(n), self._symbol)

    def __repr__(self) -> str:
        """String representation for debugging"""
        if self.is_empty:
            return f"HistoricalWindow(symbol={self._symbol}, bars=0, empty=True)"
        return (
            f"HistoricalWindow(symbol={self._symbol}, bars={len(self)}, "
            f"start={self.start_time}, end={self.end_time})"
        )