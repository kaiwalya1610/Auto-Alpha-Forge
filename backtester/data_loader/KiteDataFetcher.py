import requests
import datetime
import pandas as pd
import os
import sys
from enum import Enum
from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Add project root to Python path so we can import zerodha_login
# This file is in backtester/data_loader/, so we go up 2 levels to reach project root
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from zerodha_login import ZerodhaLogin
from kiteconnect import KiteConnect

class Interval(Enum):
    MINUTE_1 = 'minute'
    MINUTE_2 = '2minute'
    MINUTE_3 = '3minute'
    MINUTE_4 = '4minute'
    MINUTE_5 = '5minute'
    MINUTE_10 = '10minute'
    MINUTE_15 = '15minute'
    MINUTE_30 = '30minute'
    HOUR_1 = '60minute'
    HOUR_2 = '2hour'
    HOUR_3 = '3hour'
    HOUR_4 = '4hour'
    DAY = 'day'

class PyZData:
    """
    Historical data fetcher using KiteConnect SDK.

    Now uses official KiteConnect SDK for historical data retrieval (recommended).
    Legacy REST API methods preserved for backward compatibility.
    """

    ROOT_URL = "https://kite.zerodha.com/oms"  # Legacy REST API URL
    LOGIN_URL = "https://kite.zerodha.com/api/login"
    TWOFA_URL = "https://kite.zerodha.com/api/twofa"
    INSTRUMENTS_URL = "https://api.kite.trade/instruments"
    HISTORICAL_ENDPOINT = "/instruments/historical/{instrument_token}/{interval}"

    def __init__(self, enctoken=None, use_sdk=True):
        """
        Initialize PyZData historical data fetcher.

        Args:
            enctoken: Legacy enctoken for backward compatibility (deprecated)
            use_sdk: If True, uses KiteConnect SDK (recommended). If False, uses legacy REST API
        """
        self.use_sdk = use_sdk

        if enctoken is not None:
            # Use provided enctoken (backward compatibility with legacy REST API)
            self.use_sdk = False  # Force legacy mode
            self.session = requests.Session()
            self._init_retry_strategy()
            self.headers = {"Authorization": f"enctoken {enctoken}"}
            self.kite = None
            print(f"\n✅ Logged in with enctoken (legacy mode)\n")
        else:
            # Auto-login via ZerodhaLogin with SDK support
            auth = ZerodhaLogin(auto_login=True, auth_method="oauth")

            if self.use_sdk:
                # Use KiteConnect SDK (recommended)
                try:
                    self.kite = auth.get_kite_instance()
                    self.session = auth.get_session()  # Keep for instruments download
                    self.headers = auth.get_headers()
                    print(f"\n✅ Initialized with KiteConnect SDK\n")
                except Exception as e:
                    print(f"⚠️ Failed to initialize SDK: {e}")
                    print("⚠️ Falling back to legacy REST API")
                    self.use_sdk = False
                    self.kite = None
                    self.session = auth.get_session()
                    self.headers = auth.get_headers()
            else:
                # Legacy REST API mode
                self.kite = None
                self.session = auth.get_session()
                self.headers = auth.get_headers()
                print(f"\nℹ️ Using legacy REST API for historical data\n")

        self.instrument_data = self._load_instrument_data()
        
    def _init_retry_strategy(self):
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _load_instrument_data(self) -> pd.DataFrame:
        print("Loading instrument data from", self.INSTRUMENTS_URL)
        return pd.read_csv(self.INSTRUMENTS_URL)

    def get_instrument_token(self, tradingsymbol: str, exchange: str) -> int:
        
        condition = (
            (self.instrument_data['tradingsymbol'] == tradingsymbol) &
            (self.instrument_data['exchange'] == exchange)
        )
        result = self.instrument_data[condition]
        if result.empty:
            raise ValueError("Instrument token not found for the given symbol and exchange.")
        return int(result.iloc[0]['instrument_token'])

    def _get_trading_symbol(self, instrument_token: int) -> str:
        result = self.instrument_data[self.instrument_data['instrument_token'] == instrument_token]
        if result.empty:
            raise ValueError("Trading symbol not found for the given instrument token.")
        return result.iloc[0]['tradingsymbol']

    def _get_month_data(self, instrument_token: int, year: int, month: int, interval: Interval, oi: bool = False, print_logs: bool = False) -> pd.DataFrame:
        """
        Fetch historical data for a specific month using KiteConnect SDK.

        Args:
            instrument_token: Instrument token
            year: Year
            month: Month
            interval: Interval enum
            oi: Include open interest data
            print_logs: Print status logs

        Returns:
            DataFrame with OHLCV data
        """
        tradingsymbol = self._get_trading_symbol(instrument_token)
        from_date = pd.to_datetime(f"{year}-{month}-01")
        to_date = pd.to_datetime(f"{year}-{month}-{from_date.days_in_month}")
        to_date_extended = to_date + datetime.timedelta(days=5)

        if self.use_sdk:
            # Use official KiteConnect SDK (recommended)
            try:
                # SDK expects datetime objects and interval string
                candles = self.kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=from_date,
                    to_date=to_date_extended,
                    interval=interval.value,
                    oi=oi
                )

                if candles:
                    # SDK returns list of dicts: [{date, open, high, low, close, volume, oi}, ...]
                    data = pd.DataFrame(candles)

                    # Rename 'date' column to 'datetime' for consistency
                    data.rename(columns={'date': 'datetime'}, inplace=True)

                    # Add columns
                    columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
                    if oi and 'oi' in data.columns:
                        data.rename(columns={'oi': 'open_interest'}, inplace=True)
                        columns.append('open_interest')

                    data['tradingsymbol'] = tradingsymbol
                    data['datetime'] = pd.to_datetime(data['datetime'])
                    data = data[['tradingsymbol'] + columns]

                    # Filter to requested date range
                    data = data[(data['datetime'].dt.date >= from_date.date()) & (data['datetime'].dt.date <= to_date.date())]
                    data.drop_duplicates(inplace=True)
                    data.reset_index(drop=True, inplace=True)

                    if print_logs:
                        print(f"{tradingsymbol} data fetched (SDK): {from_date.date()} - {to_date.date()}")

                    return data

            except Exception as e:
                if print_logs:
                    print(f"Failed to fetch {tradingsymbol} data (SDK): {from_date.date()} - {to_date.date()} - {e}")
                return pd.DataFrame()

        else:
            # Legacy REST API method
            params = {
                "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
                "to": to_date_extended.strftime("%Y-%m-%d %H:%M:%S"),
                "oi": int(oi)
            }

            url = f"{self.ROOT_URL}{self.HISTORICAL_ENDPOINT.format(instrument_token=instrument_token, interval=interval.value)}"
            response = self.session.get(url, params=params, headers=self.headers)

            if response.ok:
                response_json = response.json()
                if response_json.get('status') == 'success':
                    data = pd.DataFrame(response_json['data']['candles'])
                    if not data.empty:
                        columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
                        if oi:
                            columns.append('open_interest')
                        data.columns = columns
                        data['tradingsymbol'] = tradingsymbol
                        data['datetime'] = pd.to_datetime(data['datetime'])
                        data['datetime'] = data['datetime'].apply(lambda x: pd.Timestamp.combine(x.date(), x.time()))
                        data = data[['tradingsymbol'] + columns]
                        data = data[(data['datetime'].dt.date >= from_date.date()) & (data['datetime'].dt.date <= to_date.date())]
                        data.drop_duplicates(inplace=True)
                        data.reset_index(drop=True, inplace=True)

                        if print_logs:
                            print(f"{tradingsymbol} data fetched: {from_date.date()} - {to_date.date()}")

                        return data
            else:
                if print_logs:
                    print(f"Failed to fetch {tradingsymbol} data: {from_date.date()} - {to_date.date()}")

        return pd.DataFrame()

    def get_data(self, instrument_token, start_date, end_date, interval: Interval, oi: bool = False, print_logs: bool = False ) -> pd.DataFrame:

        from_date = pd.to_datetime(start_date)
        to_date = pd.to_datetime(end_date)

        all_data = []
        
        current = from_date.replace(day=1)
        while current <= to_date:
            
            year, month = current.year, current.month
            
            df = self._get_month_data(instrument_token=instrument_token, year=year, month=month, interval=interval, oi=oi, print_logs=print_logs)

            if not df.empty:
                df = df[(df['datetime'].dt.date >= from_date.date()) & (df['datetime'].dt.date <= to_date.date())]
                all_data.append(df)

            current = pd.Timestamp(year=current.year, month=current.month, day=1)
            current = current + pd.Timedelta(days=current.days_in_month)

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            final_df.drop_duplicates(inplace=True)
            final_df.reset_index(drop=True, inplace=True)
            return final_df

        return pd.DataFrame()


def load_nifty_500_from_csv(csv_path: str = "ind_nifty500list.csv") -> pd.DataFrame:
    """
    Load Nifty 500 stocks from the provided CSV file.
    
    Args:
        csv_path: Path to the CSV file containing Nifty 500 list
        
    Returns:
        DataFrame with Symbol column
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    print(f"✅ Loaded {len(df)} stocks from {csv_path}")
    
    return df


def get_nifty_500_stocks(instrument_data: pd.DataFrame, nifty_500_df: pd.DataFrame) -> list:
    """
    Get list of Nifty 500 stocks with their instrument tokens.
    
    Args:
        instrument_data: DataFrame from Zerodha instruments API
        nifty_500_df: DataFrame loaded from ind_nifty500list.csv
        
    Returns:
        List of tuples: [(symbol, instrument_token), ...]
    """
    nifty_symbols = nifty_500_df['Symbol'].tolist()
    
    # Filter instrument data for NSE equities matching Nifty 500 symbols
    matched_stocks = instrument_data[
        (instrument_data['exchange'] == 'NSE') & 
        (instrument_data['tradingsymbol'].isin(nifty_symbols))
    ].copy()
    
    print(f"✅ Matched {len(matched_stocks)} stocks from instrument data")
    
    return matched_stocks[['tradingsymbol', 'instrument_token']].values.tolist()


def main():
    """
    Main function to fetch 15-minute interval data for Nifty 500 stocks
    for the last 1 year and save to CSV with OI and Volume.
    """
    print("=" * 80)
    print("🚀 Starting Nifty 500 Data Collection")
    print("=" * 80)
    
    # Create output directory
    output_dir = "nifty500_data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"📁 Created output directory: {output_dir}\n")
    else:
        print(f"📁 Output directory: {output_dir}\n")
    
    # Load Nifty 500 symbols from CSV
    print("📄 Loading Nifty 500 symbols from CSV...")
    try:
        nifty_500_df = load_nifty_500_from_csv("ind_nifty500list.csv")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return
    
    # Initialize PyZData with auto-login
    print("\n📡 Initializing connection...")
    kite = PyZData()
    
    # Get Nifty 500 stocks with instrument tokens
    print("\n📊 Matching symbols with instrument tokens...")
    nifty_500_stocks = get_nifty_500_stocks(kite.instrument_data, nifty_500_df)
    print(f"✅ Found {len(nifty_500_stocks)} stocks to process\n")
    
    # Calculate date range - last 1 year
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=365)
    
    print(f"📅 Date Range: {start_date.date()} to {end_date.date()}")
    print(f"⏱️  Interval: 15 minutes")
    print(f"📊 Data: OHLC + Volume + OI (where applicable)\n")
    print("=" * 80)
    
    # Collect all data
    all_stocks_data = []
    failed_stocks = []
    
    for idx, (symbol, token) in enumerate(nifty_500_stocks, 1):
        try:
            print(f"[{idx}/{len(nifty_500_stocks)}] 📥 Fetching {symbol}...", end=" ")
            
            # Try with OI first (for F&O stocks), if fails, retry without OI
            df = None
            try:
                df = kite.get_data(
                    instrument_token=int(token),
                    start_date=start_date,
                    end_date=end_date,
                    interval=Interval.MINUTE_15,
                    oi=True,  # Enable OI
                    print_logs=False
                )
            except Exception:
                # If OI fetch fails, try without OI (for non-F&O stocks)
                df = kite.get_data(
                    instrument_token=int(token),
                    start_date=start_date,
                    end_date=end_date,
                    interval=Interval.MINUTE_15,
                    oi=False,
                    print_logs=False
                )
            
            if not df.empty:
                all_stocks_data.append(df)
                has_oi = 'open_interest' in df.columns
                print(f"✅ {len(df)} candles {'(with OI)' if has_oi else '(no OI)'}")
            else:
                print(f"⚠️  No data")
                failed_stocks.append(symbol)
                
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            failed_stocks.append(symbol)
            continue
    
    print("\n" + "=" * 80)
    print("💾 Saving data to CSV...")
    
    if all_stocks_data:
        # Combine all dataframes
        final_df = pd.concat(all_stocks_data, ignore_index=True)
        final_df = final_df.sort_values(['tradingsymbol', 'datetime']).reset_index(drop=True)
        
        # Save to CSV with timestamp in the output directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(output_dir, f"nifty500_15min_data_{timestamp}.csv")
        final_df.to_csv(filename, index=False)
        
        print(f"✅ Data saved successfully!")
        print(f"\n📁 File: {filename}")
        print(f"📊 Total Records: {len(final_df):,}")
        print(f"📈 Stocks with data: {len(all_stocks_data)}")
        print(f"❌ Failed stocks: {len(failed_stocks)}")
        
        if failed_stocks:
            print(f"\n⚠️  Failed stocks: {', '.join(failed_stocks[:10])}")
            if len(failed_stocks) > 10:
                print(f"   ... and {len(failed_stocks) - 10} more")
        
        print("\n📊 Data Summary:")
        print(f"   Columns: {', '.join(final_df.columns.tolist())}")
        print(f"   Date Range: {final_df['datetime'].min()} to {final_df['datetime'].max()}")
        print(f"   Unique Stocks: {final_df['tradingsymbol'].nunique()}")
        
        # Check if OI data is available
        if 'open_interest' in final_df.columns:
            stocks_with_oi = final_df[final_df['open_interest'].notna()]['tradingsymbol'].nunique()
            print(f"   Stocks with OI data: {stocks_with_oi}")
        
        print("\n📌 Sample Data (First 5 rows):")
        print(final_df.head())
        
    else:
        print("❌ No data collected!")
    
    print("\n" + "=" * 80)
    print("🎉 Process Completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()