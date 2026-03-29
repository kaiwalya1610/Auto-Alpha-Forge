"""
Risk Monitor - Real-time Risk Monitoring and Enforcement

Monitors portfolio risk in real-time and enforces risk limits. Generates
alerts and violations when limits are breached.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging

from .models import (
    RiskLimits,
    RiskEvent,
    RiskAlertLevel,
    RiskAlertType,
    RiskMetrics
)
from .exceptions import RiskLimitViolation

logger = logging.getLogger(__name__)


class RiskMonitor:
    """
    Real-time risk limits enforcement.

    Monitors portfolio state continuously and checks against defined risk limits.
    Generates RiskEvent objects for violations and calculates limit utilization.

    Performance Target: < 10ms for complete risk check
    """

    def __init__(
        self,
        risk_limits: RiskLimits,
        halt_on_critical: bool = True
    ):
        """
        Initialize RiskMonitor.

        Args:
            risk_limits: Risk constraint definitions
            halt_on_critical: Whether to halt trading on critical violations
        """
        self.risk_limits = risk_limits
        self.halt_on_critical = halt_on_critical

        # Validation
        validation_errors = risk_limits.validate()
        if validation_errors:
            logger.warning(f"Risk limits validation errors: {validation_errors}")

        # State tracking
        self._trading_halted = False
        self._violation_history: List[RiskEvent] = []

    # ========================================================================
    # POSITION LIMITS CHECKING
    # ========================================================================

    def check_position_limits(
        self,
        symbol: str,
        position_value: float,
        portfolio_value: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check position-level limits.

        Args:
            symbol: Trading symbol
            position_value: Market value of position
            portfolio_value: Total portfolio value
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if portfolio_value <= 0:
            return violations

        # Calculate position weight
        position_weight = abs(position_value) / portfolio_value

        # Check max position percentage
        if position_weight > self.risk_limits.max_position_pct:
            utilization = (position_weight / self.risk_limits.max_position_pct) * 100

            if utilization >= 120:  # 20% over limit
                alert_level = RiskAlertLevel.CRITICAL
            elif utilization >= 110:
                alert_level = RiskAlertLevel.ERROR
            elif utilization >= 100:
                alert_level = RiskAlertLevel.WARNING
            else:
                alert_level = RiskAlertLevel.INFO

            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.POSITION_LIMIT,
                alert_level=alert_level,
                symbol=symbol,
                current_value=position_weight,
                limit_value=self.risk_limits.max_position_pct,
                message=f"Position size limit exceeded for {symbol}: "
                       f"{position_weight*100:.2f}% (limit: {self.risk_limits.max_position_pct*100:.2f}%)"
            )
            violations.append(event)

        # Check max position size (dollar limit)
        if self.risk_limits.max_position_size is not None:
            if abs(position_value) > self.risk_limits.max_position_size:
                event = RiskEvent(
                    timestamp=timestamp,
                    alert_type=RiskAlertType.POSITION_LIMIT,
                    alert_level=RiskAlertLevel.WARNING,
                    symbol=symbol,
                    current_value=abs(position_value),
                    limit_value=self.risk_limits.max_position_size,
                    message=f"Position dollar limit exceeded for {symbol}: "
                           f"${abs(position_value):,.2f} (limit: ${self.risk_limits.max_position_size:,.2f})"
                )
                violations.append(event)

        return violations

    # ========================================================================
    # PORTFOLIO LIMITS CHECKING
    # ========================================================================

    def check_portfolio_limits(
        self,
        portfolio_value: float,
        positions_value: float,
        cash: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check portfolio-level limits.

        Args:
            portfolio_value: Total portfolio value
            positions_value: Total value of positions
            cash: Available cash
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if portfolio_value <= 0:
            return violations

        # Calculate leverage
        total_exposure = abs(positions_value)
        leverage = total_exposure / portfolio_value if portfolio_value > 0 else 0.0

        # Check max leverage
        if leverage > self.risk_limits.max_leverage:
            utilization = (leverage / self.risk_limits.max_leverage) * 100

            if utilization >= 120:
                alert_level = RiskAlertLevel.CRITICAL
            elif utilization >= 110:
                alert_level = RiskAlertLevel.ERROR
            elif utilization >= 100:
                alert_level = RiskAlertLevel.WARNING
            else:
                alert_level = RiskAlertLevel.INFO

            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.LEVERAGE,
                alert_level=alert_level,
                symbol=None,
                current_value=leverage,
                limit_value=self.risk_limits.max_leverage,
                message=f"Leverage limit exceeded: {leverage:.2f}x "
                       f"(limit: {self.risk_limits.max_leverage:.2f}x)"
            )
            violations.append(event)

        return violations

    def check_concentration(
        self,
        positions: Dict[str, float],  # {symbol: market_value}
        portfolio_value: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check concentration risk limits.

        Args:
            positions: Dictionary of {symbol: market_value}
            portfolio_value: Total portfolio value
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if portfolio_value <= 0 or not positions:
            return violations

        # Calculate position weights
        weights = {symbol: abs(value) / portfolio_value for symbol, value in positions.items()}

        # Count concentrated positions (>5% or custom threshold)
        concentrated_threshold = 0.05
        concentrated_positions = [s for s, w in weights.items() if w > concentrated_threshold]

        # Check max concentrated positions
        if len(concentrated_positions) > self.risk_limits.max_concentrated_positions:
            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.CONCENTRATION,
                alert_level=RiskAlertLevel.WARNING,
                symbol=None,
                current_value=float(len(concentrated_positions)),
                limit_value=float(self.risk_limits.max_concentrated_positions),
                message=f"Too many concentrated positions: {len(concentrated_positions)} "
                       f"(limit: {self.risk_limits.max_concentrated_positions})",
                metadata={'concentrated_symbols': concentrated_positions}
            )
            violations.append(event)

        # Check max single bet
        max_position = max(weights.values()) if weights else 0.0
        if max_position > self.risk_limits.max_single_bet:
            max_symbol = max(weights.items(), key=lambda x: x[1])[0]
            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.CONCENTRATION,
                alert_level=RiskAlertLevel.ERROR,
                symbol=max_symbol,
                current_value=max_position,
                limit_value=self.risk_limits.max_single_bet,
                message=f"Single position too large: {max_symbol} at {max_position*100:.2f}% "
                       f"(limit: {self.risk_limits.max_single_bet*100:.2f}%)"
            )
            violations.append(event)

        # Check minimum diversification
        if len(positions) < self.risk_limits.min_positions:
            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.CONCENTRATION,
                alert_level=RiskAlertLevel.INFO,
                symbol=None,
                current_value=float(len(positions)),
                limit_value=float(self.risk_limits.min_positions),
                message=f"Insufficient diversification: {len(positions)} positions "
                       f"(minimum: {self.risk_limits.min_positions})"
            )
            violations.append(event)

        return violations

    # ========================================================================
    # VOLATILITY LIMITS CHECKING
    # ========================================================================

    def check_volatility_limits(
        self,
        portfolio_volatility: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check portfolio volatility limits.

        Args:
            portfolio_volatility: Annualized portfolio volatility
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if portfolio_volatility > self.risk_limits.max_portfolio_volatility:
            utilization = (portfolio_volatility / self.risk_limits.max_portfolio_volatility) * 100

            if utilization >= 120:
                alert_level = RiskAlertLevel.ERROR
            elif utilization >= 100:
                alert_level = RiskAlertLevel.WARNING
            else:
                alert_level = RiskAlertLevel.INFO

            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.VOLATILITY,
                alert_level=alert_level,
                symbol=None,
                current_value=portfolio_volatility,
                limit_value=self.risk_limits.max_portfolio_volatility,
                message=f"Portfolio volatility limit exceeded: {portfolio_volatility*100:.2f}% "
                       f"(limit: {self.risk_limits.max_portfolio_volatility*100:.2f}%)"
            )
            violations.append(event)

        return violations

    # ========================================================================
    # VAR LIMITS CHECKING
    # ========================================================================

    def check_var_limits(
        self,
        portfolio_var: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check portfolio VaR limits.

        Args:
            portfolio_var: Portfolio Value at Risk
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if self.risk_limits.max_portfolio_var_95 is None:
            return violations

        if portfolio_var > self.risk_limits.max_portfolio_var_95:
            utilization = (portfolio_var / self.risk_limits.max_portfolio_var_95) * 100

            if utilization >= 120:
                alert_level = RiskAlertLevel.ERROR
            elif utilization >= 100:
                alert_level = RiskAlertLevel.WARNING
            else:
                alert_level = RiskAlertLevel.INFO

            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.PORTFOLIO_VAR,
                alert_level=alert_level,
                symbol=None,
                current_value=portfolio_var,
                limit_value=self.risk_limits.max_portfolio_var_95,
                message=f"Portfolio VaR limit exceeded: ${portfolio_var:,.2f} "
                       f"(limit: ${self.risk_limits.max_portfolio_var_95:,.2f})"
            )
            violations.append(event)

        return violations

    # ========================================================================
    # DRAWDOWN LIMITS CHECKING
    # ========================================================================

    def check_drawdown(
        self,
        current_drawdown: float,
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check drawdown limits.

        Args:
            current_drawdown: Current drawdown percentage
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        # Check stop trading drawdown (circuit breaker)
        if current_drawdown >= self.risk_limits.stop_trading_drawdown:
            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.DRAWDOWN,
                alert_level=RiskAlertLevel.CRITICAL,
                symbol=None,
                current_value=current_drawdown,
                limit_value=self.risk_limits.stop_trading_drawdown,
                message=f"CIRCUIT BREAKER: Stop trading drawdown reached: {current_drawdown*100:.2f}% "
                       f"(limit: {self.risk_limits.stop_trading_drawdown*100:.2f}%)"
            )
            violations.append(event)

            if self.halt_on_critical:
                self._trading_halted = True
                logger.critical(f"Trading halted due to drawdown: {current_drawdown*100:.2f}%")

        # Check max drawdown warning
        elif current_drawdown >= self.risk_limits.max_drawdown:
            utilization = (current_drawdown / self.risk_limits.max_drawdown) * 100

            if utilization >= 95:  # 95% of max drawdown
                alert_level = RiskAlertLevel.ERROR
            else:
                alert_level = RiskAlertLevel.WARNING

            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.DRAWDOWN,
                alert_level=alert_level,
                symbol=None,
                current_value=current_drawdown,
                limit_value=self.risk_limits.max_drawdown,
                message=f"Maximum drawdown limit exceeded: {current_drawdown*100:.2f}% "
                       f"(limit: {self.risk_limits.max_drawdown*100:.2f}%)"
            )
            violations.append(event)

        return violations

    # ========================================================================
    # CORRELATION LIMITS CHECKING
    # ========================================================================

    def check_correlation(
        self,
        correlation_matrix: np.ndarray,
        symbols: List[str],
        timestamp: datetime
    ) -> List[RiskEvent]:
        """
        Check correlation limits.

        Args:
            correlation_matrix: Asset correlation matrix
            symbols: List of symbols corresponding to matrix rows/cols
            timestamp: Current timestamp

        Returns:
            List of RiskEvent violations
        """
        violations = []

        if correlation_matrix is None or len(correlation_matrix) < 2:
            return violations

        # Calculate average correlation (excluding diagonal)
        n = len(correlation_matrix)
        mask = np.ones((n, n), dtype=bool)
        np.fill_diagonal(mask, False)
        avg_correlation = np.mean(np.abs(correlation_matrix[mask]))

        if avg_correlation > self.risk_limits.max_avg_correlation:
            event = RiskEvent(
                timestamp=timestamp,
                alert_type=RiskAlertType.CORRELATION,
                alert_level=RiskAlertLevel.WARNING,
                symbol=None,
                current_value=avg_correlation,
                limit_value=self.risk_limits.max_avg_correlation,
                message=f"Average correlation too high: {avg_correlation:.3f} "
                       f"(limit: {self.risk_limits.max_avg_correlation:.3f})"
            )
            violations.append(event)

        return violations

    # ========================================================================
    # COMPREHENSIVE MONITORING
    # ========================================================================

    def monitor_risk(
        self,
        risk_metrics: RiskMetrics
    ) -> List[RiskEvent]:
        """
        Comprehensive risk monitoring across all limits.

        Args:
            risk_metrics: Current risk metrics snapshot

        Returns:
            List of all RiskEvent violations
        """
        violations = []
        timestamp = risk_metrics.timestamp

        # Check portfolio limits
        violations.extend(self.check_portfolio_limits(
            portfolio_value=risk_metrics.portfolio_value,
            positions_value=risk_metrics.positions_value,
            cash=risk_metrics.cash,
            timestamp=timestamp
        ))

        # Check volatility limits
        violations.extend(self.check_volatility_limits(
            portfolio_volatility=risk_metrics.portfolio_volatility,
            timestamp=timestamp
        ))

        # Check VaR limits
        violations.extend(self.check_var_limits(
            portfolio_var=risk_metrics.portfolio_var_95,
            timestamp=timestamp
        ))

        # Check drawdown limits
        violations.extend(self.check_drawdown(
            current_drawdown=risk_metrics.current_drawdown,
            timestamp=timestamp
        ))

        # Check correlation limits
        if risk_metrics.correlation_matrix is not None:
            symbols = list(risk_metrics.position_risks.keys())
            violations.extend(self.check_correlation(
                correlation_matrix=risk_metrics.correlation_matrix,
                symbols=symbols,
                timestamp=timestamp
            ))

        # Check position-level limits
        for symbol, position_risk in risk_metrics.position_risks.items():
            violations.extend(self.check_position_limits(
                symbol=symbol,
                position_value=position_risk.market_value,
                portfolio_value=risk_metrics.portfolio_value,
                timestamp=timestamp
            ))

        # Check concentration
        positions = {s: p.market_value for s, p in risk_metrics.position_risks.items()}
        violations.extend(self.check_concentration(
            positions=positions,
            portfolio_value=risk_metrics.portfolio_value,
            timestamp=timestamp
        ))

        # Store violations in history
        self._violation_history.extend(violations)

        # Log violations
        for violation in violations:
            if violation.alert_level == RiskAlertLevel.CRITICAL:
                logger.critical(violation.message)
            elif violation.alert_level == RiskAlertLevel.ERROR:
                logger.error(violation.message)
            elif violation.alert_level == RiskAlertLevel.WARNING:
                logger.warning(violation.message)
            else:
                logger.info(violation.message)

        return violations

    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================

    def is_trading_halted(self) -> bool:
        """Check if trading has been halted due to violations."""
        return self._trading_halted

    def resume_trading(self):
        """Resume trading after manual review."""
        self._trading_halted = False
        logger.info("Trading resumed manually")

    def get_violation_history(self) -> List[RiskEvent]:
        """Get all historical violations."""
        return self._violation_history.copy()

    def get_recent_violations(self, n: int = 10) -> List[RiskEvent]:
        """Get N most recent violations."""
        return self._violation_history[-n:]

    def clear_violation_history(self):
        """Clear violation history."""
        self._violation_history.clear()
        logger.info("Violation history cleared")

    def get_utilization(
        self,
        risk_metrics: RiskMetrics
    ) -> Dict[str, float]:
        """
        Calculate limit utilization percentages.

        Args:
            risk_metrics: Current risk metrics

        Returns:
            Dictionary of {limit_name: utilization_pct}
        """
        utilization = {}

        # Leverage utilization
        if risk_metrics.leverage > 0:
            utilization['leverage'] = (risk_metrics.leverage / self.risk_limits.max_leverage) * 100

        # Volatility utilization
        if risk_metrics.portfolio_volatility > 0:
            utilization['volatility'] = (risk_metrics.portfolio_volatility / self.risk_limits.max_portfolio_volatility) * 100

        # Drawdown utilization
        if risk_metrics.current_drawdown > 0:
            utilization['drawdown'] = (risk_metrics.current_drawdown / self.risk_limits.max_drawdown) * 100

        # VaR utilization
        if self.risk_limits.max_portfolio_var_95 is not None and risk_metrics.portfolio_var_95 > 0:
            utilization['var'] = (risk_metrics.portfolio_var_95 / self.risk_limits.max_portfolio_var_95) * 100

        # Position count utilization
        num_positions = len(risk_metrics.position_risks)
        utilization['diversification'] = (num_positions / self.risk_limits.min_positions) * 100

        return utilization
