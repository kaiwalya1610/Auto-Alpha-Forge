"""
Risk Management Module for Backtesting Engine

This module provides comprehensive risk management capabilities including:
- Pre-trade risk assessment and position sizing
- Portfolio optimization and rebalancing
- Real-time risk monitoring and limits enforcement
- Post-trade risk analytics and reporting

Author: Zerodha Algo Trading Infrastructure
"""

from .models import (
    RiskMetrics,
    RiskLimits,
    RiskEvent,
    PositionRisk,
    OptimizationResult,
    RiskAlertLevel,
    RiskAlertType
)

from .exceptions import (
    RiskManagerError,
    RiskLimitViolation,
    InsufficientDataError,
    OptimizationError
)

from .risk_calculator import RiskCalculator
from .position_sizer import PositionSizer
from .portfolio_optimizer import PortfolioOptimizer
from .risk_monitor import RiskMonitor

__all__ = [
    # Core Models
    'RiskMetrics',
    'RiskLimits',
    'RiskEvent',
    'PositionRisk',
    'OptimizationResult',
    'RiskAlertLevel',
    'RiskAlertType',

    # Exceptions
    'RiskManagerError',
    'RiskLimitViolation',
    'InsufficientDataError',
    'OptimizationError',

    # Core Components
    'RiskCalculator',
    'PositionSizer',
    'PortfolioOptimizer',
    'RiskMonitor',
]

__version__ = '1.0.0'
