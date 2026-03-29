"""
Backtester Utilities Package

Provides utility functions for data conversion, performance optimization,
and common operations across the backtesting system.
"""

from .log_setup import setup_backtest_logging

from .dataframe_utils import (
    pandas_to_polars,
    polars_to_pandas,
    convert_market_data_to_polars,
    align_polars_dataframes,
    create_equity_curve_polars,
    calculate_returns_polars,
    get_price_at_timestamp,
    get_price_history,
    optimize_polars_dataframe,
    batch_convert_to_polars,
    DataFrameAdapter
)

__all__ = [
    # Logging
    'setup_backtest_logging',

    # Conversion Functions
    'pandas_to_polars',
    'polars_to_pandas',
    'convert_market_data_to_polars',
    'batch_convert_to_polars',

    # Alignment & Query
    'align_polars_dataframes',
    'get_price_at_timestamp',
    'get_price_history',

    # Creation & Calculation
    'create_equity_curve_polars',
    'calculate_returns_polars',

    # Optimization
    'optimize_polars_dataframe',

    # Adapters
    'DataFrameAdapter',
]

__version__ = '1.0.0'
