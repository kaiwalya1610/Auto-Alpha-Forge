
"""
Portfolio Manager

Main orchestrator class that manages trading portfolio state including cash, positions,
transactions, and equity curve tracking. Coordinates all portfolio operations using
existing models (Order, Position, Transaction, EquityPoint).

Author: Portfolio Management System
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal

from backtester.portfolio_manager.models import Order, Position, Transaction, EquityPoint, TransactionType, OrderStatus
from backtester.portfolio_manager.utils import calculate_commission, calculate_slippage
from backtester.portfolio_manager.exceptions import (
    InsufficientFundsError,
    InvalidOrderError,
    PositionNotFoundError,
    InsufficientPositionError
)

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Portfolio Manager - The brain of the trading system.

    Tracks cash, positions, transactions, and equity curve. Executes orders,
    manages position lifecycle, and provides portfolio analytics.

    Attributes:
        initial_capital (float): Starting cash amount (never changes)
        cash (float): Current cash balance
        positions (Dict[str, Position]): Active positions keyed by symbol
        transactions (List[Transaction]): Complete transaction history
        equity_curve (List[EquityPoint]): Portfolio value snapshots over time
        commission_rate (float): Commission as percentage of trade value
        minimum_commission (float): Minimum commission per trade
        slippage_rate (float): Slippage as percentage of trade value
        allow_short_selling (bool): Whether short positions are allowed
        total_commissions (float): Cumulative commissions paid
        total_slippage (float): Cumulative slippage incurred

    Example:
        >>> pm = PortfolioManager(
        ...     initial_capital=100000.0,
        ...     commission_rate=0.001,
        ...     minimum_commission=1.0,
        ...     slippage_rate=0.0005,
        ...     allow_short_selling=False
        ... )
        >>> order = Order(symbol="SBIN", action=TransactionType.BUY, quantity=10, order_type="MARKET")
        >>> transaction = pm.process_order(order, current_price=500.0, timestamp=datetime.now())
        >>> print(f"Cash remaining: {pm.get_cash()}")
        >>> print(f"Portfolio value: {pm.get_portfolio_value({'SBIN': 510.0})}")
    """

    def __init__(
        self,
        initial_capital: float,
        commission_rate: float = 0.001,
        minimum_commission: float = 1.0,
        slippage_rate: float = 0.0005,
        allow_short_selling: bool = False
    ):
        """
        Initialize Portfolio Manager.

        Args:
            initial_capital: Starting cash amount
            commission_rate: Commission as percentage (0.001 = 0.1%)
            minimum_commission: Minimum commission per trade
            slippage_rate: Slippage as percentage (0.0005 = 0.05%)
            allow_short_selling: Whether to allow short positions

        Raises:
            ValueError: If initial_capital is not positive
        """
        if initial_capital <= 0:
            raise ValueError(f"Initial capital must be positive, got {initial_capital}")

        # Core state
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.positions: Dict[str, Position] = {}
        self.transactions: List[Transaction] = []
        self.equity_curve: List[EquityPoint] = []

        # Configuration
        self.commission_rate = float(commission_rate)
        self.minimum_commission = float(minimum_commission)
        self.slippage_rate = float(slippage_rate)
        self.allow_short_selling = allow_short_selling

        # Metrics counters
        self.total_commissions = 0.0
        self.total_slippage = 0.0

        logger.info(
            f"PortfolioManager initialized: capital=${initial_capital:,.2f}, "
            f"commission={commission_rate:.4f}, slippage={slippage_rate:.4f}, "
            f"short_selling={allow_short_selling}"
        )

    def __repr__(self) -> str:
        """String representation of portfolio manager."""
        return (
            f"PortfolioManager(capital=${self.initial_capital:,.2f}, "
            f"cash=${self.cash:,.2f}, positions={len(self.positions)}, "
            f"transactions={len(self.transactions)})"
        )

    # =========================================================================
    # Core Order Processing
    # =========================================================================

    def _validate_order(self, order: Order, current_price: float) -> None:
        """
        Validate order before execution.

        Args:
            order: Order to validate
            current_price: Current market price

        Raises:
            InvalidOrderError: If order parameters are invalid
            InsufficientPositionError: If selling more than owned
        """
        validation_errors = []

        # Basic validations
        if current_price <= 0:
            validation_errors.append(f"Price must be positive, got {current_price}")

        if order.quantity <= 0:
            validation_errors.append(f"Quantity must be positive, got {order.quantity}")

        # Check for sell validations
        if order.action == TransactionType.SELL:
            current_position = self.positions.get(order.symbol)

            if current_position is None:
                # No existing position
                if not self.allow_short_selling:
                    # Short selling disabled - cannot sell without existing position
                    raise PositionNotFoundError(
                        symbol=order.symbol,
                        holdings=list(self.positions.keys())
                    )
                # else: short selling enabled - this will create a new short position
            elif current_position.is_long:
                # Selling from long position - check if we have enough shares
                if current_position.quantity < order.quantity:
                    raise InsufficientPositionError(
                        symbol=order.symbol,
                        owned_quantity=current_position.quantity,
                        requested_quantity=order.quantity
                    )
            elif current_position.is_short:
                # Already short - this sell will increase the short position (more negative)
                # No quantity validation needed for increasing shorts
                pass

        # Check for buy validations
        if order.action == TransactionType.BUY:
            current_position = self.positions.get(order.symbol)

            if current_position and current_position.is_short:
                # Buying to cover a short position
                if not self.allow_short_selling:
                    validation_errors.append(
                        f"Short selling disabled, cannot have negative position in {order.symbol}"
                    )
                # Check if trying to cover more than short quantity
                if abs(current_position.quantity) < order.quantity:
                    # Covering more than short - will flip to long, which is fine
                    pass

        if validation_errors:
            raise InvalidOrderError(
                order_details=order.get_summary(),
                validation_errors=validation_errors
            )

    def process_order(
        self,
        order: Order,
        current_price: float,
        timestamp: Optional[datetime] = None
    ) -> Transaction:
        """
        Process and execute an order.

        Main entry point for order execution. Validates the order, executes it,
        updates portfolio state, and returns the resulting transaction.

        Args:
            order: Order object to execute
            current_price: Current market price for execution
            timestamp: Execution timestamp (defaults to now)

        Returns:
            Transaction object representing the executed trade

        Raises:
            InvalidOrderError: If order is invalid
            InsufficientFundsError: If insufficient cash for buy
            InsufficientPositionError: If insufficient position for sell
            PositionNotFoundError: If trying to sell non-existent position

        Example:
            >>> order = Order(symbol="SBIN", action=TransactionType.BUY, quantity=10, order_type="MARKET")
            >>> transaction = pm.process_order(order, current_price=500.0)
            >>> print(f"Executed: {transaction.quantity} @ {transaction.price}")
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Validate order
        self._validate_order(order, current_price)

        # Execute based on action
        if order.action == TransactionType.BUY:
            transaction = self._execute_buy(order, current_price, timestamp)
        else:  # SELL
            transaction = self._execute_sell(order, current_price, timestamp)

        # Update order status
        order.update_status(OrderStatus.FILLED)
        order.add_fill(
            filled_qty=order.quantity,
            fill_price=current_price
        )

        logger.info(
            f"Order executed: {order.action.value} {order.quantity} {order.symbol} @ "
            f"${current_price:.2f} (fees: ${transaction.total_fees:.2f})"
        )

        return transaction

    def _execute_buy(
        self,
        order: Order,
        current_price: float,
        timestamp: datetime
    ) -> Transaction:
        """
        Execute a buy order.

        Handles both:
        - Opening/adding to LONG positions
        - Covering (reducing) SHORT positions

        Args:
            order: Buy order to execute
            current_price: Execution price
            timestamp: Execution timestamp

        Returns:
            Transaction object

        Raises:
            InsufficientFundsError: If not enough cash
        """
        # Create transaction using factory method (auto-calculates fees)
        transaction = Transaction.create_with_fees(
            timestamp=timestamp,
            symbol=order.symbol,
            action=TransactionType.BUY,
            quantity=order.quantity,
            price=current_price,
            commission_rate=self.commission_rate,
            minimum_commission=self.minimum_commission,
            slippage_rate=self.slippage_rate,
            exchange=order.exchange,
            notes=f"Order ID: {order.order_id}"
        )

        # Check if sufficient cash
        # For BUY orders: net_amount is positive (total cash outflow including fees)
        required_cash = transaction.net_amount
        if self.cash < required_cash:
            raise InsufficientFundsError(
                required_amount=required_cash,
                available_balance=self.cash
            )

        # Deduct cash
        self.cash -= required_cash

        # Update or create position
        if order.symbol in self.positions:
            existing_position = self.positions[order.symbol]

            if existing_position.is_short:
                # Covering a short position
                new_quantity = existing_position.quantity + order.quantity

                if new_quantity == 0:
                    # Fully covered - close position
                    del self.positions[order.symbol]
                    logger.debug(f"Covered short position: {order.symbol}")
                elif new_quantity < 0:
                    # Partially covered - still short
                    existing_position.quantity = new_quantity
                    existing_position.update_price(current_price)
                    logger.debug(
                        f"Partially covered short: {order.symbol} qty={new_quantity} "
                        f"(still short {abs(new_quantity)} shares)"
                    )
                else:
                    # Over-covered - flipped to long
                    existing_position.quantity = new_quantity
                    existing_position.entry_price = transaction.effective_price
                    existing_position.update_price(current_price)

                    # Update stop-loss and target for new long position
                    if order.position_stop_loss is not None:
                        existing_position.stop_loss_price = order.position_stop_loss
                    if order.position_target is not None:
                        existing_position.target_price = order.position_target

                    logger.debug(
                        f"Over-covered short, now long: {order.symbol} qty={new_quantity}"
                    )
            else:
                # Adding to existing long position - average in
                total_quantity = existing_position.quantity + order.quantity
                total_cost = (existing_position.quantity * existing_position.entry_price +
                             order.quantity * transaction.effective_price)
                new_avg_price = total_cost / total_quantity

                existing_position.quantity = total_quantity
                existing_position.entry_price = new_avg_price
                existing_position.update_price(current_price)

                # Update stop-loss and target if provided in the new order
                if order.position_stop_loss is not None:
                    existing_position.stop_loss_price = order.position_stop_loss
                if order.position_target is not None:
                    existing_position.target_price = order.position_target

                logger.debug(
                    f"Added to long position: {order.symbol} qty={total_quantity} "
                    f"avg_price=${new_avg_price:.2f}"
                )
        else:
            # Create new long position
            self.positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=order.quantity,
                entry_price=transaction.effective_price,
                current_price=current_price,
                entry_timestamp=timestamp,
                exchange=order.exchange,
                stop_loss_price=order.position_stop_loss,
                target_price=order.position_target
            )

            logger.debug(
                f"New long position: {order.symbol} qty={order.quantity} "
                f"entry=${transaction.effective_price:.2f}"
            )

        # Record transaction and update counters
        self.transactions.append(transaction)
        self.total_commissions += transaction.commission
        self.total_slippage += transaction.slippage

        return transaction

    def _execute_sell(
        self,
        order: Order,
        current_price: float,
        timestamp: datetime
    ) -> Transaction:
        """
        Execute a sell order.

        Handles both:
        - Reducing/closing LONG positions
        - Opening/increasing SHORT positions

        Args:
            order: Sell order to execute
            current_price: Execution price
            timestamp: Execution timestamp

        Returns:
            Transaction object

        Raises:
            PositionNotFoundError: If position doesn't exist (when shorting disabled)
            InsufficientPositionError: If not enough shares to sell
        """
        # Create transaction using factory method
        transaction = Transaction.create_with_fees(
            timestamp=timestamp,
            symbol=order.symbol,
            action=TransactionType.SELL,
            quantity=order.quantity,
            price=current_price,
            commission_rate=self.commission_rate,
            minimum_commission=self.minimum_commission,
            slippage_rate=self.slippage_rate,
            exchange=order.exchange,
            notes=f"Order ID: {order.order_id}"
        )

        # Add cash (net_amount is positive for sells)
        self.cash += transaction.net_amount

        # Update or create position
        if order.symbol in self.positions:
            position = self.positions[order.symbol]

            if position.is_long:
                # Selling from long position
                new_quantity = position.quantity - order.quantity

                if new_quantity == 0:
                    # Fully closed - remove position
                    del self.positions[order.symbol]
                    logger.debug(f"Closed long position: {order.symbol}")
                elif new_quantity > 0:
                    # Partially closed - still long
                    position.quantity = new_quantity
                    position.update_price(current_price)
                    logger.debug(
                        f"Reduced long position: {order.symbol} qty={new_quantity} "
                        f"remaining"
                    )
                else:
                    # Over-sold - flipped to short
                    position.quantity = new_quantity
                    position.entry_price = transaction.effective_price
                    position.update_price(current_price)

                    # Update stop-loss and target for new short position
                    if order.position_stop_loss is not None:
                        position.stop_loss_price = order.position_stop_loss
                    if order.position_target is not None:
                        position.target_price = order.position_target

                    logger.debug(
                        f"Over-sold long, now short: {order.symbol} qty={new_quantity}"
                    )
            else:
                # Increasing short position (selling more shares we don't own)
                new_quantity = position.quantity - order.quantity

                # Calculate new average entry price for short
                total_cost = (abs(position.quantity) * position.entry_price +
                             order.quantity * transaction.effective_price)
                new_avg_price = total_cost / abs(new_quantity)

                position.quantity = new_quantity
                position.entry_price = new_avg_price
                position.update_price(current_price)

                # Update stop-loss and target if provided
                if order.position_stop_loss is not None:
                    position.stop_loss_price = order.position_stop_loss
                if order.position_target is not None:
                    position.target_price = order.position_target

                logger.debug(
                    f"Increased short position: {order.symbol} qty={new_quantity} "
                    f"avg_price=${new_avg_price:.2f}"
                )
        else:
            # No existing position - create new short position
            self.positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=-order.quantity,  # Negative for short
                entry_price=transaction.effective_price,
                current_price=current_price,
                entry_timestamp=timestamp,
                exchange=order.exchange,
                stop_loss_price=order.position_stop_loss,
                target_price=order.position_target
            )

            logger.debug(
                f"New short position: {order.symbol} qty={-order.quantity} "
                f"entry=${transaction.effective_price:.2f}"
            )

        # Record transaction and update counters
        self.transactions.append(transaction)
        self.total_commissions += transaction.commission
        self.total_slippage += transaction.slippage

        return transaction

    # =========================================================================
    # Position Query Methods
    # =========================================================================

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Symbol to query

        Returns:
            Position object or None if no position exists

        Example:
            >>> position = pm.get_position("SBIN")
            >>> if position:
            ...     print(f"Holding {position.quantity} shares")
        """
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """
        Check if a position exists for a symbol.

        Args:
            symbol: Symbol to check

        Returns:
            True if position exists, False otherwise

        Example:
            >>> if pm.has_position("SBIN"):
            ...     print("Already own SBIN")
        """
        return symbol in self.positions

    def get_all_positions(self) -> Dict[str, Position]:
        """
        Get all current positions.

        Returns:
            Dictionary of symbol -> Position objects

        Example:
            >>> positions = pm.get_all_positions()
            >>> for symbol, position in positions.items():
            ...     print(f"{symbol}: {position.quantity} shares")
        """
        return self.positions.copy()

    def get_position_quantity(self, symbol: str) -> int:
        """
        Get quantity of shares held for a symbol.

        Args:
            symbol: Symbol to query

        Returns:
            Number of shares (0 if no position)

        Example:
            >>> qty = pm.get_position_quantity("SBIN")
            >>> print(f"Holding {qty} shares of SBIN")
        """
        position = self.positions.get(symbol)
        return position.quantity if position else 0

    # =========================================================================
    # Portfolio Valuation Methods
    # =========================================================================

    def update_prices(self, price_dict: Dict[str, float]) -> None:
        """
        Update current market prices for all positions.

        Args:
            price_dict: Dictionary mapping symbol -> current price

        Example:
            >>> pm.update_prices({"SBIN": 510.0, "INFY": 1450.0})
        """
        for symbol, position in self.positions.items():
            if symbol in price_dict:
                position.update_price(price_dict[symbol])
                logger.debug(
                    f"Updated {symbol} price: ${price_dict[symbol]:.2f} "
                    f"(unrealized P&L: ${position.unrealized_pnl:.2f})"
                )

    def get_positions_value(self, price_dict: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total value of all positions.

        Args:
            price_dict: Optional dict of current prices (updates positions if provided)

        Returns:
            Total market value of all positions

        Example:
            >>> value = pm.get_positions_value({"SBIN": 510.0, "INFY": 1450.0})
            >>> print(f"Total positions value: ${value:,.2f}")
        """
        if price_dict:
            self.update_prices(price_dict)

        total_value = sum(position.market_value for position in self.positions.values())
        return total_value

    def get_portfolio_value(self, price_dict: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total portfolio value (cash + positions).

        Args:
            price_dict: Optional dict of current prices (updates positions if provided)

        Returns:
            Total portfolio value

        Example:
            >>> total = pm.get_portfolio_value({"SBIN": 510.0})
            >>> print(f"Total portfolio value: ${total:,.2f}")
        """
        positions_value = self.get_positions_value(price_dict)
        return self.cash + positions_value

    def get_cash(self) -> float:
        """
        Get current cash balance.

        Returns:
            Available cash

        Example:
            >>> cash = pm.get_cash()
            >>> print(f"Available cash: ${cash:,.2f}")
        """
        return self.cash

    # =========================================================================
    # P&L and Metrics Methods
    # =========================================================================

    def get_unrealized_pnl(self) -> float:
        """
        Calculate total unrealized profit/loss on open positions.

        Returns:
            Total unrealized P&L (positive = profit, negative = loss)

        Example:
            >>> unrealized = pm.get_unrealized_pnl()
            >>> print(f"Unrealized P&L: ${unrealized:,.2f}")
        """
        total_unrealized = sum(
            position.unrealized_pnl for position in self.positions.values()
        )
        return total_unrealized

    def get_realized_pnl(self) -> float:
        """
        Calculate total realized profit/loss from closed trades.

        Calculates P&L by analyzing all transactions to identify buy-sell pairs
        and their profits/losses. This represents actual gains/losses from
        completed round trips.

        Returns:
            Total realized P&L (positive = profit, negative = loss)

        Example:
            >>> realized = pm.get_realized_pnl()
            >>> print(f"Realized P&L: ${realized:,.2f}")
        """
        # Group transactions by symbol
        symbol_transactions = {}
        for txn in self.transactions:
            if txn.symbol not in symbol_transactions:
                symbol_transactions[txn.symbol] = []
            symbol_transactions[txn.symbol].append(txn)

        total_realized_pnl = 0.0

        # Calculate realized P&L for each symbol
        for symbol, txns in symbol_transactions.items():
            # Track position for FIFO accounting
            holding_queue = []  # List of (quantity, price) tuples

            for txn in sorted(txns, key=lambda t: t.timestamp):
                if txn.action == TransactionType.BUY:
                    # Add to holdings
                    holding_queue.append((txn.quantity, txn.effective_price))
                else:  # SELL
                    # Remove from holdings and calculate P&L
                    remaining_to_sell = txn.quantity
                    sell_price = txn.effective_price

                    while remaining_to_sell > 0 and holding_queue:
                        buy_qty, buy_price = holding_queue[0]

                        if buy_qty <= remaining_to_sell:
                            # Fully close this lot
                            pnl = buy_qty * (sell_price - buy_price)
                            total_realized_pnl += pnl
                            remaining_to_sell -= buy_qty
                            holding_queue.pop(0)
                        else:
                            # Partially close this lot
                            pnl = remaining_to_sell * (sell_price - buy_price)
                            total_realized_pnl += pnl
                            holding_queue[0] = (buy_qty - remaining_to_sell, buy_price)
                            remaining_to_sell = 0

        return total_realized_pnl

    def get_total_return(self, price_dict: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total portfolio return as a percentage.

        Args:
            price_dict: Optional dict of current prices

        Returns:
            Return percentage (e.g., 15.5 means 15.5% return)

        Example:
            >>> return_pct = pm.get_total_return({"SBIN": 510.0})
            >>> print(f"Total return: {return_pct:.2f}%")
        """
        current_value = self.get_portfolio_value(price_dict)
        total_return = ((current_value - self.initial_capital) / self.initial_capital) * 100
        return total_return

    def get_total_commissions(self) -> float:
        """
        Get total commissions paid.

        Returns:
            Total commissions + slippage

        Example:
            >>> fees = pm.get_total_commissions()
            >>> print(f"Total fees paid: ${fees:,.2f}")
        """
        return self.total_commissions + self.total_slippage

    def record_equity_point(
        self,
        timestamp: datetime,
        price_dict: Optional[Dict[str, float]] = None
    ) -> EquityPoint:
        """
        Record a snapshot of portfolio value for equity curve tracking.

        Args:
            timestamp: Time of snapshot
            price_dict: Optional dict of current prices

        Returns:
            The created EquityPoint object

        Example:
            >>> point = pm.record_equity_point(datetime.now(), {"SBIN": 510.0})
            >>> print(f"Portfolio value: ${point.total_value:,.2f}")
        """
        positions_value = self.get_positions_value(price_dict)

        equity_point = EquityPoint(
            timestamp=timestamp,
            cash=self.cash,
            positions_value=positions_value
        )

        self.equity_curve.append(equity_point)

        logger.debug(
            f"Equity point recorded: ${equity_point.total_value:,.2f} "
            f"(cash: ${self.cash:,.2f}, positions: ${positions_value:,.2f})"
        )

        return equity_point

    # =========================================================================
    # History and Summary Methods
    # =========================================================================

    def get_transaction_history(self) -> List[Transaction]:
        """
        Get complete transaction history.

        Returns:
            List of all Transaction objects in chronological order

        Example:
            >>> history = pm.get_transaction_history()
            >>> for txn in history:
            ...     print(f"{txn.timestamp}: {txn.action.value} {txn.quantity} {txn.symbol}")
        """
        return self.transactions.copy()

    def get_equity_curve(self) -> List[EquityPoint]:
        """
        Get portfolio value history.

        Returns:
            List of all EquityPoint objects in chronological order

        Example:
            >>> curve = pm.get_equity_curve()
            >>> for point in curve:
            ...     print(f"{point.timestamp}: ${point.total_value:,.2f}")
        """
        return self.equity_curve.copy()

    def get_summary(self, price_dict: Optional[Dict[str, float]] = None) -> Dict:
        """
        Get comprehensive portfolio summary.

        Args:
            price_dict: Optional dict of current prices

        Returns:
            Dictionary containing all key portfolio metrics

        Example:
            >>> summary = pm.get_summary({"SBIN": 510.0})
            >>> print(f"Total return: {summary['total_return_pct']:.2f}%")
            >>> print(f"Win rate: {summary['win_rate']:.1f}%")
        """
        # Update prices if provided
        if price_dict:
            self.update_prices(price_dict)

        # Calculate metrics
        current_value = self.get_portfolio_value()
        positions_value = self.get_positions_value()
        unrealized_pnl = self.get_unrealized_pnl()
        realized_pnl = self.get_realized_pnl()
        total_return = self.get_total_return()

        # Trading statistics
        total_trades = len(self.transactions)
        buy_trades = sum(1 for txn in self.transactions if txn.action == TransactionType.BUY)
        sell_trades = sum(1 for txn in self.transactions if txn.action == TransactionType.SELL)

        # Calculate win/loss statistics
        winning_trades = 0
        losing_trades = 0
        total_wins = 0.0
        total_losses = 0.0

        # Analyze closed positions
        symbol_transactions = {}
        for txn in self.transactions:
            if txn.symbol not in symbol_transactions:
                symbol_transactions[txn.symbol] = []
            symbol_transactions[txn.symbol].append(txn)

        for txns in symbol_transactions.values():
            holding_queue = []

            for txn in sorted(txns, key=lambda t: t.timestamp):
                if txn.action == TransactionType.BUY:
                    holding_queue.append((txn.quantity, txn.effective_price))
                else:
                    remaining_to_sell = txn.quantity
                    sell_price = txn.effective_price

                    while remaining_to_sell > 0 and holding_queue:
                        buy_qty, buy_price = holding_queue[0]
                        qty_to_close = min(buy_qty, remaining_to_sell)

                        pnl = qty_to_close * (sell_price - buy_price)

                        if pnl > 0:
                            winning_trades += 1
                            total_wins += pnl
                        elif pnl < 0:
                            losing_trades += 1
                            total_losses += abs(pnl)

                        if buy_qty <= remaining_to_sell:
                            remaining_to_sell -= buy_qty
                            holding_queue.pop(0)
                        else:
                            holding_queue[0] = (buy_qty - remaining_to_sell, buy_price)
                            remaining_to_sell = 0

        # Calculate win rate and averages
        total_closed_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0.0
        avg_win = (total_wins / winning_trades) if winning_trades > 0 else 0.0
        avg_loss = (total_losses / losing_trades) if losing_trades > 0 else 0.0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')

        summary = {
            # Portfolio state
            "initial_capital": self.initial_capital,
            "current_cash": self.cash,
            "positions_value": positions_value,
            "total_value": current_value,

            # Performance metrics
            "total_return_pct": total_return,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "total_pnl": unrealized_pnl + realized_pnl,

            # Position metrics
            "num_positions": len(self.positions),
            "positions": {symbol: {
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "market_value": pos.market_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": pos.unrealized_pnl_pct
            } for symbol, pos in self.positions.items()},

            # Trading statistics
            "total_trades": total_trades,
            "buy_trades": buy_trades,
            "sell_trades": sell_trades,
            "closed_trades": total_closed_trades,

            # Win/Loss statistics
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,

            # Cost metrics
            "total_commissions": self.total_commissions,
            "total_slippage": self.total_slippage,
            "total_fees": self.total_commissions + self.total_slippage,

            # Equity curve
            "equity_points": len(self.equity_curve),
        }

        return summary
