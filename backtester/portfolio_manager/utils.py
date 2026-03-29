"""
Utility functions for portfolio manager backtesting.

This module contains helper functions for commission and slippage calculations.
Note: Validation is handled by the model classes themselves.
"""

import logging

logger = logging.getLogger(__name__)


def calculate_commission(quantity, price_per_share, commission_rate, minimum_commission=1.0):
    """
    Calculate trading commission based on order parameters.

    Args:
        quantity (int/float): Number of shares
        price_per_share (float): Price per share
        commission_rate (float): Commission rate as a decimal (e.g., 0.0001 for 0.01%)
        minimum_commission (float): Minimum commission to charge (default: Rs.1.0)

    Returns:
        float: Commission amount in rupees
    """
    order_value = quantity * price_per_share
    calculated_commission = order_value * commission_rate

    # Apply minimum commission floor
    final_commission = max(calculated_commission, minimum_commission)

    logger.debug(
        f"Commission calculation: qty={quantity}, price={price_per_share}, "
        f"rate={commission_rate} -> Rs.{final_commission:.2f} "
        f"(minimum floor: Rs.{minimum_commission:.2f})"
    )
    return final_commission


def calculate_slippage(quantity, price, slippage_rate):
    """
    Estimate market impact and slippage for an order.

    Args:
        quantity (int/float): Number of shares
        price (float): Current/execution price
        slippage_rate (float): Slippage rate as a decimal (e.g., 0.0005 for 0.05%)

    Returns:
        float: Slippage amount in rupees
    """
    order_value = quantity * price
    slippage_amount = order_value * slippage_rate

    logger.debug(
        f"Slippage calculation: qty={quantity}, price={price}, "
        f"rate={slippage_rate} -> Rs.{slippage_amount:.2f}"
    )
    return slippage_amount
