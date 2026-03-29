"""
Portfolio Snapshot Module - Immutable portfolio state for strategies

This module provides the PortfolioSnapshot dataclass which represents a complete
read-only view of portfolio state at a specific point in time.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

from .position_info import PositionInfo

if TYPE_CHECKING:
    from ..portfolio_manager import PortfolioManager


@dataclass(frozen=True)
class PortfolioSnapshot:
    """
    Complete portfolio state at a specific point in time.

    Provides read-only access to portfolio metrics, cash, and positions.
    Immutable to prevent strategies from accidentally modifying state.

    Attributes:
        timestamp: Snapshot timestamp
        total_value: Total portfolio value (cash + positions)
        cash: Available cash
        positions_value: Total value of all positions
        realized_pnl: Cumulative realized profit/loss
        unrealized_pnl: Current unrealized profit/loss
        total_pnl: Total P&L (realized + unrealized)
        position_count: Number of open positions
        leverage: Portfolio leverage ratio
        positions: Dictionary of all positions {symbol: PositionInfo}
    """
    timestamp: datetime
    total_value: float
    cash: float
    positions_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    position_count: int
    leverage: float
    positions: Dict[str, PositionInfo] = field(default_factory=dict)

    @classmethod
    def from_portfolio_manager(
        cls,
        pm: 'PortfolioManager',
        current_prices: Dict[str, float],
        timestamp: datetime
    ) -> 'PortfolioSnapshot':
        """
        Create PortfolioSnapshot from PortfolioManager state.

        Args:
            pm: PortfolioManager instance
            current_prices: Dictionary of current prices {symbol: price}
            timestamp: Current timestamp

        Returns:
            Immutable PortfolioSnapshot
        """
        # Update prices and compute values directly (O(positions), not O(transactions))
        pm.update_prices(current_prices)
        positions_value = pm.get_positions_value()
        unrealized_pnl = pm.get_unrealized_pnl()
        total_value = pm.cash + positions_value

        # Convert positions to PositionInfo objects
        position_infos = {}
        for symbol, position in pm.positions.items():
            if symbol in current_prices:
                position_infos[symbol] = PositionInfo.from_position(
                    position=position,
                    current_price=current_prices[symbol],
                    current_time=timestamp
                )

        # Calculate leverage (total exposure / total value)
        total_exposure = sum(abs(pos.market_value) for pos in position_infos.values())
        leverage = total_exposure / total_value if total_value > 0 else 0.0

        return cls(
            timestamp=timestamp,
            total_value=total_value,
            cash=pm.cash,
            positions_value=positions_value,
            realized_pnl=0.0,  # Expensive to compute per-bar; use get_summary() at end
            unrealized_pnl=unrealized_pnl,
            total_pnl=unrealized_pnl,
            position_count=len(position_infos),
            leverage=leverage,
            positions=position_infos
        )

    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """
        Get position info for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            PositionInfo if position exists, None otherwise
        """
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """
        Check if portfolio has a position in the given symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if position exists, False otherwise
        """
        return symbol in self.positions

    @property
    def exposure(self) -> float:
        """Calculate total portfolio exposure (sum of absolute position values)"""
        return sum(abs(pos.market_value) for pos in self.positions.values())

    @property
    def long_exposure(self) -> float:
        """Calculate total long exposure"""
        return sum(pos.market_value for pos in self.positions.values() if pos.is_long)

    @property
    def short_exposure(self) -> float:
        """Calculate total short exposure (as positive number)"""
        return sum(abs(pos.market_value) for pos in self.positions.values() if pos.is_short)

    @property
    def net_exposure(self) -> float:
        """Calculate net exposure (long - short)"""
        return self.long_exposure - self.short_exposure