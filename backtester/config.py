"""
Backtest Configuration

This module contains the BacktestConfig dataclass which defines all configuration
options for running backtests.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable
import logging

from backtester.risk_manager import RiskLimits
from backtester.data_loader import Interval


@dataclass
class BacktestConfig:
    """
    Configuration for backtesting system.

    This class contains all settings for running a backtest, including capital,
    costs, risk management, position sizing, and UI options.

    Example:
        >>> config = BacktestConfig(
        ...     initial_capital=100000,
        ...     commission_rate=0.001,
        ...     enable_risk_checks=True
        ... )

    Attributes:
        initial_capital: Starting capital for the backtest
        commission_rate: Commission as percentage (0.001 = 0.1%)
        slippage_rate: Slippage as percentage (0.0005 = 0.05%)

        enable_risk_checks: Enable risk management monitoring
        risk_limits: RiskLimits instance (if None and risk checks enabled, uses conservative)
        risk_check_mode: How to handle risk violations - 'block', 'warn', or 'log'
        risk_calc_frequency: How often to calculate risk metrics (every N bars)
        on_risk_violation: Optional callback when risk violation occurs

        use_position_sizer: Enable advanced position sizing
        position_sizing_method: Method to use - 'equal', 'risk_based', 'kelly', etc.
        max_position_size: Maximum position size as fraction of portfolio (0.1 = 10%)
        risk_per_trade: Risk per trade as fraction of capital (for risk-based sizing)

        enable_rebalancing: Enable periodic portfolio rebalancing
        rebalance_frequency: Rebalance every N bars
        optimization_method: Method for rebalancing - 'equal_weight', 'risk_parity', etc.

        allow_short_selling: Allow short positions in the backtest

        show_progress: Display rich progress bar during backtest
        log_signals: Log all generated signals (verbose)

        on_bar_start: Optional callback called at start of each bar
        on_bar_end: Optional callback called at end of each bar
    """

    # ========================================================================
    # CORE SETTINGS
    # ========================================================================

    initial_capital: float = 100000.0
    """Starting capital for the backtest"""

    commission_rate: float = 0.001
    """Commission as percentage (0.001 = 0.1%)"""

    slippage_rate: float = 0.0005
    """Slippage as percentage (0.0005 = 0.05%)"""

    # ========================================================================
    # RISK MANAGEMENT SETTINGS
    # ========================================================================

    enable_risk_checks: bool = False
    """Enable risk management monitoring and enforcement"""

    risk_limits: Optional['RiskLimits'] = None
    """
    RiskLimits instance defining position sizes, drawdown limits, etc.
    If None and enable_risk_checks=True, will use RiskLimits.conservative()
    """

    risk_check_mode: str = 'warn'
    """
    How to handle risk violations:
    - 'block': Reject orders that violate limits
    - 'warn': Log warnings but allow orders
    - 'log': Silently log violations
    """

    risk_calc_frequency: int = 10
    """Calculate comprehensive risk metrics every N bars (for performance)"""

    on_risk_violation: Optional[Callable] = None
    """Optional callback function called when risk violation occurs"""

    # ========================================================================
    # POSITION SIZING SETTINGS
    # ========================================================================

    use_position_sizer: bool = False
    """Enable advanced position sizing algorithms"""

    position_sizing_method: str = 'equal'
    """
    Position sizing method to use:
    - 'equal': Equal allocation across positions
    - 'risk_based': Size based on fixed risk per trade
    - 'kelly': Kelly criterion
    - 'volatility_target': Target volatility
    - 'atr': ATR-based sizing
    - 'fixed_percent': Fixed percentage of capital
    - 'signal_strength': Size based on signal confidence
    - 'optimal_f': Optimal F
    """

    max_position_size: float = 0.1
    """Maximum position size as fraction of portfolio (0.1 = 10%)"""

    risk_per_trade: float = 0.01
    """Risk per trade as fraction of capital (for risk-based sizing, 0.01 = 1%)"""

    # ========================================================================
    # PORTFOLIO REBALANCING SETTINGS
    # ========================================================================

    enable_rebalancing: bool = False
    """Enable periodic portfolio rebalancing"""

    rebalance_frequency: int = 20
    """Rebalance portfolio every N bars"""

    optimization_method: str = 'equal_weight'
    """
    Portfolio optimization method:
    - 'equal_weight': Equal weight allocation
    - 'risk_parity': Risk parity allocation
    - 'mean_variance': Mean-variance optimization
    """

    # ========================================================================
    # TRADING SETTINGS
    # ========================================================================

    allow_short_selling: bool = False
    """Allow short positions in the backtest"""

    # ========================================================================
    # MULTI-TIMEFRAME SETTINGS
    # ========================================================================

    primary_interval: Optional['Interval'] = None
    """
    Which interval drives the event loop.
    If None, defaults to the `interval` passed to run().
    
    Use this when you want a specific timeframe to drive the backtest loop
    while accessing data from other timeframes. For example:
    - Set to Interval.DAY to drive loop with daily bars
    - Strategies can still access Interval.HOUR_1 or Interval.MINUTE_15 data
    
    Most strategies should leave this as None (auto-detect from run() interval).
    """

    # ========================================================================
    # UI AND LOGGING SETTINGS
    # ========================================================================

    show_progress: bool = True
    """Display rich progress bar during backtest"""

    log_signals: bool = False
    """Log all generated signals (verbose output)"""

    # ========================================================================
    # HOOKS AND CALLBACKS
    # ========================================================================

    on_bar_start: Optional[Callable] = None
    """
    Optional callback called at the start of each bar.
    Signature: on_bar_start(bar_index: int, timestamp: datetime, context: StrategyContext)
    """

    on_bar_end: Optional[Callable] = None
    """
    Optional callback called at the end of each bar.
    Signature: on_bar_end(bar_index: int, timestamp: datetime, context: StrategyContext)
    """

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate commission and slippage
        if self.commission_rate < 0:
            raise ValueError("commission_rate must be non-negative")
        if self.slippage_rate < 0:
            raise ValueError("slippage_rate must be non-negative")

        # Validate risk check mode
        valid_modes = {'block', 'warn', 'log'}
        if self.risk_check_mode not in valid_modes:
            raise ValueError(f"risk_check_mode must be one of {valid_modes}")

        # Validate position sizing method
        valid_methods = {
            'equal', 'risk_based', 'kelly', 'volatility_target',
            'atr', 'fixed_percent', 'signal_strength', 'optimal_f'
        }
        if self.position_sizing_method not in valid_methods:
            raise ValueError(f"position_sizing_method must be one of {valid_methods}")

        # Validate max position size
        if not 0 < self.max_position_size <= 1:
            raise ValueError("max_position_size must be between 0 and 1")

        if self.risk_per_trade <= 0:
            raise ValueError("risk_per_trade must be positive")
        if self.risk_per_trade > 0.1:
            logging.getLogger(__name__).warning(
                f"risk_per_trade={self.risk_per_trade:.1%} is very high (>10%)"
            )

        # Validate optimization method
        valid_optimization = {'equal_weight', 'risk_parity', 'mean_variance'}
        if self.optimization_method not in valid_optimization:
            raise ValueError(f"optimization_method must be one of {valid_optimization}")

        # Validate frequencies
        if self.risk_calc_frequency < 1:
            raise ValueError("risk_calc_frequency must be at least 1")
        if self.rebalance_frequency < 1:
            raise ValueError("rebalance_frequency must be at least 1")

    def summary(self) -> str:
        """Generate human-readable configuration summary."""
        risk_status = "Enabled" if self.enable_risk_checks else "Disabled"
        position_sizer_status = "Enabled" if self.use_position_sizer else "Disabled"
        rebalancing_status = "Enabled" if self.enable_rebalancing else "Disabled"
        primary_tf = self.primary_interval.value if self.primary_interval else "Auto (from run() interval)"

        return f"""
Backtest Configuration Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Core Settings:
  Initial Capital: Rs {self.initial_capital:,.2f}
  Commission Rate: {self.commission_rate * 100:.3f}%
  Slippage Rate: {self.slippage_rate * 100:.3f}%

Risk Management: {risk_status}
  Mode: {self.risk_check_mode}
  Calculation Frequency: Every {self.risk_calc_frequency} bars

Position Sizing: {position_sizer_status}
  Method: {self.position_sizing_method}
  Max Position Size: {self.max_position_size * 100:.1f}%
  Risk Per Trade: {self.risk_per_trade * 100:.1f}%

Portfolio Rebalancing: {rebalancing_status}
  Frequency: Every {self.rebalance_frequency} bars
  Method: {self.optimization_method}

Trading:
  Short Selling: {'Allowed' if self.allow_short_selling else 'Not Allowed'}

Multi-Timeframe:
  Primary Interval: {primary_tf}

UI:
  Progress Bar: {'Enabled' if self.show_progress else 'Disabled'}
  Signal Logging: {'Enabled' if self.log_signals else 'Disabled'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    @classmethod
    def conservative(cls) -> 'BacktestConfig':
        """
        Create a conservative configuration suitable for risk-averse strategies.

        Returns:
            BacktestConfig with conservative settings
        """
        from backtester.risk_manager import RiskLimits

        return cls(
            initial_capital=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,  # Higher slippage assumption
            enable_risk_checks=True,
            risk_limits=RiskLimits.conservative(),
            risk_check_mode='block',  # Block violating orders
            use_position_sizer=True,
            position_sizing_method='risk_based',
            max_position_size=0.05,  # Max 5% per position
            risk_per_trade=0.01,  # 1% risk per trade
            allow_short_selling=False
        )

    @classmethod
    def moderate(cls) -> 'BacktestConfig':
        """
        Create a moderate configuration balancing risk and returns.

        Returns:
            BacktestConfig with moderate settings
        """
        from backtester.risk_manager import RiskLimits

        return cls(
            initial_capital=100000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            enable_risk_checks=True,
            risk_limits=RiskLimits.moderate(),
            risk_check_mode='warn',  # Warn but allow
            use_position_sizer=True,
            position_sizing_method='risk_based',
            max_position_size=0.10,  # Max 10% per position
            risk_per_trade=0.02,  # 2% risk per trade
            allow_short_selling=True
        )

    @classmethod
    def aggressive(cls) -> 'BacktestConfig':
        """
        Create an aggressive configuration for higher risk tolerance.

        Returns:
            BacktestConfig with aggressive settings
        """
        from backtester.risk_manager import RiskLimits

        return cls(
            initial_capital=100000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            enable_risk_checks=True,
            risk_limits=RiskLimits.aggressive(),
            risk_check_mode='log',  # Just log violations
            use_position_sizer=True,
            position_sizing_method='kelly',
            max_position_size=0.20,  # Max 20% per position
            risk_per_trade=0.05,  # 5% risk per trade
            allow_short_selling=True
        )

    @classmethod
    def minimal(cls) -> 'BacktestConfig':
        """
        Create a minimal configuration for quick testing.

        Returns:
            BacktestConfig with minimal features enabled
        """
        return cls(
            initial_capital=100000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            show_progress=True,
            enable_risk_checks=False,
            use_position_sizer=False,
            enable_rebalancing=False
        )
