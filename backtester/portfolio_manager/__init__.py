"""
Portfolio Manager Package

This package provides position and portfolio management capabilities for backtesting
and live trading.

Main Components:
- PortfolioManager: Main orchestrator for managing trading portfolio state
- Order: Represents trading orders with lifecycle management
- Position: Track open positions with real-time P&L calculation
- Transaction: Record completed trades with full audit trail
- EquityPoint: Portfolio value snapshots for equity curve tracking

Enums:
- TransactionType: BUY/SELL actions
- OrderType: MARKET, LIMIT, SL, SL-M
- OrderStatus: PENDING, OPEN, FILLED, PARTIAL, CANCELLED, REJECTED

Utilities:
- calculate_commission: Calculate trading fees
- calculate_slippage: Estimate market impact

Exceptions:
- PortfolioError: Base exception for all portfolio errors
- InsufficientFundsError: Not enough cash for purchase
- InvalidOrderError: Malformed order parameters
- PositionNotFoundError: Trying to sell non-existent position
- InsufficientPositionError: Trying to sell more than owned
"""

from .models import (
    Order,
    Position,
    Transaction,
    EquityPoint,
    TransactionType,
    OrderType,
    OrderStatus
)
from .utils import calculate_commission, calculate_slippage
from .exceptions import (
    PortfolioError,
    InsufficientFundsError,
    InvalidOrderError,
    PositionNotFoundError,
    InsufficientPositionError
)
from .portfolio_manager import PortfolioManager

__all__ = [
    # Main Manager
    'PortfolioManager',
    # Models
    'Order',
    'Position',
    'Transaction',
    'EquityPoint',
    # Enums
    'TransactionType',
    'OrderType',
    'OrderStatus',
    # Utilities
    'calculate_commission',
    'calculate_slippage',
    # Exceptions
    'PortfolioError',
    'InsufficientFundsError',
    'InvalidOrderError',
    'PositionNotFoundError',
    'InsufficientPositionError',
]

__version__ = '1.0.0'
