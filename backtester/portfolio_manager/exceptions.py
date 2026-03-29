"""
Custom exception classes for portfolio management.

This module defines specific error types for the portfolio manager,
enabling precise error handling and helpful debugging information.
"""


class PortfolioError(Exception):
    """
    Base exception class for all portfolio-related errors.

    Use this as a parent class to catch all portfolio errors with a single
    except clause. Allows for granular error handling of specific error types
    while maintaining a common catch-all mechanism.

    Example:
        try:
            portfolio.buy_stock(symbol, quantity, price)
        except PortfolioError as e:
            print(f"Portfolio operation failed: {e}")
    """
    pass


class InsufficientFundsError(PortfolioError):
    """
    Raised when attempting to buy stocks without sufficient cash balance.

    This error provides clear information about the required amount and
    available balance to help users understand exactly what's needed.

    Attributes:
        required_amount (float): Total amount needed for the transaction
        available_balance (float): Current cash balance
        shortfall (float): Difference between required and available amounts

    Example:
        try:
            portfolio.buy_stock("SBIN", 100, 500)  # 50,000 needed, only 40,000 available
        except InsufficientFundsError as e:
            print(f"Not enough funds! Need: {e.required_amount}, Have: {e.available_balance}")
    """

    def __init__(self, required_amount, available_balance):
        self.required_amount = required_amount
        self.available_balance = available_balance
        self.shortfall = required_amount - available_balance

        message = (
            f"Insufficient funds for this transaction. "
            f"Required: �{required_amount:,.2f}, "
            f"Available: �{available_balance:,.2f}, "
            f"Shortfall: �{self.shortfall:,.2f}"
        )
        super().__init__(message)


class InvalidOrderError(PortfolioError):
    """
    Raised when an order is malformed or contains invalid parameters.

    This error catches problems before they reach the execution system,
    validating order parameters like quantity, price, and other required fields.

    Attributes:
        order_details (dict): The invalid order data
        validation_errors (list): List of validation error messages

    Example:
        try:
            portfolio.place_order(symbol="SBIN", quantity=-10, price=500)  # Invalid quantity
        except InvalidOrderError as e:
            print(f"Invalid order: {e}")
    """

    def __init__(self, message, order_details=None, validation_errors=None):
        self.order_details = order_details or {}
        self.validation_errors = validation_errors or []

        if validation_errors:
            detailed_message = f"{message}\nValidation errors:\n"
            detailed_message += "\n".join(f"  - {error}" for error in validation_errors)
            super().__init__(detailed_message)
        else:
            super().__init__(message)


class PositionNotFoundError(PortfolioError):
    """
    Raised when attempting to sell a stock that is not held in the portfolio.

    This error prevents transactions on non-existent positions, helping users
    identify attempts to sell stocks they don't own.

    Attributes:
        symbol (str): The stock symbol that was not found
        holdings (list): List of currently held positions

    Example:
        try:
            portfolio.sell_stock("NOTOWNED", 10, 500)
        except PositionNotFoundError as e:
            print(f"Cannot sell: {e}")
            print(f"Your holdings: {e.holdings}")
    """

    def __init__(self, symbol, holdings=None):
        self.symbol = symbol
        self.holdings = holdings or []

        message = (
            f"Position not found for symbol '{symbol}'. "
            f"You do not currently hold this stock."
        )
        if holdings:
            message += f"\nCurrent holdings: {', '.join(holdings) if holdings else 'None'}"

        super().__init__(message)


class InsufficientPositionError(PortfolioError):
    """
    Raised when attempting to sell more shares than are held in the portfolio.

    This error prevents over-selling and helps users understand their actual
    position size vs. the requested quantity.

    Attributes:
        symbol (str): The stock symbol
        owned_quantity (int): Number of shares currently held
        requested_quantity (int): Number of shares requested to sell
        excess (int): Difference between requested and owned quantities

    Example:
        try:
            portfolio.sell_stock("SBIN", 100, 500)  # Own 50, trying to sell 100
        except InsufficientPositionError as e:
            print(f"Not enough shares! Owned: {e.owned_quantity}, Requested: {e.requested_quantity}")
    """

    def __init__(self, symbol, owned_quantity, requested_quantity):
        self.symbol = symbol
        self.owned_quantity = owned_quantity
        self.requested_quantity = requested_quantity
        self.excess = requested_quantity - owned_quantity

        message = (
            f"Insufficient position for '{symbol}'. "
            f"Owned: {owned_quantity} shares, "
            f"Trying to sell: {requested_quantity} shares, "
            f"Excess: {self.excess} shares"
        )
        super().__init__(message)


if __name__ == "__main__":
    """
    Demonstration and testing of exception classes.
    Run this file directly to see examples of each exception type.
    """

    print("=" * 70)
    print("PORTFOLIO EXCEPTION EXAMPLES")
    print("=" * 70)

    # 1. InsufficientFundsError
    print("\n1. InsufficientFundsError - Insufficient cash for purchase")
    print("-" * 70)
    try:
        raise InsufficientFundsError(
            required_amount=50000.00,
            available_balance=40000.00
        )
    except InsufficientFundsError as e:
        print(f"❌ Exception caught: {e}")
        print(f"   - Required: ₹{e.required_amount:,.2f}")
        print(f"   - Available: ₹{e.available_balance:,.2f}")
        print(f"   - Shortfall: ₹{e.shortfall:,.2f}")

    # 2. InvalidOrderError - Basic invalid order
    print("\n2. InvalidOrderError - Missing/invalid order parameters")
    print("-" * 70)
    try:
        raise InvalidOrderError(
            message="Invalid order parameters",
            order_details={"symbol": "SBIN", "quantity": -10, "price": 500},
            validation_errors=[
                "Quantity must be positive (got -10)",
                "Price must be greater than 0 (got 500)"
            ]
        )
    except InvalidOrderError as e:
        print(f"❌ Exception caught: {e}")

    # 3. InvalidOrderError - Simple message
    print("\n3. InvalidOrderError - Simple case without validation details")
    print("-" * 70)
    try:
        raise InvalidOrderError("Order symbol is required but not provided")
    except InvalidOrderError as e:
        print(f"❌ Exception caught: {e}")

    # 4. PositionNotFoundError
    print("\n4. PositionNotFoundError - Trying to sell non-existent position")
    print("-" * 70)
    try:
        raise PositionNotFoundError(
            symbol="NOTOWNED",
            holdings=["SBIN", "RELIANCE", "INFY"]
        )
    except PositionNotFoundError as e:
        print(f"❌ Exception caught: {e}")
        print(f"   - Symbol not found: {e.symbol}")
        print(f"   - Your holdings: {e.holdings}")

    # 5. PositionNotFoundError - No holdings
    print("\n5. PositionNotFoundError - No holdings at all")
    print("-" * 70)
    try:
        raise PositionNotFoundError(symbol="TCS")
    except PositionNotFoundError as e:
        print(f"❌ Exception caught: {e}")

    # 6. InsufficientPositionError
    print("\n6. InsufficientPositionError - Trying to over-sell")
    print("-" * 70)
    try:
        raise InsufficientPositionError(
            symbol="SBIN",
            owned_quantity=50,
            requested_quantity=100
        )
    except InsufficientPositionError as e:
        print(f"❌ Exception caught: {e}")
        print(f"   - Symbol: {e.symbol}")
        print(f"   - Owned: {e.owned_quantity} shares")
        print(f"   - Requested: {e.requested_quantity} shares")
        print(f"   - Excess: {e.excess} shares")

    # 7. Catching base PortfolioError
    print("\n7. Catching all portfolio errors with base PortfolioError")
    print("-" * 70)
    exceptions_list = [
        InsufficientFundsError(100000, 50000),
        PositionNotFoundError("XYZ"),
        InsufficientPositionError("ABC", 10, 20)
    ]

    for exc in exceptions_list:
        try:
            raise exc
        except PortfolioError as e:
            print(f"✓ Caught {type(e).__name__}: {str(e)[:60]}...")

    print("\n" + "=" * 70)
    print("All exception examples demonstrated successfully!")
    print("=" * 70)
