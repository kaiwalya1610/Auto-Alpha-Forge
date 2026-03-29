"""
DataOrchestrator - Smart Caching Gateway for Market Data

Simple caching layer that:
- Stores all data for a symbol+interval in one file
- Automatically fetches missing date ranges
- Merges and deduplicates data

Example:
    >>> from backtester.data_loader.DataOrchestrator import DataOrchestrator
    >>> from backtester.data_loader.KiteDataFetcher import Interval
    >>>
    >>> orchestrator = DataOrchestrator()
    >>> df = orchestrator.get_data(
    ...     symbol="SBIN",
    ...     exchange="NSE",
    ...     start_date="2024-01-01",
    ...     end_date="2024-12-31",
    ...     interval=Interval.MINUTE_15
    ... )
"""

import os
import json
import pandas as pd
import polars as pl
import datetime
from typing import Optional, List, Tuple, Dict, Any, Union
from pathlib import Path
import logging
from threading import Lock
import sys

# Support both package import and direct execution
try:
    from backtester.data_loader.KiteDataFetcher import PyZData, Interval
except ModuleNotFoundError:
    # Add parent directory to path for direct execution
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from backtester.data_loader.KiteDataFetcher import PyZData, Interval

logger = logging.getLogger(__name__)


class DataOrchestrator:
    """
    Smart caching gateway for market data.

    Each symbol+interval combination is stored in one file that grows over time
    as you fetch more date ranges.
    """

    def __init__(self, cache_dir: str = None, enctoken: str = None):
        """
        Initialize DataOrchestrator.

        Args:
            cache_dir: Cache directory path (default: backtester/data_loader/cache)
            enctoken: Zerodha enctoken (optional, will auto-login if not provided)
        """
        # Setup cache directory
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(__file__), 'cache')

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / 'metadata.json'

        # Initialize KiteDataFetcher
        self.kite_fetcher = PyZData(enctoken=enctoken)

        # Load metadata
        self.metadata = self._load_metadata()
        self.lock = Lock()

        logger.info(f"DataOrchestrator ready. Cache: {self.cache_dir}, Datasets: {len(self.metadata)}")

    def _load_metadata(self) -> Dict:
        """Load metadata from JSON file."""
        if not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return {}

    def _save_metadata(self):
        """Save metadata to JSON file."""
        with self.lock:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)

    def get_data(
        self,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        interval: Interval,
        oi: bool = False,
        force_refresh: bool = False
    ) -> pl.DataFrame:
        """
        Get market data with smart caching (Polars-native with Parquet storage).

        Args:
            symbol: Trading symbol (e.g., "SBIN")
            exchange: Exchange (e.g., "NSE")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Time interval (Interval enum)
            oi: Include open interest (default: False)
            force_refresh: Ignore cache (default: False)

        Returns:
            Polars DataFrame with OHLCV data (3-5x faster than Pandas/CSV)

        Example:
            >>> df = orchestrator.get_data("SBIN", "NSE", "2024-01-01", "2024-12-31", Interval.MINUTE_15)
        """
        # Convert dates
        req_start = pd.to_datetime(start_date).date()
        req_end = pd.to_datetime(end_date).date()

        # Cache key and file path (Parquet format for fast I/O)
        interval_str = interval.value if isinstance(interval, Interval) else str(interval)
        cache_key = f"{symbol}_{exchange}_{interval_str}"
        cache_file = self.cache_dir / symbol / exchange / interval_str / 'data.parquet'

        logger.info(f"Request: {cache_key} from {req_start} to {req_end}")

        # Try to read from cache
        cached_df = None
        if not force_refresh and cache_file.exists():
            try:
                cached_df = pl.read_parquet(cache_file)
                # Ensure datetime column is datetime type
                if 'datetime' in cached_df.columns:
                    cached_df = cached_df.with_columns(pl.col('datetime').cast(pl.Datetime))
            except Exception as e:
                logger.warning(f"Failed to read Parquet cache: {e}")

        # Get instrument token
        instrument_token = self.kite_fetcher.get_instrument_token(symbol, exchange)

        # Case 1: No cache - fetch everything
        if cached_df is None or cached_df.height == 0:
            logger.info("Cache miss - fetching from API")

            # Fetch data from API (returns Pandas DataFrame)
            df_pandas = self.kite_fetcher.get_data(
                instrument_token=instrument_token,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                oi=oi,
                print_logs=True
            )

            if not df_pandas.empty:
                # Convert timezone-aware datetime to timezone-naive before Polars conversion
                # (Polars doesn't recognize IST '+05:30' timezone)
                if 'datetime' in df_pandas.columns and hasattr(df_pandas['datetime'].dtype, 'tz') and df_pandas['datetime'].dtype.tz is not None:
                    df_pandas['datetime'] = df_pandas['datetime'].dt.tz_localize(None)

                # Convert to Polars for performance (normalize to μs for Parquet compat)
                df = pl.from_pandas(df_pandas)
                if 'datetime' in df.columns:
                    df = df.with_columns(pl.col('datetime').cast(pl.Datetime('us')))
                self._save_to_cache(cache_key, cache_file, df, symbol, exchange, interval_str, oi)
                logger.info(f"Returned {df.height} records from API")
                return df

            # Return empty Polars DataFrame
            return pl.DataFrame()

        # Case 2: Have cache - check coverage
        cached_start = cached_df['datetime'].min().date()
        cached_end = cached_df['datetime'].max().date()
        logger.info(f"Cache: {cached_start} to {cached_end}")

        # Full coverage?
        if cached_start <= req_start and cached_end >= req_end:
            logger.info("Full cache hit")
            result = cached_df.filter(
                (pl.col('datetime').cast(pl.Date) >= req_start) &
                (pl.col('datetime').cast(pl.Date) <= req_end)
            )
            return result

        # Partial coverage - find gaps
        gaps = []

        # Gap before cache
        if req_start < cached_start:
            gap_end = min(cached_start - datetime.timedelta(days=1), req_end)
            if req_start <= gap_end:
                gaps.append((req_start, gap_end))

        # Gap after cache
        if req_end > cached_end:
            gap_start = max(cached_end + datetime.timedelta(days=1), req_start)
            if gap_start <= req_end:
                gaps.append((gap_start, req_end))

        logger.info(f"Partial cache hit - fetching {len(gaps)} gap(s)")

        # Fetch gaps
        result = cached_df.clone()
        for gap_start, gap_end in gaps:
            logger.info(f"Fetching gap: {gap_start} to {gap_end}")

            gap_df_pandas = self.kite_fetcher.get_data(
                instrument_token=instrument_token,
                start_date=gap_start.strftime('%Y-%m-%d'),
                end_date=gap_end.strftime('%Y-%m-%d'),
                interval=interval,
                oi=oi,
                print_logs=True
            )

            if not gap_df_pandas.empty:
                # Convert timezone-aware datetime to timezone-naive before Polars conversion
                if 'datetime' in gap_df_pandas.columns and hasattr(gap_df_pandas['datetime'].dtype, 'tz') and gap_df_pandas['datetime'].dtype.tz is not None:
                    gap_df_pandas['datetime'] = gap_df_pandas['datetime'].dt.tz_localize(None)

                # Convert to Polars and merge (normalize to μs for Parquet compat)
                gap_df = pl.from_pandas(gap_df_pandas)
                if 'datetime' in gap_df.columns:
                    gap_df = gap_df.with_columns(pl.col('datetime').cast(pl.Datetime('us')))
                result = pl.concat([result, gap_df], how="vertical")

        # Deduplicate and sort
        result = result.unique(subset=['tradingsymbol', 'datetime']).sort('datetime')

        # Update cache with merged data
        self._save_to_cache(cache_key, cache_file, result, symbol, exchange, interval_str, oi)

        # Filter to requested range
        result = result.filter(
            (pl.col('datetime').cast(pl.Date) >= req_start) &
            (pl.col('datetime').cast(pl.Date) <= req_end)
        )

        logger.info(f"Returned {len(result)} records (cache + API)")
        return result

    def _save_to_cache(
        self,
        cache_key: str,
        cache_file: Path,
        df: pl.DataFrame,
        symbol: str,
        exchange: str,
        interval_str: str,
        has_oi: bool
    ):
        """Save Polars DataFrame to Parquet cache and update metadata."""
        if df.height == 0:
            return

        # Create directory and save Parquet (3-5x faster than CSV)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(cache_file)

        # Update metadata
        relative_path = cache_file.relative_to(self.cache_dir)
        with self.lock:
            self.metadata[cache_key] = {
                'symbol': symbol,
                'exchange': exchange,
                'interval': interval_str,
                'start_date': df['datetime'].min().strftime('%Y-%m-%d'),
                'end_date': df['datetime'].max().strftime('%Y-%m-%d'),
                'records': df.height,
                'has_oi': has_oi,
                'file_path': str(relative_path).replace('\\', '/'),
                'last_updated': datetime.datetime.now().isoformat(),
                'format': 'parquet'
            }

        self._save_metadata()
        logger.info(f"Cached {df.height} records for {cache_key} (Parquet)")

    def get_data_batch(
        self,
        symbols: List[str],
        exchange: str,
        start_date: str,
        end_date: str,
        interval: Interval,
        oi: bool = False,
        force_refresh: bool = False
    ) -> Dict[str, pl.DataFrame]:
        """
        Fetch data for multiple symbols (Polars-native).

        Args:
            symbols: List of trading symbols
            exchange: Exchange (same for all)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Time interval
            oi: Include open interest
            force_refresh: Ignore cache

        Returns:
            Dictionary mapping symbols to Polars DataFrames

        Example:
            >>> data = orchestrator.get_data_batch(
            ...     ["SBIN", "INFY", "TCS"],
            ...     "NSE",
            ...     "2024-01-01",
            ...     "2024-12-31",
            ...     Interval.DAY
            ... )
        """
        logger.info(f"Batch request: {len(symbols)} symbols")

        results = {}
        failed = []

        for idx, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"[{idx}/{len(symbols)}] {symbol}")

                df = self.get_data(
                    symbol=symbol,
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                    oi=oi,
                    force_refresh=force_refresh
                )

                if df.height > 0:
                    results[symbol] = df
                else:
                    failed.append(symbol)

            except Exception as e:
                failed.append(symbol)
                logger.error(f"{symbol} failed: {e}")

        logger.info(f"Batch complete: {len(results)} success, {len(failed)} failed")
        if failed:
            logger.warning(f"Failed: {', '.join(failed)}")

        return results

    def get_cache_info(self, symbol: str = None, exchange: str = None) -> Dict[str, Any]:
        """
        Get cache statistics.

        Args:
            symbol: Filter by symbol (optional)
            exchange: Filter by exchange (optional)

        Returns:
            Dictionary with cache info

        Example:
            >>> info = orchestrator.get_cache_info(symbol="SBIN")
            >>> print(f"Cached datasets: {info['datasets']}")
        """
        if symbol and exchange:
            prefix = f"{symbol}_{exchange}_"
            filtered = {k: v for k, v in self.metadata.items() if k.startswith(prefix)}
            return {
                'symbol': symbol,
                'exchange': exchange,
                'datasets': len(filtered),
                'details': filtered
            }

        elif symbol:
            filtered = {k: v for k, v in self.metadata.items() if v['symbol'] == symbol}
            return {
                'symbol': symbol,
                'datasets': len(filtered),
                'details': filtered
            }

        else:
            total_records = sum(v['records'] for v in self.metadata.values())
            symbols = set(v['symbol'] for v in self.metadata.values())
            return {
                'total_datasets': len(self.metadata),
                'total_records': total_records,
                'unique_symbols': len(symbols),
                'symbols': sorted(list(symbols)),
                'cache_dir': str(self.cache_dir)
            }

    def clear_cache(
        self,
        symbol: str = None,
        exchange: str = None,
        interval: Interval = None
    ):
        """
        Clear cached data.

        Args:
            symbol: Clear specific symbol (optional)
            exchange: Clear specific exchange (optional)
            interval: Clear specific interval (optional)

        Example:
            >>> # Clear specific dataset
            >>> orchestrator.clear_cache("SBIN", "NSE", Interval.MINUTE_15)
            >>>
            >>> # Clear all cache
            >>> orchestrator.clear_cache()
        """
        if symbol and exchange and interval:
            # Clear specific cache
            interval_str = interval.value if isinstance(interval, Interval) else str(interval)
            cache_key = f"{symbol}_{exchange}_{interval_str}"

            if cache_key in self.metadata:
                cache_file = self.cache_dir / self.metadata[cache_key]['file_path']

                if cache_file.exists():
                    cache_file.unlink()

                with self.lock:
                    del self.metadata[cache_key]

                self._save_metadata()
                logger.info(f"Cleared cache: {cache_key}")
            else:
                logger.warning(f"Cache key not found: {cache_key}")

        else:
            # Clear all cache
            for meta in self.metadata.values():
                cache_file = self.cache_dir / meta['file_path']
                if cache_file.exists():
                    cache_file.unlink()

            with self.lock:
                self.metadata = {}

            self._save_metadata()
            logger.info("Cleared all cache")


def main():
    """Demo usage of DataOrchestrator."""
    print("=" * 80)
    print("DataOrchestrator Demo")
    print("=" * 80)

    orchestrator = DataOrchestrator()

    # Example 1: Fetch SBIN data
    print("\nExample 1: Fetch SBIN data (15-minute)")
    df = orchestrator.get_data(
        symbol="SBIN",
        exchange="NSE",
        start_date="2024-01-01",
        end_date="2024-01-31",
        interval=Interval.MINUTE_15
    )
    print(f"Fetched {len(df)} records")
    print(df.head())

    # Example 2: Same request (should use cache)
    print("\n\nExample 2: Re-fetch same data (cache hit)")
    df2 = orchestrator.get_data(
        symbol="SBIN",
        exchange="NSE",
        start_date="2024-01-01",
        end_date="2024-01-31",
        interval=Interval.MINUTE_15
    )
    print(f"Returned {len(df2)} records from cache")

    # Example 3: Extended range (gap fetch)
    print("\n\nExample 3: Extended date range (gap fetch)")
    df3 = orchestrator.get_data(
        symbol="SBIN",
        exchange="NSE",
        start_date="2024-01-01",
        end_date="2024-02-29",
        interval=Interval.MINUTE_15
    )
    print(f"Returned {len(df3)} records (cache + new data)")

    # Example 4: Cache info
    print("\n\nExample 4: Cache info")
    info = orchestrator.get_cache_info()
    print(f"Total datasets: {info['total_datasets']}")
    print(f"Total records: {info['total_records']:,}")
    print(f"Symbols: {', '.join(info['symbols'])}")

    # Example 5: Batch fetch
    print("\n\nExample 5: Batch fetch")
    batch_data = orchestrator.get_data_batch(
        symbols=["INFY", "TCS"],
        exchange="NSE",
        start_date="2024-01-01",
        end_date="2024-01-31",
        interval=Interval.DAY
    )
    for symbol, df in batch_data.items():
        print(f"{symbol}: {len(df)} records")

    print("\n" + "=" * 80)
    print("Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
