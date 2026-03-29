"""
Risk Manager Custom Exceptions

Defines all exception types used in the risk management module.
"""


class RiskManagerError(Exception):
    """Base exception for all risk manager errors."""
    pass


class RiskLimitViolation(RiskManagerError):
    """Raised when a risk limit is breached."""

    def __init__(self, limit_type: str, current_value: float, limit_value: float, message: str = None):
        """
        Initialize RiskLimitViolation.

        Args:
            limit_type: Type of limit violated (e.g., 'max_position_pct', 'max_drawdown')
            current_value: Current value that violated the limit
            limit_value: The limit threshold that was breached
            message: Optional custom message
        """
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value

        if message is None:
            message = (
                f"Risk limit violation: {limit_type} "
                f"(current: {current_value:.4f}, limit: {limit_value:.4f})"
            )

        super().__init__(message)


class InsufficientDataError(RiskManagerError):
    """Raised when insufficient historical data is available for calculations."""

    def __init__(self, required_periods: int, available_periods: int, symbol: str = None):
        """
        Initialize InsufficientDataError.

        Args:
            required_periods: Number of periods required
            available_periods: Number of periods available
            symbol: Optional symbol that lacks data
        """
        self.required_periods = required_periods
        self.available_periods = available_periods
        self.symbol = symbol

        symbol_str = f" for {symbol}" if symbol else ""
        message = (
            f"Insufficient data{symbol_str}: "
            f"required {required_periods} periods, have {available_periods}"
        )

        super().__init__(message)


class OptimizationError(RiskManagerError):
    """Raised when portfolio optimization fails."""

    def __init__(self, method: str, reason: str, details: dict = None):
        """
        Initialize OptimizationError.

        Args:
            method: Optimization method that failed (e.g., 'mean_variance', 'risk_parity')
            reason: Reason for failure
            details: Optional dictionary with additional error details
        """
        self.method = method
        self.reason = reason
        self.details = details or {}

        message = f"Optimization failed ({method}): {reason}"

        super().__init__(message)
