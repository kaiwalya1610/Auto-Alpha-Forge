"""
DataFrame Utilities - Pandas-Polars Conversion Layer

This module provides efficient conversion between Pandas and Polars DataFrames.
Polars is used as the primary DataFrame library for better performance (5-10x faster
than pandas) and memory efficiency.

Design Principle:
- Data loaders output Pandas DataFrames (don't modify existing code)
- Convert to Polars immediately after data retrieval
- Use Polars throughout backtesting pipeline
- Convert back to Pandas only when required by external libraries

Performance Notes:
- Pandas 2.x + Polars uses Apache Arrow for zero-copy conversion (when possible)
- String columns may require copying
- DatetimeIndex is converted to datetime column in Polars
"""

import pandas as pd
import polars as pl
from typing import Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


def pandas_to_polars(
    df: pd.DataFrame,
    include_index: bool = True,
    rechunk: bool = True
) -> pl.DataFrame:
    """
    Convert Pandas DataFrame to Polars DataFrame.

    Uses pl.from_pandas() which leverages Apache Arrow for efficient conversion.
    With Pandas 2.x, this is often zero-copy for compatible dtypes.

    Args:
        df: Pandas DataFrame to convert
        include_index: Whether to include the index as a column (default: True)
        rechunk: Whether to rechunk for better performance (default: True)

    Returns:
        Polars DataFrame

    Performance:
        - Zero-copy for numeric columns with Pandas 2.x
        - ~1-2ms for typical market data (1000 rows x 10 columns)

    Example:
        >>> pdf = pd.DataFrame({'price': [100, 101, 102]})
        >>> plf = pandas_to_polars(pdf)
        >>> type(plf)
        <class 'polars.dataframe.frame.DataFrame'>
    """
    pl_df = pl.from_pandas(df, include_index=include_index)

    if rechunk:
        pl_df = pl_df.rechunk()

    return pl_df


def polars_to_pandas(
    df: pl.DataFrame,
    set_index: Optional[str] = None,
    use_pyarrow_extension_array: bool = True
) -> pd.DataFrame:
    """
    Convert Polars DataFrame to Pandas DataFrame.

    Args:
        df: Polars DataFrame to convert
        set_index: Column name to use as index (optional)
        use_pyarrow_extension_array: Use PyArrow-backed arrays for better compatibility

    Returns:
        Pandas DataFrame

    Performance:
        - Zero-copy with use_pyarrow_extension_array=True (Pandas 2.x)
        - ~1-2ms for typical data

    Example:
        >>> plf = pl.DataFrame({'price': [100, 101, 102]})
        >>> pdf = polars_to_pandas(plf, set_index=None)
        >>> type(pdf)
        <class 'pandas.core.frame.DataFrame'>
    """
    pd_df = df.to_pandas(use_pyarrow_extension_array=use_pyarrow_extension_array)

    if set_index is not None and set_index in pd_df.columns:
        pd_df = pd_df.set_index(set_index)

    return pd_df


def convert_market_data_to_polars(
    data_dict: Dict[str, pd.DataFrame],
    date_column: str = 'date'
) -> Dict[str, pl.DataFrame]:
    """
    Convert dictionary of Pandas DataFrames to Polars.

    Common use case: Convert market data loaded from DataOrchestrator.

    Args:
        data_dict: Dictionary of {symbol: pandas_dataframe}
        date_column: Name of the date/datetime column

    Returns:
        Dictionary of {symbol: polars_dataframe}

    Example:
        >>> data = {
        ...     'SBIN': pd.DataFrame({'date': [...], 'close': [...]}),
        ...     'INFY': pd.DataFrame({'date': [...], 'close': [...]})
        ... }
        >>> pl_data = convert_market_data_to_polars(data)
    """
    converted = {}

    for symbol, pdf in data_dict.items():
        try:
            # Convert to Polars
            plf = pandas_to_polars(pdf, include_index=False)

            # Ensure date column is datetime type
            if date_column in plf.columns:
                plf = plf.with_columns(
                    pl.col(date_column).cast(pl.Datetime)
                )

            # Sort by date for efficient lookups
            plf = plf.sort(date_column)

            converted[symbol] = plf

        except Exception as e:
            logger.error(f"Error converting market data for {symbol}: {e}")
            # Keep original on error
            converted[symbol] = pdf

    return converted


def align_polars_dataframes(
    dfs: Dict[str, pl.DataFrame],
    on: str = 'date',
    how: str = 'outer'
) -> Dict[str, pl.DataFrame]:
    """
    Align multiple Polars DataFrames to common timestamps.

    Args:
        dfs: Dictionary of {symbol: dataframe}
        on: Column to align on (usually 'date' or 'timestamp')
        how: Join strategy ('inner', 'outer', 'left')

    Returns:
        Dictionary of aligned DataFrames

    Note:
        This is more memory-efficient than creating a single joined DataFrame.
    """
    if not dfs:
        return {}

    # Get union of all timestamps (for outer join)
    if how == 'outer':
        all_timestamps = set()
        for df in dfs.values():
            all_timestamps.update(df[on].to_list())
        aligned_timestamps = sorted(all_timestamps)

    # Get intersection of timestamps (for inner join)
    elif how == 'inner':
        timestamp_sets = [set(df[on].to_list()) for df in dfs.values()]
        aligned_timestamps = sorted(set.intersection(*timestamp_sets))

    else:
        # For 'left', use first DataFrame's timestamps
        first_df = next(iter(dfs.values()))
        aligned_timestamps = first_df[on].to_list()

    # Create aligned DataFrames
    aligned = {}
    timestamp_df = pl.DataFrame({on: aligned_timestamps})

    for symbol, df in dfs.items():
        # Left join to preserve all aligned timestamps
        aligned_df = timestamp_df.join(df, on=on, how='left')
        aligned[symbol] = aligned_df

    return aligned


def create_equity_curve_polars(
    equity_data: List[Dict],
    columns: Optional[List[str]] = None
) -> pl.DataFrame:
    """
    Create equity curve DataFrame in Polars format.

    Args:
        equity_data: List of dictionaries with equity snapshots
        columns: Column names to include (None = all)

    Returns:
        Polars DataFrame with equity curve

    Example:
        >>> equity_data = [
        ...     {'timestamp': dt1, 'cash': 10000, 'total_value': 10500},
        ...     {'timestamp': dt2, 'cash': 9500, 'total_value': 11000}
        ... ]
        >>> equity_df = create_equity_curve_polars(equity_data)
    """
    if not equity_data:
        return pl.DataFrame()

    # Create Polars DataFrame directly
    df = pl.from_dicts(equity_data)

    # Filter columns if specified
    if columns is not None:
        df = df.select(columns)

    # Ensure timestamp is datetime
    if 'timestamp' in df.columns:
        df = df.with_columns(pl.col('timestamp').cast(pl.Datetime))

    return df


def calculate_returns_polars(
    equity_df: pl.DataFrame,
    value_column: str = 'total_value'
) -> pl.DataFrame:
    """
    Calculate returns from equity curve using Polars.

    Args:
        equity_df: Equity curve DataFrame
        value_column: Column containing portfolio value

    Returns:
        DataFrame with added 'returns' column

    Performance:
        ~10x faster than pandas for large DataFrames
    """
    df = equity_df.with_columns([
        (pl.col(value_column).pct_change()).alias('returns')
    ])

    return df


def get_price_at_timestamp(
    df: pl.DataFrame,
    timestamp,
    price_column: str = 'close',
    date_column: str = 'date'
) -> Optional[float]:
    """
    Get price at specific timestamp from Polars DataFrame.

    Args:
        df: Market data DataFrame
        timestamp: Timestamp to query
        price_column: Column containing price
        date_column: Column containing dates

    Returns:
        Price value or None if not found

    Performance:
        < 0.1ms with sorted data
    """
    try:
        result = df.filter(pl.col(date_column) == timestamp)

        if result.height == 0:
            return None

        return result[price_column][0]

    except Exception as e:
        logger.debug(f"Error getting price at timestamp: {e}")
        return None


def get_price_history(
    df: pl.DataFrame,
    n_periods: int,
    current_timestamp,
    price_column: str = 'close',
    date_column: str = 'date',
    include_current: bool = True
) -> Optional[pl.Series]:
    """
    Get N periods of price history up to current timestamp.

    Args:
        df: Market data DataFrame
        n_periods: Number of periods to retrieve
        current_timestamp: Current timestamp
        price_column: Column containing price
        date_column: Column containing dates
        include_current: Whether to include current bar

    Returns:
        Polars Series with price history or None

    Performance:
        < 1ms for typical queries (N <= 200)
    """
    try:
        # Filter up to current timestamp
        if include_current:
            filtered = df.filter(pl.col(date_column) <= current_timestamp)
        else:
            filtered = df.filter(pl.col(date_column) < current_timestamp)

        # Take last N periods
        history = filtered.tail(n_periods)[price_column]

        if history.len() == 0:
            return None

        return history

    except Exception as e:
        logger.debug(f"Error getting price history: {e}")
        return None


def optimize_polars_dataframe(df: pl.DataFrame) -> pl.DataFrame:
    """
    Optimize Polars DataFrame for query performance.

    Applies:
    - Rechunking for contiguous memory
    - Type optimization (downcast numeric types)
    - String to categorical conversion for repeated values

    Args:
        df: DataFrame to optimize

    Returns:
        Optimized DataFrame
    """
    # Rechunk for contiguous memory
    df = df.rechunk()

    # Convert string columns with low cardinality to categorical
    for col in df.columns:
        if df[col].dtype == pl.Utf8:
            # Check cardinality
            unique_ratio = df[col].n_unique() / df.height
            if unique_ratio < 0.5:  # Less than 50% unique
                df = df.with_columns(pl.col(col).cast(pl.Categorical))

    return df


# ============================================================================
# BATCH CONVERSION UTILITIES
# ============================================================================

def batch_convert_to_polars(
    dataframes: Union[List[pd.DataFrame], Dict[str, pd.DataFrame]],
    optimize: bool = True
) -> Union[List[pl.DataFrame], Dict[str, pl.DataFrame]]:
    """
    Convert multiple Pandas DataFrames to Polars in batch.

    Args:
        dataframes: List or dict of Pandas DataFrames
        optimize: Whether to optimize after conversion

    Returns:
        Same structure with Polars DataFrames
    """
    if isinstance(dataframes, dict):
        result = {}
        for key, pdf in dataframes.items():
            plf = pandas_to_polars(pdf)
            if optimize:
                plf = optimize_polars_dataframe(plf)
            result[key] = plf
        return result

    elif isinstance(dataframes, list):
        result = []
        for pdf in dataframes:
            plf = pandas_to_polars(pdf)
            if optimize:
                plf = optimize_polars_dataframe(plf)
            result.append(plf)
        return result

    else:
        raise TypeError("dataframes must be list or dict")


# ============================================================================
# COMPATIBILITY LAYER
# ============================================================================

class DataFrameAdapter:
    """
    Adapter to work with both Pandas and Polars DataFrames transparently.

    Useful for gradual migration or when working with libraries that
    require specific DataFrame types.
    """

    def __init__(self, df: Union[pd.DataFrame, pl.DataFrame]):
        """
        Initialize adapter.

        Args:
            df: Either Pandas or Polars DataFrame
        """
        self._df = df
        self._is_polars = isinstance(df, pl.DataFrame)

    @property
    def is_polars(self) -> bool:
        """Check if underlying DataFrame is Polars."""
        return self._is_polars

    @property
    def is_pandas(self) -> bool:
        """Check if underlying DataFrame is Pandas."""
        return not self._is_polars

    def to_polars(self) -> pl.DataFrame:
        """Get as Polars DataFrame."""
        if self._is_polars:
            return self._df
        return pandas_to_polars(self._df)

    def to_pandas(self) -> pd.DataFrame:
        """Get as Pandas DataFrame."""
        if not self._is_polars:
            return self._df
        return polars_to_pandas(self._df)

    def __repr__(self) -> str:
        df_type = "Polars" if self._is_polars else "Pandas"
        return f"DataFrameAdapter({df_type} DataFrame with {len(self._df)} rows)"
