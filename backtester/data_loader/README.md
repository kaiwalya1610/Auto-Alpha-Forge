# Data Loader Module

Smart caching gateway for market data with automatic gap detection and incremental updates.

## Features

- **Cache-first retrieval**: Checks local cache before making API calls
- **Automatic gap detection**: Only fetches missing date ranges
- **Incremental updates**: Cached data grows over time as you request more dates
- **Simple structure**: One file per symbol+interval combination
- **Thread-safe**: Safe for concurrent access
- **Batch operations**: Fetch multiple symbols efficiently

## Installation

Make sure dependencies are installed:

```bash
pip install -r requirements.txt
```

## Quick Start

### Basic Usage

```python
from backtester.data_loader import DataOrchestrator, Interval

# Initialize (auto-authenticates with Zerodha)
orchestrator = DataOrchestrator()

# Fetch data - first call fetches from API and caches
df = orchestrator.get_data(
    symbol="SBIN",
    exchange="NSE",
    start_date="2024-01-01",
    end_date="2024-06-30",
    interval=Interval.MINUTE_15
)

print(f"Fetched {len(df)} candles")
print(df.head())
```

### Cache Behavior Examples

```python
# First call - fetches from API, caches data
df1 = orchestrator.get_data("SBIN", "NSE", "2024-01-01", "2024-03-31", Interval.DAY)
# Result: API call made, Jan-Mar cached

# Second call - same range, returns from cache instantly
df2 = orchestrator.get_data("SBIN", "NSE", "2024-01-01", "2024-03-31", Interval.DAY)
# Result: Instant return from cache

# Third call - extended range, only fetches gap
df3 = orchestrator.get_data("SBIN", "NSE", "2024-01-01", "2024-06-30", Interval.DAY)
# Result: Cache has Jan-Mar, only fetches Apr-Jun, merges automatically
```

### Batch Operations

```python
# Fetch multiple symbols at once
data = orchestrator.get_data_batch(
    symbols=["SBIN", "INFY", "TCS", "RELIANCE"],
    exchange="NSE",
    start_date="2024-01-01",
    end_date="2024-12-31",
    interval=Interval.MINUTE_15
)

# Access individual DataFrames
for symbol, df in data.items():
    print(f"{symbol}: {len(df)} records")
```

### Cache Management

```python
# Get cache statistics
info = orchestrator.get_cache_info()
print(f"Total cached datasets: {info['total_datasets']}")
print(f"Total records: {info['total_records']:,}")
print(f"Cached symbols: {', '.join(info['symbols'])}")

# Get info for specific symbol
sbin_info = orchestrator.get_cache_info(symbol="SBIN", exchange="NSE")
print(sbin_info)

# Clear specific cache
orchestrator.clear_cache(
    symbol="SBIN",
    exchange="NSE",
    interval=Interval.MINUTE_15
)

# Clear all cache
orchestrator.clear_cache()
```

### Include Open Interest

```python
# For F&O instruments
df = orchestrator.get_data(
    symbol="NIFTY24JANFUT",
    exchange="NFO",
    start_date="2024-01-01",
    end_date="2024-01-31",
    interval=Interval.MINUTE_15,
    oi=True  # Include open interest column
)
```

### Force Refresh

```python
# Ignore cache and fetch fresh data
df = orchestrator.get_data(
    symbol="SBIN",
    exchange="NSE",
    start_date="2024-01-01",
    end_date="2024-12-31",
    interval=Interval.DAY,
    force_refresh=True  # Bypass cache
)
```

## Cache Structure

Data is organized as:

```
backtester/data_loader/cache/
├── metadata.json                     # Central registry
├── SBIN/
│   └── NSE/
│       ├── 15minute/
│       │   └── data.csv             # All 15-min data for SBIN-NSE
│       └── day/
│           └── data.csv             # All daily data for SBIN-NSE
└── INFY/
    └── NSE/
        └── 15minute/
            └── data.csv
```

### Metadata Format

`metadata.json` tracks all cached datasets:

```json
{
  "SBIN_NSE_15minute": {
    "symbol": "SBIN",
    "exchange": "NSE",
    "interval": "15minute",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "records": 15234,
    "has_oi": false,
    "file_path": "SBIN/NSE/15minute/data.csv",
    "last_updated": "2025-11-01T10:30:00"
  }
}
```

## Available Intervals

From the `Interval` enum:

```python
# Minute intervals
Interval.MINUTE_1       # 1 minute
Interval.MINUTE_3       # 3 minutes
Interval.MINUTE_5       # 5 minutes
Interval.MINUTE_10      # 10 minutes
Interval.MINUTE_15      # 15 minutes
Interval.MINUTE_30      # 30 minutes

# Hour intervals
Interval.HOUR_1         # 1 hour
Interval.HOUR_2         # 2 hours
Interval.HOUR_3         # 3 hours
Interval.HOUR_4         # 4 hours

# Day interval
Interval.DAY            # Daily
```

## API Reference

### DataOrchestrator

#### `__init__(cache_dir=None, enctoken=None)`

Initialize orchestrator.

- `cache_dir`: Optional custom cache directory (default: `backtester/data_loader/cache`)
- `enctoken`: Optional Zerodha enctoken (auto-login if not provided)

#### `get_data(symbol, exchange, start_date, end_date, interval, oi=False, force_refresh=False)`

Get market data with smart caching.

**Returns**: DataFrame with columns `tradingsymbol`, `datetime`, `open`, `high`, `low`, `close`, `volume`, optionally `open_interest`

#### `get_data_batch(symbols, exchange, start_date, end_date, interval, oi=False, force_refresh=False)`

Fetch data for multiple symbols.

**Returns**: Dictionary mapping symbols to DataFrames

#### `get_cache_info(symbol=None, exchange=None)`

Get cache statistics.

**Returns**: Dictionary with cache information

#### `clear_cache(symbol=None, exchange=None, interval=None)`

Clear cached data (all or specific).

## How It Works

### Smart Caching Logic

1. **Request received**: `get_data("SBIN", "NSE", "2024-01-01", "2024-12-31", Interval.DAY)`

2. **Check cache**: Look for cached data in `SBIN/NSE/day/data.csv`

3. **Analyze coverage**:
   - **No cache**: Fetch entire range from API → Cache it
   - **Full coverage**: Return from cache (instant)
   - **Partial coverage**: Identify gaps → Fetch only gaps → Merge with cache → Update cache

4. **Return**: Filtered DataFrame for requested date range

### Gap Detection Example

```
Cached data:   [Jan 1 ========== Mar 31]
Requested:     [Jan 1 ======================== Jun 30]
Gap to fetch:                     [Apr 1 ====== Jun 30]
```

Only the gap (Apr-Jun) is fetched from the API, then merged with cached data (Jan-Mar).

## Demo Script

Run the included demo to see it in action:

```bash
python backtester/data_loader/DataOrchestrator.py
```

The demo will:
1. Fetch SBIN data (API call + cache)
2. Re-fetch same data (cache hit)
3. Extend date range (gap fetch + merge)
4. Show cache statistics
5. Batch fetch multiple symbols

## Notes

- Cache files grow over time as you request more date ranges
- Duplicate data is automatically removed during merges
- Thread-safe for concurrent access
- Metadata is updated atomically
- Failed API calls don't corrupt cache

## Integration with Backtesting

```python
from backtester.data_loader import DataOrchestrator, Interval

class MyStrategy:
    def __init__(self):
        self.data_loader = DataOrchestrator()

    def backtest(self, symbol, start_date, end_date):
        # Get data with automatic caching
        df = self.data_loader.get_data(
            symbol=symbol,
            exchange="NSE",
            start_date=start_date,
            end_date=end_date,
            interval=Interval.MINUTE_15
        )

        # Run strategy logic on df
        # ...
```
