"""
Position Info Module - Read-only position snapshot for strategies

This module provides the PositionInfo dataclass which represents an immutable
snapshot of a trading position, preventing strategies from directly modifying positions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..portfolio_manager import Position


@dataclass(frozen=True)
class PositionInfo:
    """
    Read-only view of a position.

    This is NOT the Position object from PortfolioManager, but an immutable
    snapshot that prevents strategies from modifying positions directly.

    Attributes:
        symbol: Trading symbol
        quantity: Number of shares/contracts (positive for long, negative for short)
        entry_price: Average entry price
        current_price: Current market price
        entry_time: When the position was first opened
        market_value: Current market value (quantity * current_price)
        cost_basis: Total cost of position (quantity * entry_price)
        unrealized_pnl: Unrealized profit/loss
        unrealized_pnl_pct: Unrealized P&L as percentage of cost basis
    """
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_time: datetime
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    @classmethod
    def from_position(cls, position: 'Position', current_price: float, current_time: datetime) -> 'PositionInfo':
        """
        Create PositionInfo from a PortfolioManager Position object.

        Args:
            position: Position object from PortfolioManager
            current_price: Current market price for the symbol
            current_time: Current timestamp

        Returns:
            Immutable PositionInfo snapshot
        """
        market_value = position.quantity * current_price
        cost_basis = position.quantity * position.entry_price
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = (unrealized_pnl / abs(cost_basis) * 100) if cost_basis != 0 else 0.0

        return cls(
            symbol=position.symbol,
            quantity=position.quantity,
            entry_price=position.entry_price,
            current_price=current_price,
            entry_time=position.entry_timestamp,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct
        )

    @property
    def is_long(self) -> bool:
        """Check if this is a long position"""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if this is a short position"""
        return self.quantity < 0

    @property
    def abs_quantity(self) -> int:
        """Get absolute quantity (always positive)"""
        return abs(self.quantity)

    def holding_period(self, current_time: datetime) -> float:
        """
        Calculate holding period in days.

        Args:
            current_time: Current timestamp

        Returns:
            Holding period in days (fractional)
        """
        delta = current_time - self.entry_time
        return delta.total_seconds() / 86400.0  # Convert to days