"""
Portfolio Manager Models

This module defines core data structures for portfolio and position management:
- Order: Represents a trading order (instruction to buy/sell, may not be executed yet)
- Position: Represents an open position in a security
- Transaction: Represents a completed trade (buy/sell)
- EquityPoint: Represents a portfolio value snapshot at a specific moment in time
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class TransactionType(Enum):
    """Enum for transaction types"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Enum for order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"  # Stop-loss limit
    SL_M = "SL-M"  # Stop-loss market


class OrderStatus(Enum):
    """Enum for order status"""
    PENDING = "PENDING"  # Created but not sent to exchange yet
    OPEN = "OPEN"  # Placed with exchange, waiting for execution
    FILLED = "FILLED"  # Completely executed
    PARTIAL = "PARTIAL"  # Partially filled
    CANCELLED = "CANCELLED"  # Cancelled by user
    REJECTED = "REJECTED"  # Rejected by exchange/broker


@dataclass
class Order:
    """
    Represents a trading order (instruction to buy or sell).

    An order is a trading intention that may or may not be executed yet.
    Tracks order lifecycle from creation through execution or cancellation.

    Attributes:
        symbol: Stock symbol to trade (e.g., "SBIN", "RELIANCE")
        action: Buy or sell (use TransactionType.BUY or TransactionType.SELL)
        quantity: Number of shares to trade
        order_type: Type of order (MARKET, LIMIT, SL, SL-M)
        timestamp: When the order was created
        limit_price: Limit price for LIMIT and SL orders (required for those types)
        stop_price: Stop/trigger price for SL and SL-M orders (required for those types)
        order_id: Unique identifier for this order
        status: Current order status (PENDING, OPEN, FILLED, etc.)
        exchange: Exchange where order will be placed (e.g., "NSE", "BSE")
        notes: Optional notes about the order
        filled_quantity: How many shares have been executed (for partial fills)
        average_fill_price: Average price at which order was filled
        position_stop_loss: Stop-loss price for the position created by this order
        position_target: Target price for the position created by this order
    """

    symbol: str
    action: TransactionType
    quantity: int
    order_type: OrderType
    timestamp: datetime
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    exchange: str = "NSE"
    notes: str = ""
    filled_quantity: int = 0
    average_fill_price: Optional[float] = None
    position_stop_loss: Optional[float] = None
    position_target: Optional[float] = None

    def __post_init__(self):
        """Validate order data and generate ID if not provided"""
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")

        if self.order_type in (OrderType.LIMIT, OrderType.SL):
            if self.limit_price is None:
                raise ValueError(f"{self.order_type.value} orders must have a limit_price")
            if self.limit_price <= 0:
                raise ValueError(f"Limit price must be positive, got {self.limit_price}")

        if self.order_type in (OrderType.SL, OrderType.SL_M):
            if self.stop_price is None:
                raise ValueError(f"{self.order_type.value} orders must have a stop_price")
            if self.stop_price <= 0:
                raise ValueError(f"Stop price must be positive, got {self.stop_price}")

        if self.order_id is None:
            self.order_id = self._generate_order_id()

    def _generate_order_id(self) -> str:
        """
        Generate a unique order ID based on timestamp and details.

        Returns:
            Unique order identifier
        """
        timestamp_str = self.timestamp.strftime("%Y%m%d%H%M%S%f")
        return f"ORD{self.action.value[:1]}{timestamp_str}_{self.symbol}"

    @property
    def is_filled(self) -> bool:
        """
        Check if order is completely filled.

        Returns:
            True if status is FILLED, False otherwise
        """
        return self.status == OrderStatus.FILLED

    @property
    def is_pending(self) -> bool:
        """
        Check if order is still pending (not sent to exchange).

        Returns:
            True if status is PENDING, False otherwise
        """
        return self.status == OrderStatus.PENDING

    @property
    def is_active(self) -> bool:
        """
        Check if order is still active (can still be executed).

        Returns:
            True if order is PENDING, OPEN, or PARTIAL, False otherwise
        """
        return self.status in (OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIAL)

    @property
    def is_closed(self) -> bool:
        """
        Check if order is closed (no further execution possible).

        Returns:
            True if order is FILLED, CANCELLED, or REJECTED, False otherwise
        """
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

    @property
    def remaining_quantity(self) -> int:
        """
        Calculate remaining quantity to be filled.

        Returns:
            Number of shares still to be executed
        """
        return self.quantity - self.filled_quantity

    @property
    def fill_percentage(self) -> float:
        """
        Calculate what percentage of the order has been filled.

        Returns:
            Percentage filled (0-100)
        """
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100

    def update_status(self, new_status: OrderStatus) -> None:
        """
        Update the order status.

        Args:
            new_status: New status to set

        Raises:
            ValueError: If trying to update a closed order
        """
        if self.is_closed and new_status != self.status:
            raise ValueError(
                f"Cannot update status of closed order (current: {self.status.value})"
            )
        self.status = new_status

    def add_fill(self, filled_qty: int, fill_price: float) -> None:
        """Record a partial or complete fill of the order."""
        new_filled = self.filled_quantity + filled_qty

        # Update average fill price
        if self.average_fill_price is None:
            self.average_fill_price = fill_price
        else:
            # Weighted average
            total_value = (self.filled_quantity * self.average_fill_price) + (filled_qty * fill_price)
            self.average_fill_price = total_value / new_filled

        # Update filled quantity
        self.filled_quantity = new_filled

        # Update status
        if self.filled_quantity == self.quantity:
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIAL

    def cancel(self) -> None:
        """
        Cancel the order.

        Raises:
            ValueError: If order is already closed
        """
        if self.is_closed:
            raise ValueError(f"Cannot cancel order with status {self.status.value}")
        self.status = OrderStatus.CANCELLED

    def get_summary(self) -> dict:
        """
        Get complete order details.

        Returns:
            Dictionary containing all order information
        """
        summary = {
            'order_id': self.order_id,
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'exchange': self.exchange,
            'action': self.action.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.remaining_quantity,
            'fill_percentage': round(self.fill_percentage, 2),
            'status': self.status.value,
            'notes': self.notes
        }

        if self.limit_price is not None:
            summary['limit_price'] = round(self.limit_price, 2)

        if self.stop_price is not None:
            summary['stop_price'] = round(self.stop_price, 2)

        if self.average_fill_price is not None:
            summary['average_fill_price'] = round(self.average_fill_price, 2)

        return summary

    def __str__(self) -> str:
        """String representation for easy debugging"""
        type_info = f"{self.order_type.value}"

        # Add price info based on order type
        price_parts = []
        if self.limit_price is not None:
            price_parts.append(f"Limit: Rs.{self.limit_price:.2f}")
        if self.stop_price is not None:
            price_parts.append(f"Stop: Rs.{self.stop_price:.2f}")

        price_info = f" ({', '.join(price_parts)})" if price_parts else ""

        # Add fill info if partially or fully filled
        fill_info = ""
        if self.filled_quantity > 0:
            fill_info = f", Filled: {self.filled_quantity}/{self.quantity}"
            if self.average_fill_price:
                fill_info += f" @ Rs.{self.average_fill_price:.2f}"

        return (
            f"Order({self.action.value} {self.quantity} {self.symbol} {self.exchange} "
            f"{type_info}{price_info}, Status: {self.status.value}{fill_info}, "
            f"ID: {self.order_id})"
        )

    def __repr__(self) -> str:
        return (
            f"Order(symbol={self.symbol!r}, action={self.action}, "
            f"quantity={self.quantity}, order_type={self.order_type}, "
            f"status={self.status}, order_id={self.order_id!r})"
        )


@dataclass
class Position:
    """
    Represents an open position in a security (long or short).

    Tracks all information about a holding including entry details, current state,
    and automatically calculates profit/loss metrics.

    Supports both LONG and SHORT positions:
    - LONG: quantity > 0 (you own the stock)
    - SHORT: quantity < 0 (you've borrowed and sold the stock)

    Attributes:
        symbol: Stock symbol (e.g., "SBIN", "RELIANCE")
        quantity: Number of shares (positive=long, negative=short)
        entry_price: Price per share at which position was opened
        entry_timestamp: When the position was opened
        current_price: Current market price per share
        exchange: Exchange where the security is traded (e.g., "NSE", "BSE")
        stop_loss_price: Optional stop-loss price for automatic exit
        target_price: Optional target price for automatic exit
    """

    symbol: str
    quantity: int
    entry_price: float
    entry_timestamp: datetime
    current_price: float
    exchange: str = "NSE"
    stop_loss_price: Optional[float] = None
    target_price: Optional[float] = None

    def __post_init__(self):
        """Validate position data after initialization"""
        if self.quantity == 0:
            raise ValueError(f"Quantity cannot be zero, got {self.quantity}")
        if self.entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {self.entry_price}")
        if self.current_price <= 0:
            raise ValueError(f"Current price must be positive, got {self.current_price}")

    @property
    def is_long(self) -> bool:
        """
        Check if this is a long position.

        Returns:
            True if quantity > 0 (long position), False otherwise
        """
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """
        Check if this is a short position.

        Returns:
            True if quantity < 0 (short position), False otherwise
        """
        return self.quantity < 0

    @property
    def market_value(self) -> float:
        """
        Current market value of the position.

        For LONG positions: positive value (you own shares)
        For SHORT positions: negative value (you owe shares - liability)

        Returns:
            Current value (quantity × current_price)
        """
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """
        Original cost of the position.

        For LONG positions: positive value (what you paid)
        For SHORT positions: negative value (cash received when shorted)

        Returns:
            Total amount invested (quantity × entry_price)
        """
        return self.quantity * self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        """
        Unrealized profit/loss in absolute currency terms.

        Works for both LONG and SHORT positions:
        - LONG: profit when current_price > entry_price
        - SHORT: profit when current_price < entry_price

        Returns:
            Profit (positive) or loss (negative)
        """
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        """
        Unrealized profit/loss as a percentage.

        For both LONG and SHORT positions, calculates return based on
        absolute value of initial investment.

        Returns:
            Percentage return (e.g., 15.5 for 15.5% gain, -10.0 for 10% loss)
        """
        if self.cost_basis == 0:
            return 0.0
        # Use abs(cost_basis) for shorts to get correct sign
        return (self.unrealized_pnl / abs(self.cost_basis)) * 100

    @property
    def is_profitable(self) -> bool:
        """
        Quick check if position is currently profitable.

        Works for both LONG and SHORT positions:
        - LONG: profitable when current_price > entry_price
        - SHORT: profitable when current_price < entry_price

        Returns:
            True if position has positive unrealized P&L, False otherwise
        """
        return self.unrealized_pnl > 0

    def update_price(self, new_price: float) -> None:
        """Update the current market price of the position."""
        self.current_price = new_price

    def get_summary(self) -> dict:
        """
        Get a complete summary of the position.

        Returns:
            Dictionary containing all position details and metrics
        """
        return {
            'symbol': self.symbol,
            'exchange': self.exchange,
            'quantity': self.quantity,
            'entry_price': round(self.entry_price, 2),
            'current_price': round(self.current_price, 2),
            'entry_timestamp': self.entry_timestamp.isoformat(),
            'cost_basis': round(self.cost_basis, 2),
            'market_value': round(self.market_value, 2),
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'unrealized_pnl_pct': round(self.unrealized_pnl_pct, 2),
            'is_profitable': self.is_profitable
        }

    def __str__(self) -> str:
        """String representation for easy debugging"""
        pnl_sign = '+' if self.unrealized_pnl >= 0 else ''
        return (
            f"Position({self.symbol} {self.exchange}: {self.quantity} shares @ "
            f"Rs.{self.entry_price:.2f} -> Rs.{self.current_price:.2f}, "
            f"P&L: {pnl_sign}Rs.{self.unrealized_pnl:.2f} ({pnl_sign}{self.unrealized_pnl_pct:.2f}%))"
        )

    def __repr__(self) -> str:
        return (
            f"Position(symbol={self.symbol!r}, quantity={self.quantity}, "
            f"entry_price={self.entry_price}, current_price={self.current_price})"
        )


@dataclass
class Transaction:
    """
    Represents a completed trade (buy or sell that already happened).

    Provides complete audit trail with all trade details including costs.

    Attributes:
        timestamp: When the trade was executed
        symbol: Stock symbol traded
        action: Buy or sell (use TransactionType.BUY or TransactionType.SELL)
        quantity: Number of shares traded
        price: Price per share
        commission: Brokerage commission paid
        slippage_pct: Slippage as percentage of price (e.g., 0.5 for 0.5%)
        transaction_id: Unique identifier for this transaction
        exchange: Exchange where trade was executed
        notes: Optional notes about the trade
    """

    timestamp: datetime
    symbol: str
    action: TransactionType
    quantity: int
    price: float
    commission: float = 0.0
    slippage_pct: float = 0.0
    transaction_id: Optional[str] = None
    exchange: str = "NSE"
    notes: str = ""

    def __post_init__(self):
        """Validate transaction data and generate ID if not provided"""
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.price <= 0:
            raise ValueError(f"Price must be positive, got {self.price}")
        if self.commission < 0:
            raise ValueError(f"Commission cannot be negative, got {self.commission}")
        if self.slippage_pct < 0:
            raise ValueError(f"Slippage percentage cannot be negative, got {self.slippage_pct}")
        if self.slippage_pct > 100:
            raise ValueError(f"Slippage percentage cannot exceed 100%, got {self.slippage_pct}")

        # Generate transaction ID if not provided
        if self.transaction_id is None:
            self.transaction_id = self._generate_transaction_id()

    def _generate_transaction_id(self) -> str:
        """
        Generate a unique transaction ID based on timestamp and details.

        Returns:
            Unique transaction identifier
        """
        timestamp_str = self.timestamp.strftime("%Y%m%d%H%M%S%f")
        return f"{self.action.value[:1]}{timestamp_str}_{self.symbol}"

    @classmethod
    def create_with_fees(
        cls,
        timestamp: datetime,
        symbol: str,
        action: TransactionType,
        quantity: int,
        price: float,
        commission_rate: float,
        slippage_rate: float,
        minimum_commission: float = 1.0,
        exchange: str = "NSE",
        notes: str = "",
        transaction_id: Optional[str] = None
    ) -> 'Transaction':
        """
        Factory method to create a Transaction with automatic fee calculation.

        This method integrates with the utils module to calculate commission and
        slippage based on rates, providing a cleaner interface for transaction creation.

        Args:
            timestamp: When the trade was executed
            symbol: Stock symbol traded
            action: Buy or sell (TransactionType.BUY or TransactionType.SELL)
            quantity: Number of shares traded
            price: Price per share
            commission_rate: Commission rate as decimal (e.g., 0.0003 for 0.03%)
            slippage_rate: Slippage rate as decimal (e.g., 0.0005 for 0.05%)
            minimum_commission: Minimum commission to charge (default: Rs.1.0)
            exchange: Exchange where trade was executed (default: "NSE")
            notes: Optional notes about the trade
            transaction_id: Optional custom transaction ID

        Returns:
            Transaction instance with calculated fees

        Example:
            >>> tx = Transaction.create_with_fees(
            ...     timestamp=datetime.now(),
            ...     symbol="SBIN",
            ...     action=TransactionType.BUY,
            ...     quantity=100,
            ...     price=550.0,
            ...     commission_rate=0.0003,  # 0.03%
            ...     slippage_rate=0.0005     # 0.05%
            ... )
            >>> print(f"Commission: Rs.{tx.commission:.2f}")
            >>> print(f"Slippage: Rs.{tx.slippage:.2f}")
        """
        from backtester.portfolio_manager.utils import calculate_commission, calculate_slippage

        # Calculate fees using utils functions
        commission = calculate_commission(
            quantity=quantity,
            price_per_share=price,
            commission_rate=commission_rate,
            minimum_commission=minimum_commission
        )

        slippage_amount = calculate_slippage(
            quantity=quantity,
            price=price,
            slippage_rate=slippage_rate
        )

        # Convert slippage amount to percentage for storage
        gross_amount = quantity * price
        slippage_pct = (slippage_amount / gross_amount * 100) if gross_amount > 0 else 0.0

        # Create and return Transaction instance
        return cls(
            timestamp=timestamp,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            commission=commission,
            slippage_pct=slippage_pct,
            transaction_id=transaction_id,
            exchange=exchange,
            notes=notes
        )

    @property
    def gross_amount(self) -> float:
        """
        Gross transaction amount before any fees.

        Returns:
            Total value (quantity × price)
        """
        return self.quantity * self.price

    @property
    def slippage(self) -> float:
        """
        Calculated slippage amount based on percentage and price.

        Returns:
            Slippage cost (gross_amount × slippage_pct / 100)
        """
        return self.gross_amount * (self.slippage_pct / 100)

    @property
    def total_fees(self) -> float:
        """
        Total fees paid for this transaction.

        Returns:
            Sum of all fees (commission + slippage)
        """
        return self.commission + self.slippage

    @property
    def net_amount(self) -> float:
        """
        Net transaction amount after all fees.

        For BUY: gross_amount + fees (total cash outflow)
        For SELL: gross_amount - fees (net cash inflow)

        Returns:
            Net amount after fees
        """
        if self.action == TransactionType.BUY:
            return self.gross_amount + self.total_fees
        else:  # SELL
            return self.gross_amount - self.total_fees

    @property
    def effective_price(self) -> float:
        """
        Effective price per share after including all fees.

        Returns:
            Actual cost/proceeds per share after fees
        """
        return self.net_amount / self.quantity

    def get_summary(self) -> dict:
        """
        Get complete transaction details.

        Returns:
            Dictionary containing all transaction information
        """
        return {
            'transaction_id': self.transaction_id,
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'exchange': self.exchange,
            'action': self.action.value,
            'quantity': self.quantity,
            'price': round(self.price, 2),
            'gross_amount': round(self.gross_amount, 2),
            'commission': round(self.commission, 2),
            'slippage_pct': round(self.slippage_pct, 2),
            'slippage': round(self.slippage, 2),
            'total_fees': round(self.total_fees, 2),
            'net_amount': round(self.net_amount, 2),
            'effective_price': round(self.effective_price, 2),
            'notes': self.notes
        }

    def __str__(self) -> str:
        """String representation for easy debugging"""
        return (
            f"Transaction({self.action.value} {self.quantity} {self.symbol} @ "
            f"Rs.{self.price:.2f}, Net: Rs.{self.net_amount:.2f}, "
            f"Fees: Rs.{self.total_fees:.2f}, ID: {self.transaction_id})"
        )

    def __repr__(self) -> str:
        return (
            f"Transaction(symbol={self.symbol!r}, action={self.action}, "
            f"quantity={self.quantity}, price={self.price}, "
            f"transaction_id={self.transaction_id!r})"
        )


@dataclass
class EquityPoint:
    """
    Represents a snapshot of portfolio value at a specific moment in time.

    Used to build equity curves for performance tracking and visualization.
    Each point captures the complete state of portfolio value.

    Attributes:
        timestamp: When this snapshot was taken
        cash: Cash available in the portfolio
        positions_value: Combined market value of all open positions
    """

    timestamp: datetime
    cash: float
    positions_value: float

   

    @property
    def total_value(self) -> float:
        """
        Total portfolio value (cash + positions).

        Returns:
            Total portfolio value at this point in time
        """
        return self.cash + self.positions_value

    @property
    def positions_percentage(self) -> float:
        """
        Percentage of portfolio allocated to positions.

        Returns:
            Percentage of total value in positions (0-100)
        """
        if self.total_value == 0:
            return 0.0
        return (self.positions_value / self.total_value) * 100

    @property
    def cash_percentage(self) -> float:
        """
        Percentage of portfolio held as cash.

        Returns:
            Percentage of total value in cash (0-100)
        """
        if self.total_value == 0:
            return 0.0
        return (self.cash / self.total_value) * 100

    def get_summary(self) -> dict:
        """
        Get complete equity point details.

        Returns:
            Dictionary containing all equity point information
        """
        return {
            'timestamp': self.timestamp.isoformat(),
            'cash': round(self.cash, 2),
            'positions_value': round(self.positions_value, 2),
            'total_value': round(self.total_value, 2),
            'cash_percentage': round(self.cash_percentage, 2),
            'positions_percentage': round(self.positions_percentage, 2)
        }

    def __str__(self) -> str:
        """String representation for easy debugging"""
        return (
            f"EquityPoint({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
            f"Total=Rs.{self.total_value:,.2f}, Cash=Rs.{self.cash:,.2f} "
            f"({self.cash_percentage:.1f}%), Positions=Rs.{self.positions_value:,.2f} "
            f"({self.positions_percentage:.1f}%))"
        )

    def __repr__(self) -> str:
        return (
            f"EquityPoint(timestamp={self.timestamp!r}, cash={self.cash}, "
            f"positions_value={self.positions_value})"
        )

# Example usage and testing
if __name__ == "__main__":
    from datetime import datetime

    # Example 1: Create an Order - Market Order
    print("=" * 80)
    print("ORDER EXAMPLES")
    print("=" * 80)

    # 1a. Market Order
    print("\n--- Market Order ---")
    market_order = Order(
        symbol="SBIN",
        action=TransactionType.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        timestamp=datetime(2024, 1, 15, 9, 15, 30),
        exchange="NSE",
        notes="Buy at market price"
    )

    print(market_order)
    print(f"Is Active: {market_order.is_active}")
    print(f"Is Pending: {market_order.is_pending}")
    print(f"Remaining Quantity: {market_order.remaining_quantity}")

    # Simulate order execution
    print("\n--- Simulating Full Fill ---")
    market_order.update_status(OrderStatus.OPEN)  # Order sent to exchange
    market_order.add_fill(100, 550.50)  # Filled completely
    print(market_order)
    print(f"Is Filled: {market_order.is_filled}")
    print(f"Average Fill Price: Rs.{market_order.average_fill_price:.2f}")

    # 1b. Limit Order
    print("\n--- Limit Order ---")
    limit_order = Order(
        symbol="RELIANCE",
        action=TransactionType.BUY,
        quantity=50,
        order_type=OrderType.LIMIT,
        timestamp=datetime(2024, 1, 15, 9, 20, 0),
        limit_price=2450.00,
        exchange="NSE",
        notes="Buy only if price drops to 2450"
    )

    print(limit_order)
    print("\nOrder Summary:")
    for key, value in limit_order.get_summary().items():
        print(f"  {key}: {value}")

    # 1c. Stop-Loss Order
    print("\n--- Stop-Loss Order ---")
    sl_order = Order(
        symbol="TCS",
        action=TransactionType.SELL,
        quantity=25,
        order_type=OrderType.SL,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        stop_price=3400.00,
        limit_price=3395.00,
        exchange="NSE",
        notes="Exit if price falls below 3400"
    )

    print(sl_order)

    # 1d. Partial Fill Scenario
    print("\n--- Partial Fill Scenario ---")
    large_order = Order(
        symbol="INFY",
        action=TransactionType.BUY,
        quantity=1000,
        order_type=OrderType.LIMIT,
        timestamp=datetime(2024, 1, 15, 11, 0, 0),
        limit_price=1450.00,
        exchange="NSE",
        notes="Large order - may fill partially"
    )

    print(large_order)
    large_order.update_status(OrderStatus.OPEN)

    # First partial fill
    print("\n--- First Partial Fill: 300 shares @ Rs.1449.50 ---")
    large_order.add_fill(300, 1449.50)
    print(large_order)
    print(f"Fill Percentage: {large_order.fill_percentage:.2f}%")
    print(f"Remaining: {large_order.remaining_quantity} shares")

    # Second partial fill
    print("\n--- Second Partial Fill: 400 shares @ Rs.1450.00 ---")
    large_order.add_fill(400, 1450.00)
    print(large_order)
    print(f"Fill Percentage: {large_order.fill_percentage:.2f}%")
    print(f"Average Fill Price: Rs.{large_order.average_fill_price:.2f}")

    # Complete the order
    print("\n--- Final Fill: 300 shares @ Rs.1450.25 ---")
    large_order.add_fill(300, 1450.25)
    print(large_order)
    print(f"Is Filled: {large_order.is_filled}")
    print(f"Final Average Fill Price: Rs.{large_order.average_fill_price:.2f}")

    # 1e. Cancelled Order
    print("\n--- Cancelled Order ---")
    cancelled_order = Order(
        symbol="WIPRO",
        action=TransactionType.BUY,
        quantity=200,
        order_type=OrderType.LIMIT,
        timestamp=datetime(2024, 1, 15, 14, 0, 0),
        limit_price=420.00,
        exchange="NSE",
        notes="Cancel if not filled by 3 PM"
    )

    print(cancelled_order)
    cancelled_order.update_status(OrderStatus.OPEN)
    cancelled_order.cancel()
    print(f"\nAfter cancellation: {cancelled_order}")
    print(f"Is Closed: {cancelled_order.is_closed}")

    # Example 2: Create a Position
    print("\n" + "=" * 80)
    print("POSITION EXAMPLE")
    print("=" * 80)

    position = Position(
        symbol="SBIN",
        quantity=100,
        entry_price=550.0,
        entry_timestamp=datetime(2024, 1, 15, 9, 30),
        current_price=575.0,
        exchange="NSE"
    )

    print(position)
    print(f"\nMarket Value: Rs.{position.market_value:,.2f}")
    print(f"Cost Basis: Rs.{position.cost_basis:,.2f}")
    print(f"Unrealized P&L: Rs.{position.unrealized_pnl:,.2f} ({position.unrealized_pnl_pct:.2f}%)")
    print(f"Is Profitable: {position.is_profitable}")

    print("\nFull Summary:")
    for key, value in position.get_summary().items():
        print(f"  {key}: {value}")

    # Update price and see changes
    print("\n--- After price update to Rs.540 ---")
    position.update_price(540.0)
    print(position)

    # Example 2: Create a Transaction
    print("\n" + "=" * 80)
    print("TRANSACTION EXAMPLE")
    print("=" * 80)

    buy_transaction = Transaction(
        timestamp=datetime(2024, 1, 15, 9, 30, 45),
        symbol="SBIN",
        action=TransactionType.BUY,
        quantity=100,
        price=550.0,
        commission=20.0,
        slippage_pct=0.5,  # 0.5% slippage
        exchange="NSE",
        notes="Entry position based on bullish signal"
    )

    print(buy_transaction)
    print(f"\nGross Amount: Rs.{buy_transaction.gross_amount:,.2f}")
    print(f"Slippage: {buy_transaction.slippage_pct}% = Rs.{buy_transaction.slippage:,.2f}")
    print(f"Total Fees: Rs.{buy_transaction.total_fees:,.2f}")
    print(f"Net Amount: Rs.{buy_transaction.net_amount:,.2f}")
    print(f"Effective Price per Share: Rs.{buy_transaction.effective_price:.2f}")

    print("\nFull Summary:")
    for key, value in buy_transaction.get_summary().items():
        print(f"  {key}: {value}")

    # Example 3: Sell Transaction
    print("\n--- SELL Transaction ---")
    sell_transaction = Transaction(
        timestamp=datetime(2024, 1, 20, 15, 20, 30),
        symbol="SBIN",
        action=TransactionType.SELL,
        quantity=100,
        price=575.0,
        commission=20.0,
        slippage_pct=0.5,  # 0.5% slippage
        exchange="NSE",
        notes="Exit position - target reached"
    )

    print(sell_transaction)
    print(f"Net Proceeds: Rs.{sell_transaction.net_amount:,.2f}")

    # Calculate realized P&L
    realized_pnl = sell_transaction.net_amount - buy_transaction.net_amount
    print(f"\nRealized P&L: Rs.{realized_pnl:,.2f}")

    # Example 4: Create Equity Points (Portfolio Snapshots)
    print("\n" + "=" * 80)
    print("EQUITY POINT EXAMPLES")
    print("=" * 80)

    # Simulate a trading day with multiple snapshots
    print("\n--- Building an Equity Curve ---")

    # Day start: All cash, no positions
    ep1 = EquityPoint(
        timestamp=datetime(2024, 1, 15, 9, 15, 0),
        cash=100000.0,
        positions_value=0.0
    )
    print(f"\nDay Start (9:15 AM):")
    print(ep1)

    # After buying SBIN: Cash reduced, positions opened
    ep2 = EquityPoint(
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        cash=100000.0 - 55295.0,  # After buying SBIN (see transaction example)
        positions_value=55000.0    # Current market value of position
    )
    print(f"\nAfter First Trade (10:30 AM):")
    print(ep2)
    print(f"Allocation - Cash: {ep2.cash_percentage:.1f}%, Positions: {ep2.positions_percentage:.1f}%")

    # Mid-day: Position value increased
    ep3 = EquityPoint(
        timestamp=datetime(2024, 1, 15, 12, 0, 0),
        cash=44705.0,
        positions_value=57500.0  # SBIN price increased to 575
    )
    print(f"\nMid-Day Update (12:00 PM):")
    print(ep3)
    gain = ep3.total_value - ep1.total_value
    gain_pct = (gain / ep1.total_value) * 100
    print(f"Portfolio Gain: Rs.{gain:,.2f} ({gain_pct:+.2f}%)")

    # After selling: Back to mostly cash
    ep4 = EquityPoint(
        timestamp=datetime(2024, 1, 15, 15, 20, 0),
        cash=44705.0 + 57192.50,  # After selling SBIN
        positions_value=0.0
    )
    print(f"\nAfter Exit (3:20 PM):")
    print(ep4)
    total_gain = ep4.total_value - ep1.total_value
    total_gain_pct = (total_gain / ep1.total_value) * 100
    print(f"Total Day Gain: Rs.{total_gain:,.2f} ({total_gain_pct:+.2f}%)")

    # Show how to build equity curve data
    print("\n--- Equity Curve Data Points ---")
    equity_curve = [ep1, ep2, ep3, ep4]

    print("\nTimestamp                   Total Value    Change      Change %")
    print("-" * 70)
    for i, ep in enumerate(equity_curve):
        if i == 0:
            change = 0.0
            change_pct = 0.0
        else:
            change = ep.total_value - equity_curve[0].total_value
            change_pct = (change / equity_curve[0].total_value) * 100

        print(f"{ep.timestamp.strftime('%Y-%m-%d %H:%M:%S')}    "
              f"Rs.{ep.total_value:>10,.2f}    "
              f"Rs.{change:>8,.2f}    "
              f"{change_pct:>6.2f}%")

    # Show summary of all points
    print("\n--- Full Summary of Last Point ---")
    for key, value in ep4.get_summary().items():
        print(f"  {key}: {value}")
