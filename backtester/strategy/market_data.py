"""
Market Data Module - Immutable market data snapshot for strategies

This module provides the MarketData dataclass which represents OHLCV data
for a single bar with validation and convenience properties.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class  MarketData:
    """
    Immutable snapshot of market data for a single bar.

    Represents OHLCV data with optional additional fields like Open Interest and VWAP.
    All data is validated upon creation to ensure consistency.

    Attributes:
        symbol: Trading symbol (e.g., "SBIN", "RELIANCE")
        timestamp: Bar timestamp
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
        open_interest: Optional open interest (for derivatives)
        vwap: Optional volume-weighted average price
        is_trading_hours: Whether this bar occurred during trading hours
        is_complete: Whether this is a complete bar (not in progress)
    """
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: Optional[int] = None
    vwap: Optional[float] = None

    def __post_init__(self):
        """Validate price and volume relationships."""
        # Price validation
        if not (self.high >= self.low):
            raise ValueError(f"{self.symbol}: High ({self.high}) must be >= Low ({self.low})")

        if not (self.high >= self.open >= self.low):
            raise ValueError(f"{self.symbol}: Open ({self.open}) must be between High and Low")

        if not (self.high >= self.close >= self.low):
            raise ValueError(f"{self.symbol}: Close ({self.close}) must be between High and Low")

        # Volume validation
        if self.volume < 0:
            raise ValueError(f"{self.symbol}: Volume cannot be negative ({self.volume})")

        # Open Interest validation
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError(f"{self.symbol}: Open Interest cannot be negative ({self.open_interest})")

    @property
    def typical_price(self) -> float:
        """Calculate typical price: (High + Low + Close) / 3"""
        return (self.high + self.low + self.close) / 3

    @property
    def mid_price(self) -> float:
        """Calculate mid price: (High + Low) / 2"""
        return (self.high + self.low) / 2

    @property
    def price_range(self) -> float:
        """Calculate price range: High - Low"""
        return self.high - self.low

    @property
    def body_size(self) -> float:
        """Calculate candle body size: |Close - Open|"""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """Check if bar is bullish (Close > Open)"""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if bar is bearish (Close < Open)"""
        return self.close < self.open
