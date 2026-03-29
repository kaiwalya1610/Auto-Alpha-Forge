"""
Risk Management Core Data Models

Defines immutable data structures for risk metrics, limits, and events.
All models follow the frozen dataclass pattern for consistency with the backtester.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Tuple
import numpy as np


# ============================================================================
# ENUMS
# ============================================================================

class RiskAlertLevel(IntEnum):
    """Alert severity levels for risk monitoring."""
    INFO = 1        # Approaching limit (80% utilization)
    WARNING = 2     # Soft limit breached
    ERROR = 3       # Hard limit breached
    CRITICAL = 4    # Circuit breaker triggered


class RiskAlertType(Enum):
    """Types of risk alerts."""
    POSITION_LIMIT = "position_limit"
    PORTFOLIO_VAR = "portfolio_var"
    DRAWDOWN = "drawdown"
    LEVERAGE = "leverage"
    CONCENTRATION = "concentration"
    CORRELATION = "correlation"
    VOLATILITY = "volatility"


# ============================================================================
# POSITION RISK
# ============================================================================

@dataclass(frozen=True)
class PositionRisk:
    """
    Risk metrics for an individual position.

    Provides comprehensive risk analysis for a single position including
    volatility, VaR, correlation, and contribution to portfolio risk.
    """

    # Position identification
    symbol: str
    quantity: float
    market_value: float

    # Position metrics
    weight: float                        # % of portfolio
    volatility: float                    # Annualized volatility
    var_95: float                        # 95% Value at Risk
    cvar_95: float                       # 95% Conditional VaR
    beta: float                          # Market beta

    # Contribution to portfolio risk
    marginal_var: float                  # Marginal contribution to VaR
    component_var: float                 # Total contribution to VaR
    risk_contribution_pct: float         # % of total portfolio risk

    # Correlations
    avg_correlation: float               # Avg correlation with other positions
    max_correlation: float               # Max correlation with any position
    correlated_symbols: List[str] = field(default_factory=list)  # Highly correlated (>0.7) symbols

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'symbol': self.symbol,
            'quantity': self.quantity,
            'market_value': self.market_value,
            'weight': self.weight,
            'volatility': self.volatility,
            'var_95': self.var_95,
            'cvar_95': self.cvar_95,
            'beta': self.beta,
            'marginal_var': self.marginal_var,
            'component_var': self.component_var,
            'risk_contribution_pct': self.risk_contribution_pct,
            'avg_correlation': self.avg_correlation,
            'max_correlation': self.max_correlation,
            'correlated_symbols': self.correlated_symbols
        }


# ============================================================================
# RISK EVENT
# ============================================================================

@dataclass(frozen=True)
class RiskEvent:
    """
    Represents a risk limit violation or alert.

    Immutable record of risk events for logging and analysis.
    """

    timestamp: datetime
    alert_type: RiskAlertType
    alert_level: RiskAlertLevel
    symbol: Optional[str]               # None for portfolio-level events
    current_value: float
    limit_value: float
    message: str
    metadata: Dict = field(default_factory=dict)

    @property
    def utilization(self) -> float:
        """Calculate limit utilization percentage."""
        if self.limit_value == 0:
            return 0.0
        return (self.current_value / self.limit_value) * 100

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'alert_type': self.alert_type.value,
            'alert_level': self.alert_level.name,
            'symbol': self.symbol,
            'current_value': self.current_value,
            'limit_value': self.limit_value,
            'utilization': self.utilization,
            'message': self.message,
            'metadata': self.metadata
        }


# ============================================================================
# RISK METRICS
# ============================================================================

@dataclass(frozen=True)
class RiskMetrics:
    """
    Complete portfolio risk snapshot at a point in time.

    Immutable snapshot of all risk metrics including volatility, VaR,
    drawdown, and per-position risk decomposition.
    """

    # Timestamp
    timestamp: datetime

    # Portfolio state
    portfolio_value: float
    cash: float
    positions_value: float
    leverage: float

    # Volatility metrics (annualized)
    portfolio_volatility: float          # Annualized portfolio volatility
    portfolio_var_95: float              # 95% Value at Risk
    portfolio_cvar_95: float             # 95% Conditional VaR

    # Drawdown metrics
    current_drawdown: float              # Current DD from peak
    max_drawdown: float                  # Historical max DD
    avg_drawdown: float                  # Average DD
    cdar_95: float                       # Conditional Drawdown at Risk

    # Return metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Risk decomposition
    position_risks: Dict[str, PositionRisk] = field(default_factory=dict)
    correlation_matrix: Optional[np.ndarray] = None
    sector_exposure: Dict[str, float] = field(default_factory=dict)

    # Risk limits status
    violations: List[RiskEvent] = field(default_factory=list)
    utilization: Dict[str, float] = field(default_factory=dict)  # Limit utilization percentages

    def has_violations(self) -> bool:
        """Check if there are any active violations."""
        return len(self.violations) > 0

    def get_violations_by_level(self, level: RiskAlertLevel) -> List[RiskEvent]:
        """Get violations of a specific severity level."""
        return [v for v in self.violations if v.alert_level == level]

    def get_critical_violations(self) -> List[RiskEvent]:
        """Get only critical violations."""
        return self.get_violations_by_level(RiskAlertLevel.CRITICAL)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'portfolio_value': self.portfolio_value,
            'cash': self.cash,
            'positions_value': self.positions_value,
            'leverage': self.leverage,
            'portfolio_volatility': self.portfolio_volatility,
            'portfolio_var_95': self.portfolio_var_95,
            'portfolio_cvar_95': self.portfolio_cvar_95,
            'current_drawdown': self.current_drawdown,
            'max_drawdown': self.max_drawdown,
            'avg_drawdown': self.avg_drawdown,
            'cdar_95': self.cdar_95,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'position_risks': {symbol: risk.to_dict() for symbol, risk in self.position_risks.items()},
            'sector_exposure': self.sector_exposure,
            'violations': [v.to_dict() for v in self.violations],
            'utilization': self.utilization
        }


# ============================================================================
# RISK LIMITS
# ============================================================================

@dataclass
class RiskLimits:
    """
    Risk constraint definitions (mutable configuration).

    Defines all risk limits and constraints for portfolio management.
    Unlike other models, this is mutable to allow dynamic adjustment.
    """

    # Position limits
    max_position_size: Optional[float] = None      # Max $ per position
    max_position_pct: float = 0.10                 # Max 10% per position
    max_sector_pct: float = 0.30                   # Max 30% per sector

    # Portfolio limits
    max_leverage: float = 1.0                      # No leverage by default
    max_portfolio_var_95: Optional[float] = None   # Max portfolio VaR
    max_portfolio_volatility: float = 0.25         # Max 25% annualized vol

    # Drawdown limits
    max_drawdown: float = 0.20                     # Max 20% drawdown
    stop_trading_drawdown: float = 0.15            # Halt at 15% DD

    # Correlation limits
    max_avg_correlation: float = 0.70              # Max avg correlation
    max_concentrated_positions: int = 5            # Max positions >5%

    # Diversification
    min_positions: int = 5                         # Minimum diversification
    max_single_bet: float = 0.15                   # Max 15% in one position

    # Risk parity settings (optional)
    risk_parity_method: str = 'volatility'         # 'volatility', 'cvar', 'var'
    rebalance_threshold: float = 0.05              # Rebalance if >5% deviation

    def validate(self) -> List[str]:
        """
        Validate risk limits configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if self.max_position_pct <= 0 or self.max_position_pct > 1:
            errors.append(f"max_position_pct must be in (0, 1], got {self.max_position_pct}")

        if self.max_sector_pct <= 0 or self.max_sector_pct > 1:
            errors.append(f"max_sector_pct must be in (0, 1], got {self.max_sector_pct}")

        if self.max_leverage < 0:
            errors.append(f"max_leverage cannot be negative, got {self.max_leverage}")

        if self.max_portfolio_volatility <= 0:
            errors.append(f"max_portfolio_volatility must be positive, got {self.max_portfolio_volatility}")

        if self.max_drawdown <= 0 or self.max_drawdown > 1:
            errors.append(f"max_drawdown must be in (0, 1], got {self.max_drawdown}")

        if self.stop_trading_drawdown <= 0 or self.stop_trading_drawdown > 1:
            errors.append(f"stop_trading_drawdown must be in (0, 1], got {self.stop_trading_drawdown}")

        if self.stop_trading_drawdown > self.max_drawdown:
            errors.append(
                f"stop_trading_drawdown ({self.stop_trading_drawdown}) should not exceed "
                f"max_drawdown ({self.max_drawdown})"
            )

        if self.min_positions <= 0:
            errors.append(f"min_positions must be positive, got {self.min_positions}")

        if self.max_single_bet <= 0 or self.max_single_bet > 1:
            errors.append(f"max_single_bet must be in (0, 1], got {self.max_single_bet}")

        if self.risk_parity_method not in ['volatility', 'cvar', 'var']:
            errors.append(f"risk_parity_method must be 'volatility', 'cvar', or 'var', got {self.risk_parity_method}")

        return errors

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'max_position_size': self.max_position_size,
            'max_position_pct': self.max_position_pct,
            'max_sector_pct': self.max_sector_pct,
            'max_leverage': self.max_leverage,
            'max_portfolio_var_95': self.max_portfolio_var_95,
            'max_portfolio_volatility': self.max_portfolio_volatility,
            'max_drawdown': self.max_drawdown,
            'stop_trading_drawdown': self.stop_trading_drawdown,
            'max_avg_correlation': self.max_avg_correlation,
            'max_concentrated_positions': self.max_concentrated_positions,
            'min_positions': self.min_positions,
            'max_single_bet': self.max_single_bet,
            'risk_parity_method': self.risk_parity_method,
            'rebalance_threshold': self.rebalance_threshold
        }

    @classmethod
    def conservative(cls) -> 'RiskLimits':
        """Create conservative risk profile."""
        return cls(
            max_position_pct=0.05,           # Max 5% per position
            max_sector_pct=0.20,             # Max 20% per sector
            max_leverage=1.0,                # No leverage
            max_drawdown=0.10,               # Max 10% drawdown
            stop_trading_drawdown=0.08,      # Stop at 8% DD
            max_portfolio_volatility=0.15,   # Max 15% volatility
            max_avg_correlation=0.60,        # Low correlation
            min_positions=10                 # Force diversification
        )

    @classmethod
    def moderate(cls) -> 'RiskLimits':
        """Create moderate risk profile."""
        return cls(
            max_position_pct=0.10,           # Max 10% per position
            max_sector_pct=0.30,             # Max 30% per sector
            max_leverage=1.5,                # 1.5× leverage allowed
            max_drawdown=0.20,               # Max 20% drawdown
            stop_trading_drawdown=0.15,      # Stop at 15% DD
            max_portfolio_volatility=0.25,   # Max 25% volatility
            max_avg_correlation=0.70,        # Moderate correlation
            min_positions=5                  # Moderate diversification
        )

    @classmethod
    def aggressive(cls) -> 'RiskLimits':
        """Create aggressive risk profile."""
        return cls(
            max_position_pct=0.20,           # Max 20% per position
            max_sector_pct=0.50,             # Max 50% per sector
            max_leverage=2.0,                # 2× leverage allowed
            max_drawdown=0.30,               # Max 30% drawdown
            stop_trading_drawdown=0.25,      # Stop at 25% DD
            max_portfolio_volatility=0.40,   # Max 40% volatility
            max_avg_correlation=0.80,        # Higher correlation OK
            min_positions=3                  # Less diversification
        )


# ============================================================================
# OPTIMIZATION RESULT
# ============================================================================

@dataclass(frozen=True)
class OptimizationResult:
    """
    Portfolio optimization output.

    Immutable result of portfolio optimization containing optimal weights,
    expected metrics, and rebalancing instructions.
    """

    timestamp: datetime
    method: str                          # 'mean_variance', 'risk_parity', etc.

    # Optimal weights
    weights: Dict[str, float]            # Symbol -> weight
    expected_return: float               # Expected portfolio return
    expected_volatility: float           # Expected portfolio volatility
    expected_sharpe: float               # Expected Sharpe ratio

    # Risk metrics
    expected_var_95: float
    expected_cvar_95: float
    max_drawdown_estimate: float

    # Optimization metadata
    objective_value: float               # Optimization objective value
    convergence_status: str              # 'optimal', 'suboptimal', 'failed'
    solver_time_ms: float                # Computation time

    # Actions to reach optimal
    rebalancing_trades: List[Tuple[str, float]] = field(default_factory=list)  # (symbol, target_qty)
    turnover: float = 0.0                # Total turnover required

    @property
    def is_optimal(self) -> bool:
        """Check if optimization converged to optimal solution."""
        return self.convergence_status == 'optimal'

    @property
    def num_positions(self) -> int:
        """Get number of positions in optimal portfolio."""
        return sum(1 for w in self.weights.values() if abs(w) > 1e-6)

    def get_significant_weights(self, threshold: float = 0.01) -> Dict[str, float]:
        """Get weights above a threshold (default 1%)."""
        return {symbol: weight for symbol, weight in self.weights.items() if abs(weight) >= threshold}

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'method': self.method,
            'weights': self.weights,
            'expected_return': self.expected_return,
            'expected_volatility': self.expected_volatility,
            'expected_sharpe': self.expected_sharpe,
            'expected_var_95': self.expected_var_95,
            'expected_cvar_95': self.expected_cvar_95,
            'max_drawdown_estimate': self.max_drawdown_estimate,
            'objective_value': self.objective_value,
            'convergence_status': self.convergence_status,
            'solver_time_ms': self.solver_time_ms,
            'rebalancing_trades': self.rebalancing_trades,
            'turnover': self.turnover,
            'num_positions': self.num_positions
        }
