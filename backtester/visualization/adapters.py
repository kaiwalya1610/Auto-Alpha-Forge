"""
Data adapters for visualization.

Transforms backtest data into chart-ready formats.
No streaming support - post-backtest visualization only.
"""

from typing import Any, Dict, Optional
import polars as pl


# Dark theme colors (hardcoded)
BULLISH_COLOR = "#00C853"
BEARISH_COLOR = "#FF1744"


def adapt_equity(source: Any) -> pl.DataFrame:
    """
    Transform BacktestResults to equity visualization data.

    Output columns:
        - timestamp: Datetime
        - total_value: Float (portfolio value)
        - cash: Float
        - positions_value: Float
        - returns: Float (% change from previous)
        - cumulative_returns: Float (% from initial)
        - drawdown: Float (% drawdown from peak, negative)

    Args:
        source: BacktestResults or equity DataFrame

    Returns:
        Polars DataFrame with equity metrics
    """
    # Extract equity curve and initial capital
    if hasattr(source, 'equity_curve'):
        equity_curve = source.equity_curve
        initial_capital = source.initial_capital
    elif isinstance(source, pl.DataFrame):
        equity_curve = source
        initial_capital = source['total_value'][0] if 'total_value' in source.columns else 100000
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")

    # Clone to avoid modifying original
    df = equity_curve.clone()

    # Ensure required column exists
    if 'total_value' not in df.columns:
        raise ValueError("Source must have 'total_value' column")

    # Calculate returns (percentage change)
    df = df.with_columns([
        (pl.col('total_value').pct_change() * 100).alias('returns'),
    ])

    # Calculate cumulative returns from initial capital
    df = df.with_columns([
        ((pl.col('total_value') - initial_capital) / initial_capital * 100)
        .alias('cumulative_returns'),
    ])

    # Calculate drawdown
    df = df.with_columns([
        pl.col('total_value').cum_max().alias('_peak'),
    ]).with_columns([
        ((pl.col('total_value') - pl.col('_peak')) / pl.col('_peak') * 100)
        .alias('drawdown'),
    ]).drop('_peak')

    # Fill first row NaN returns with 0
    df = df.with_columns([
        pl.col('returns').fill_null(0),
    ])

    return df


def adapt_ohlcv(source: Any, symbol: Optional[str] = None) -> pl.DataFrame:
    """
    Transform OHLCV data to candlestick format.

    Output columns:
        - datetime: Datetime
        - open, high, low, close: Float
        - volume: Float
        - color: String (bullish/bearish color for candles)

    Args:
        source: DataFrame, list of dicts, or data cache dict
        symbol: Symbol to extract (required if source is data cache)

    Returns:
        Polars DataFrame with standardized OHLCV
    """
    # Handle Polars DataFrame
    if isinstance(source, pl.DataFrame):
        df = _normalize_ohlcv_dataframe(source)

    # Handle list of dicts
    elif isinstance(source, list) and source and isinstance(source[0], dict):
        df = pl.DataFrame(source)
        df = _normalize_ohlcv_dataframe(df)

    # Handle data cache dict {symbol: {interval: DataFrame}}
    elif isinstance(source, dict):
        if symbol is None:
            raise ValueError("Symbol required when source is data cache dict")
        df = _extract_ohlcv_from_cache(source, symbol)

    else:
        raise ValueError(f"Unsupported source type: {type(source)}")

    # Add color column for candles
    df = df.with_columns([
        pl.when(pl.col('close') >= pl.col('open'))
        .then(pl.lit(BULLISH_COLOR))
        .otherwise(pl.lit(BEARISH_COLOR))
        .alias('color')
    ])

    return df


def _normalize_ohlcv_dataframe(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize DataFrame column names to standard OHLCV format."""
    # Map various column names to standard names
    column_mapping = {
        'date': 'datetime',
        'time': 'datetime',
        'timestamp': 'datetime',
        'Date': 'datetime',
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume',
        'OPEN': 'open',
        'HIGH': 'high',
        'LOW': 'low',
        'CLOSE': 'close',
        'VOLUME': 'volume',
    }

    # Rename columns that exist
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df = df.rename({old_name: new_name})

    # Ensure required columns exist
    required = ['open', 'high', 'low', 'close']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Add datetime if missing (use index)
    if 'datetime' not in df.columns:
        df = df.with_row_index('datetime')
        df = df.with_columns([
            pl.col('datetime').cast(pl.Int64)
        ])

    # Add volume if missing
    if 'volume' not in df.columns:
        df = df.with_columns([
            pl.lit(0).alias('volume')
        ])

    # Select and order columns
    return df.select(['datetime', 'open', 'high', 'low', 'close', 'volume'])


def _extract_ohlcv_from_cache(cache: Dict, symbol: str) -> pl.DataFrame:
    """Extract symbol data from backtester data cache."""
    if symbol not in cache:
        raise ValueError(f"Symbol {symbol} not in data cache")

    symbol_data = cache[symbol]

    # If nested by interval, take the first interval
    if isinstance(symbol_data, dict):
        first_interval = list(symbol_data.keys())[0]
        df = symbol_data[first_interval]
    else:
        df = symbol_data

    return _normalize_ohlcv_dataframe(df)


def adapt_trades(source: Any, symbol_filter: Optional[str] = None) -> pl.DataFrame:
    """
    Transform transactions to trade marker format.

    Output columns:
        - timestamp: Datetime
        - symbol: String
        - action: String ("BUY" or "SELL")
        - quantity: Int
        - price: Float
        - marker_color: String (green for buy, red for sell)
        - marker_symbol: String (triangle-up/triangle-down)
        - marker_size: Float (proportional to quantity)
        - annotation_text: String (hover text)

    Args:
        source: BacktestResults or list of Transaction objects
        symbol_filter: Only include trades for this symbol (None = all)

    Returns:
        Polars DataFrame with trade marker data
    """
    # Extract transactions
    if hasattr(source, 'transactions'):
        transactions = source.transactions
    elif isinstance(source, list):
        transactions = source
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")

    if not transactions:
        # Return empty DataFrame with correct schema
        return pl.DataFrame({
            'timestamp': [],
            'symbol': [],
            'action': [],
            'quantity': [],
            'price': [],
            'marker_color': [],
            'marker_symbol': [],
            'marker_size': [],
            'annotation_text': [],
        })

    # Convert transactions to records
    records = []
    base_marker_size = 12

    for tx in transactions:
        # Filter by symbol if specified
        if symbol_filter and tx.symbol != symbol_filter:
            continue

        # Get action as string
        action = tx.action.value if hasattr(tx.action, 'value') else str(tx.action)
        is_buy = action.upper() == 'BUY'

        # Calculate marker size (proportional to quantity, capped at 2x base)
        marker_size = min(
            base_marker_size + (tx.quantity / 50),
            base_marker_size * 2
        )

        record = {
            'timestamp': tx.timestamp,
            'symbol': tx.symbol,
            'action': action.upper(),
            'quantity': tx.quantity,
            'price': tx.price,
            'marker_color': BULLISH_COLOR if is_buy else BEARISH_COLOR,
            'marker_symbol': 'triangle-up' if is_buy else 'triangle-down',
            'marker_size': marker_size,
            'annotation_text': f"{action.upper()} {tx.quantity} @ Rs.{tx.price:.2f}",
        }
        records.append(record)

    return pl.DataFrame(records)
