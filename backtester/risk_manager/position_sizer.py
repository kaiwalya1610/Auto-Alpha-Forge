"""
Position Sizer - Position Sizing Strategies

Implements various position sizing methods including fixed sizing, risk-based,
Kelly criterion, volatility targeting, optimization-based approaches, and
discrete allocation using PyPortfolioOpt.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
import logging

from .models import RiskLimits, OptimizationResult
from .utils import calculate_volatility

# Try importing PyPortfolioOpt for discrete allocation
try:
    from pypfopt import DiscreteAllocation
    from pypfopt import expected_returns, risk_models
    HAS_PYPFOPT = True
except ImportError:
    HAS_PYPFOPT = False

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Position sizing logic for risk management.

    Provides multiple position sizing strategies to determine optimal position
    sizes based on risk parameters, signal strength, and portfolio constraints.

    Performance Target: < 5ms per position size calculation
    """

    def __init__(
        self,
        risk_limits: RiskLimits,
        annualization_factor: int = 252
    ):
        """
        Initialize PositionSizer.

        Args:
            risk_limits: Risk constraint definitions
            annualization_factor: Periods per year for volatility calculations
        """
        self.risk_limits = risk_limits
        self.annualization_factor = annualization_factor

    # ========================================================================
    # FIXED SIZE METHODS
    # ========================================================================

    def size_fixed(
        self,
        symbol: str,
        current_price: float,
        fixed_amount: float
    ) -> int:
        """
        Fixed dollar amount position sizing.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            fixed_amount: Fixed dollar amount to invest

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or fixed_amount <= 0:
            return 0

        quantity = int(fixed_amount / current_price)
        return quantity

    def size_fixed_percent(
        self,
        symbol: str,
        current_price: float,
        portfolio_value: float,
        percent: float
    ) -> int:
        """
        Fixed percentage of portfolio position sizing.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            portfolio_value: Total portfolio value
            percent: Percentage of portfolio (e.g., 0.05 for 5%)

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or portfolio_value <= 0 or percent <= 0:
            return 0

        # Apply position size limit
        max_pct = min(percent, self.risk_limits.max_position_pct)
        amount = portfolio_value * max_pct

        # Apply dollar limit if set
        if self.risk_limits.max_position_size is not None:
            amount = min(amount, self.risk_limits.max_position_size)

        quantity = int(amount / current_price)
        return quantity

    # ========================================================================
    # RISK-BASED SIZING
    # ========================================================================

    def size_risk_based(
        self,
        symbol: str,
        current_price: float,
        stop_distance: float,
        portfolio_value: float,
        risk_percent: float = 0.01
    ) -> int:
        """
        Position size based on fixed risk per trade.

        Formula: Position Size = (Portfolio Value × Risk %) / Stop Distance

        Args:
            symbol: Trading symbol
            current_price: Current market price
            stop_distance: Distance to stop loss in price units
            portfolio_value: Total portfolio value
            risk_percent: Risk per trade as decimal (e.g., 0.01 for 1%)

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or stop_distance <= 0 or portfolio_value <= 0:
            return 0

        # Calculate risk amount
        risk_amount = portfolio_value * risk_percent

        # Calculate shares based on risk
        quantity = int(risk_amount / stop_distance)

        # Apply position size limits
        max_quantity_by_pct = int((portfolio_value * self.risk_limits.max_position_pct) / current_price)
        quantity = min(quantity, max_quantity_by_pct)

        if self.risk_limits.max_position_size is not None:
            max_quantity_by_dollar = int(self.risk_limits.max_position_size / current_price)
            quantity = min(quantity, max_quantity_by_dollar)

        return max(0, quantity)

    def size_atr_based(
        self,
        symbol: str,
        current_price: float,
        atr: float,
        portfolio_value: float,
        risk_percent: float = 0.01,
        atr_multiplier: float = 2.0
    ) -> int:
        """
        Position size based on Average True Range (ATR).

        Stop distance is calculated as ATR × multiplier.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            atr: Average True Range value
            portfolio_value: Total portfolio value
            risk_percent: Risk per trade as decimal
            atr_multiplier: ATR multiplier for stop distance (typically 2-3)

        Returns:
            Number of shares/contracts
        """
        if atr <= 0:
            logger.warning(f"Invalid ATR {atr} for {symbol}, using 2% of price")
            atr = current_price * 0.02

        stop_distance = atr * atr_multiplier

        return self.size_risk_based(
            symbol=symbol,
            current_price=current_price,
            stop_distance=stop_distance,
            portfolio_value=portfolio_value,
            risk_percent=risk_percent
        )

    # ========================================================================
    # VOLATILITY TARGETING
    # ========================================================================

    def size_volatility_target(
        self,
        symbol: str,
        current_price: float,
        asset_volatility: float,
        portfolio_value: float,
        target_volatility: float = 0.15
    ) -> int:
        """
        Position size to achieve target portfolio volatility contribution.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            asset_volatility: Asset annualized volatility
            portfolio_value: Total portfolio value
            target_volatility: Target volatility contribution (e.g., 0.15 for 15%)

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or asset_volatility <= 0 or portfolio_value <= 0:
            return 0

        # Calculate target position value
        # Position Value = (Target Vol × Portfolio Value) / Asset Vol
        position_value = (target_volatility * portfolio_value) / asset_volatility

        # Apply limits
        max_position_value = portfolio_value * self.risk_limits.max_position_pct
        position_value = min(position_value, max_position_value)

        if self.risk_limits.max_position_size is not None:
            position_value = min(position_value, self.risk_limits.max_position_size)

        quantity = int(position_value / current_price)
        return max(0, quantity)

    # ========================================================================
    # KELLY CRITERION
    # ========================================================================

    def size_kelly(
        self,
        symbol: str,
        current_price: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        portfolio_value: float,
        kelly_fraction: float = 0.5
    ) -> int:
        """
        Position size using Kelly Criterion.

        Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Win

        Args:
            symbol: Trading symbol
            current_price: Current market price
            win_rate: Historical win rate (e.g., 0.55 for 55%)
            avg_win: Average win amount (as %)
            avg_loss: Average loss amount (as %)
            portfolio_value: Total portfolio value
            kelly_fraction: Fraction of Kelly to use (e.g., 0.5 for half-Kelly)

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or portfolio_value <= 0:
            return 0

        if win_rate <= 0 or win_rate >= 1:
            logger.warning(f"Invalid win_rate {win_rate}, using conservative sizing")
            return self.size_fixed_percent(symbol, current_price, portfolio_value, 0.05)

        if avg_win <= 0 or avg_loss <= 0:
            logger.warning(f"Invalid win/loss amounts, using conservative sizing")
            return self.size_fixed_percent(symbol, current_price, portfolio_value, 0.05)

        # Kelly formula
        loss_rate = 1 - win_rate
        kelly_pct = (win_rate * avg_win - loss_rate * avg_loss) / avg_win

        # Apply Kelly fraction for safety (typically 0.25 to 0.5)
        kelly_pct = kelly_pct * kelly_fraction

        # Ensure non-negative
        kelly_pct = max(0, kelly_pct)

        # Apply position limits
        kelly_pct = min(kelly_pct, self.risk_limits.max_position_pct)

        # Calculate quantity
        position_value = portfolio_value * kelly_pct

        if self.risk_limits.max_position_size is not None:
            position_value = min(position_value, self.risk_limits.max_position_size)

        quantity = int(position_value / current_price)
        return max(0, quantity)

    def size_kelly_from_sharpe(
        self,
        symbol: str,
        current_price: float,
        sharpe_ratio: float,
        portfolio_value: float,
        kelly_fraction: float = 0.5
    ) -> int:
        """
        Position size using Kelly Criterion approximation from Sharpe ratio.

        Kelly % ≈ Sharpe Ratio × (Expected Return / Volatility)

        Args:
            symbol: Trading symbol
            current_price: Current market price
            sharpe_ratio: Strategy Sharpe ratio
            portfolio_value: Total portfolio value
            kelly_fraction: Fraction of Kelly to use

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or portfolio_value <= 0 or sharpe_ratio <= 0:
            return 0

        # Approximation: Kelly % ≈ Sharpe² / 2
        kelly_pct = (sharpe_ratio ** 2) / 2

        # Apply Kelly fraction
        kelly_pct = kelly_pct * kelly_fraction

        # Apply position limits
        kelly_pct = min(kelly_pct, self.risk_limits.max_position_pct)

        # Calculate quantity
        position_value = portfolio_value * kelly_pct

        if self.risk_limits.max_position_size is not None:
            position_value = min(position_value, self.risk_limits.max_position_size)

        quantity = int(position_value / current_price)
        return max(0, quantity)

    # ========================================================================
    # RISK PARITY
    # ========================================================================

    def size_risk_parity(
        self,
        symbol: str,
        current_price: float,
        asset_volatility: float,
        portfolio_value: float,
        num_positions: int
    ) -> int:
        """
        Risk parity position sizing (equal risk contribution).

        Each position contributes equally to portfolio risk.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            asset_volatility: Asset annualized volatility
            portfolio_value: Total portfolio value
            num_positions: Total number of positions in portfolio

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or asset_volatility <= 0 or portfolio_value <= 0 or num_positions <= 0:
            return 0

        # Each position gets 1/N of the risk budget
        risk_per_position = 1.0 / num_positions

        # Position value inversely proportional to volatility
        # Weight_i = (1/Vol_i) / Σ(1/Vol_j)
        # For equal risk: Position Value = Risk Budget / Volatility
        position_value = (risk_per_position * portfolio_value) / asset_volatility

        # Normalize if needed (this assumes all assets have similar vol scaling)
        # For more accurate risk parity, use optimization

        # Apply limits
        max_position_value = portfolio_value * self.risk_limits.max_position_pct
        position_value = min(position_value, max_position_value)

        if self.risk_limits.max_position_size is not None:
            position_value = min(position_value, self.risk_limits.max_position_size)

        quantity = int(position_value / current_price)
        return max(0, quantity)

    # ========================================================================
    # OPTIMIZATION-BASED SIZING
    # ========================================================================

    def size_optimal(
        self,
        symbol: str,
        current_price: float,
        optimization_result: OptimizationResult,
        portfolio_value: float
    ) -> int:
        """
        Position size from portfolio optimization.

        Uses optimal weights from portfolio optimizer.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            optimization_result: Result from PortfolioOptimizer
            portfolio_value: Total portfolio value

        Returns:
            Number of shares/contracts
        """
        if current_price <= 0 or portfolio_value <= 0:
            return 0

        # Get optimal weight for this symbol
        optimal_weight = optimization_result.weights.get(symbol, 0.0)

        if optimal_weight <= 0:
            return 0

        # Calculate position value from weight
        position_value = portfolio_value * optimal_weight

        # Apply limits (optimizer should respect these, but double-check)
        max_position_value = portfolio_value * self.risk_limits.max_position_pct
        position_value = min(position_value, max_position_value)

        if self.risk_limits.max_position_size is not None:
            position_value = min(position_value, self.risk_limits.max_position_size)

        quantity = int(position_value / current_price)
        return max(0, quantity)

    # ========================================================================
    # SIGNAL STRENGTH ADJUSTMENT
    # ========================================================================

    def adjust_for_signal_strength(
        self,
        base_quantity: int,
        signal_strength: float,
        signal_confidence: float
    ) -> int:
        """
        Adjust position size based on signal strength and confidence.

        Args:
            base_quantity: Base quantity from sizing method
            signal_strength: Signal strength (0.0 - 1.0)
            signal_confidence: Signal confidence (0.0 - 1.0)

        Returns:
            Adjusted quantity
        """
        if base_quantity <= 0:
            return 0

        # Combined adjustment factor
        adjustment_factor = signal_strength * signal_confidence

        # Ensure reasonable bounds
        adjustment_factor = np.clip(adjustment_factor, 0.0, 1.0)

        adjusted_quantity = int(base_quantity * adjustment_factor)
        return max(0, adjusted_quantity)

    # ========================================================================
    # AVAILABLE CAPITAL CHECKING
    # ========================================================================

    def check_available_capital(
        self,
        quantity: int,
        current_price: float,
        available_cash: float,
        leverage: float = 1.0
    ) -> int:
        """
        Ensure position doesn't exceed available capital.

        Args:
            quantity: Desired quantity
            current_price: Current market price
            available_cash: Available cash
            leverage: Available leverage

        Returns:
            Adjusted quantity that fits within capital constraints
        """
        if quantity <= 0 or current_price <= 0 or available_cash <= 0:
            return 0

        # Calculate maximum quantity possible with available capital
        max_buyable = int((available_cash * leverage) / current_price)

        # Return minimum of desired and affordable
        return min(quantity, max_buyable)

    # ========================================================================
    # MAIN POSITION SIZING METHOD
    # ========================================================================

    def calculate_position_size(
        self,
        symbol: str,
        current_price: float,
        portfolio_value: float,
        available_cash: float,
        method: str = 'risk_based',
        signal_strength: float = 1.0,
        signal_confidence: float = 1.0,
        **kwargs
    ) -> int:
        """
        Main entry point for position sizing.

        Calculates position size using specified method and applies
        signal strength adjustment and capital constraints.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            portfolio_value: Total portfolio value
            available_cash: Available cash
            method: Sizing method ('fixed_pct', 'risk_based', 'kelly', 'volatility_target', 'risk_parity', 'optimal')
            signal_strength: Signal strength (0.0 - 1.0)
            signal_confidence: Signal confidence (0.0 - 1.0)
            **kwargs: Additional parameters for specific methods

        Returns:
            Final position size (number of shares/contracts)

        Example:
            >>> sizer = PositionSizer(risk_limits)
            >>> quantity = sizer.calculate_position_size(
            ...     symbol='SBIN',
            ...     current_price=500.0,
            ...     portfolio_value=100000.0,
            ...     available_cash=50000.0,
            ...     method='risk_based',
            ...     stop_distance=20.0,
            ...     risk_percent=0.01
            ... )
        """
        # Calculate base quantity using selected method
        if method == 'fixed_pct':
            percent = kwargs.get('percent', 0.05)
            base_quantity = self.size_fixed_percent(symbol, current_price, portfolio_value, percent)

        elif method == 'risk_based':
            stop_distance = kwargs.get('stop_distance')
            if stop_distance is None:
                raise ValueError("stop_distance required for risk_based method")
            risk_percent = kwargs.get('risk_percent', 0.01)
            base_quantity = self.size_risk_based(symbol, current_price, stop_distance, portfolio_value, risk_percent)

        elif method == 'atr_based':
            atr = kwargs.get('atr')
            if atr is None:
                raise ValueError("atr required for atr_based method")
            risk_percent = kwargs.get('risk_percent', 0.01)
            atr_multiplier = kwargs.get('atr_multiplier', 2.0)
            base_quantity = self.size_atr_based(symbol, current_price, atr, portfolio_value, risk_percent, atr_multiplier)

        elif method == 'volatility_target':
            asset_volatility = kwargs.get('asset_volatility')
            if asset_volatility is None:
                raise ValueError("asset_volatility required for volatility_target method")
            target_volatility = kwargs.get('target_volatility', 0.15)
            base_quantity = self.size_volatility_target(symbol, current_price, asset_volatility, portfolio_value, target_volatility)

        elif method == 'kelly':
            win_rate = kwargs.get('win_rate')
            avg_win = kwargs.get('avg_win')
            avg_loss = kwargs.get('avg_loss')
            if None in (win_rate, avg_win, avg_loss):
                raise ValueError("win_rate, avg_win, avg_loss required for kelly method")
            kelly_fraction = kwargs.get('kelly_fraction', 0.5)
            base_quantity = self.size_kelly(symbol, current_price, win_rate, avg_win, avg_loss, portfolio_value, kelly_fraction)

        elif method == 'risk_parity':
            asset_volatility = kwargs.get('asset_volatility')
            num_positions = kwargs.get('num_positions')
            if None in (asset_volatility, num_positions):
                raise ValueError("asset_volatility, num_positions required for risk_parity method")
            base_quantity = self.size_risk_parity(symbol, current_price, asset_volatility, portfolio_value, num_positions)

        elif method == 'optimal':
            optimization_result = kwargs.get('optimization_result')
            if optimization_result is None:
                raise ValueError("optimization_result required for optimal method")
            base_quantity = self.size_optimal(symbol, current_price, optimization_result, portfolio_value)

        else:
            raise ValueError(f"Unknown sizing method: {method}")

        # Adjust for signal strength
        adjusted_quantity = self.adjust_for_signal_strength(base_quantity, signal_strength, signal_confidence)

        # Check capital constraints
        final_quantity = self.check_available_capital(
            adjusted_quantity,
            current_price,
            available_cash,
            leverage=self.risk_limits.max_leverage
        )

        logger.debug(
            f"Position sizing for {symbol}: method={method}, base={base_quantity}, "
            f"adjusted={adjusted_quantity}, final={final_quantity}"
        )

        return final_quantity

    # ========================================================================
    # DISCRETE ALLOCATION (PyPortfolioOpt)
    # ========================================================================

    def allocate_discrete(
        self,
        weights: Dict[str, float],
        latest_prices: Dict[str, float],
        total_portfolio_value: float,
        short_ratio: float = 0.0
    ) -> Tuple[Dict[str, int], float]:
        """
        Convert continuous portfolio weights to discrete share quantities using PyPortfolioOpt.

        This method uses greedy allocation to determine the exact number of shares
        to purchase for each asset while respecting the total portfolio value.

        Args:
            weights: Target portfolio weights {symbol: weight}
            latest_prices: Current prices {symbol: price}
            total_portfolio_value: Total portfolio value for allocation
            short_ratio: Ratio of short positions allowed (0.0 = no shorting)

        Returns:
            Tuple of (allocation {symbol: shares}, leftover_cash)

        Raises:
            ValueError: If PyPortfolioOpt not available or invalid inputs
        """
        if not HAS_PYPFOPT:
            logger.warning("PyPortfolioOpt not available, using fallback discrete allocation")
            return self._fallback_discrete_allocation(weights, latest_prices, total_portfolio_value)

        try:
            # Create DiscreteAllocation object
            da = DiscreteAllocation(
                weights,
                latest_prices,
                total_portfolio_value=total_portfolio_value,
                short_ratio=short_ratio
            )

            # Get greedy allocation
            allocation, leftover = da.greedy_portfolio()

            logger.info(
                f"Discrete allocation: {len(allocation)} positions, "
                f"₹{leftover:,.2f} leftover from ₹{total_portfolio_value:,.2f}"
            )

            return allocation, leftover

        except Exception as e:
            logger.error(f"PyPortfolioOpt discrete allocation failed: {e}, using fallback")
            return self._fallback_discrete_allocation(weights, latest_prices, total_portfolio_value)

    def allocate_discrete_lp(
        self,
        weights: Dict[str, float],
        latest_prices: Dict[str, float],
        total_portfolio_value: float,
        reinvest: bool = False
    ) -> Tuple[Dict[str, int], float]:
        """
        Convert continuous weights to discrete shares using Linear Programming.

        LP allocation minimizes the deviation from target weights, potentially
        providing better allocations than greedy method for complex cases.

        Args:
            weights: Target portfolio weights {symbol: weight}
            latest_prices: Current prices {symbol: price}
            total_portfolio_value: Total portfolio value for allocation
            reinvest: Whether to reinvest leftover cash

        Returns:
            Tuple of (allocation {symbol: shares}, leftover_cash)
        """
        if not HAS_PYPFOPT:
            logger.warning("PyPortfolioOpt not available, using fallback")
            return self._fallback_discrete_allocation(weights, latest_prices, total_portfolio_value)

        try:
            # Create DiscreteAllocation object
            da = DiscreteAllocation(
                weights,
                latest_prices,
                total_portfolio_value=total_portfolio_value
            )

            # Get LP allocation
            allocation, leftover = da.lp_portfolio(reinvest=reinvest)

            logger.info(
                f"LP discrete allocation: {len(allocation)} positions, "
                f"₹{leftover:,.2f} leftover (reinvest={reinvest})"
            )

            return allocation, leftover

        except Exception as e:
            logger.error(f"LP discrete allocation failed: {e}, using greedy fallback")
            # Try greedy as fallback
            try:
                da = DiscreteAllocation(weights, latest_prices, total_portfolio_value=total_portfolio_value)
                return da.greedy_portfolio()
            except Exception as e:
                logger.warning(f"Greedy allocation also failed: {e}, using proportional fallback")
                return self._fallback_discrete_allocation(weights, latest_prices, total_portfolio_value)

    def _fallback_discrete_allocation(
        self,
        weights: Dict[str, float],
        latest_prices: Dict[str, float],
        total_portfolio_value: float
    ) -> Tuple[Dict[str, int], float]:
        """
        Fallback discrete allocation when PyPortfolioOpt is not available.

        Uses a simple greedy algorithm to allocate shares.

        Args:
            weights: Target portfolio weights {symbol: weight}
            latest_prices: Current prices {symbol: price}
            total_portfolio_value: Total portfolio value

        Returns:
            Tuple of (allocation {symbol: shares}, leftover_cash)
        """
        allocation = {}
        remaining_value = total_portfolio_value

        # Sort by weight (descending) to allocate largest positions first
        sorted_symbols = sorted(weights.items(), key=lambda x: x[1], reverse=True)

        for symbol, weight in sorted_symbols:
            if symbol not in latest_prices or weight <= 0:
                continue

            price = latest_prices[symbol]
            if price <= 0:
                continue

            # Calculate target value for this position
            target_value = total_portfolio_value * weight

            # Calculate number of shares
            shares = int(target_value / price)

            # Only allocate if we have enough cash
            required_cash = shares * price
            if required_cash <= remaining_value:
                allocation[symbol] = shares
                remaining_value -= required_cash

        leftover = remaining_value

        logger.info(
            f"Fallback discrete allocation: {len(allocation)} positions, "
            f"₹{leftover:,.2f} leftover from ₹{total_portfolio_value:,.2f}"
        )

        return allocation, leftover

    def get_rebalancing_orders(
        self,
        target_allocation: Dict[str, int],
        current_positions: Dict[str, int]
    ) -> List[Tuple[str, int, str]]:
        """
        Calculate rebalancing orders to reach target allocation.

        Args:
            target_allocation: Target positions {symbol: shares}
            current_positions: Current positions {symbol: shares}

        Returns:
            List of (symbol, quantity, action) where action is 'BUY' or 'SELL'
        """
        orders = []

        # All symbols (current + target)
        all_symbols = set(current_positions.keys()) | set(target_allocation.keys())

        for symbol in all_symbols:
            current_qty = current_positions.get(symbol, 0)
            target_qty = target_allocation.get(symbol, 0)

            diff = target_qty - current_qty

            if diff > 0:
                orders.append((symbol, diff, 'BUY'))
            elif diff < 0:
                orders.append((symbol, abs(diff), 'SELL'))
            # diff == 0: no change needed

        # Sort by absolute quantity (largest first)
        orders.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"Generated {len(orders)} rebalancing orders")

        return orders
