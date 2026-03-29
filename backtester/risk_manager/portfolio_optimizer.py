"""
Portfolio Optimizer - Riskfolio-lib & PyPortfolioOpt Integration

Wrapper around riskfolio-lib and PyPortfolioOpt for portfolio optimization with multiple
objectives and risk measures. Provides both libraries as alternatives for flexibility.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import logging

from .models import OptimizationResult, RiskLimits
from .exceptions import OptimizationError, InsufficientDataError
from .utils import validate_returns_data, calculate_covariance_matrix

# Try importing PyPortfolioOpt
try:
    from pypfopt import EfficientFrontier, BlackLittermanModel
    from pypfopt import expected_returns, risk_models
    from pypfopt import objective_functions
    from pypfopt import EfficientSemivariance, EfficientCDaR
    HAS_PYPFOPT = True
except ImportError:
    HAS_PYPFOPT = False

# Try importing riskfolio-lib
try:
    import riskfolio as rp
    HAS_RISKFOLIO = True
except ImportError:
    HAS_RISKFOLIO = False

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """
    Portfolio optimization wrapper using riskfolio-lib.

    Provides multiple optimization methods including mean-variance, risk parity,
    minimum CVaR, maximum Sharpe, and hierarchical risk parity. Handles
    optimization failures gracefully and caches results when appropriate.

    Performance Target: < 500ms for portfolio optimization
    """

    def __init__(
        self,
        lookback_days: int = 252,
        risk_free_rate: float = 0.0,
        allow_short: bool = False
    ):
        """
        Initialize PortfolioOptimizer.

        Args:
            lookback_days: Number of days of historical data to use
            risk_free_rate: Annual risk-free rate
            allow_short: Whether to allow short positions
        """
        self.lookback_days = lookback_days
        self.risk_free_rate = risk_free_rate
        self.allow_short = allow_short

        pass

    # ========================================================================
    # MEAN-VARIANCE OPTIMIZATION
    # ========================================================================

    def optimize_mean_variance(
        self,
        returns: pd.DataFrame,
        risk_limits: Optional[RiskLimits] = None,
        objective: str = 'Sharpe'
    ) -> OptimizationResult:
        """
        Mean-variance optimization using riskfolio-lib.

        Args:
            returns: DataFrame of asset returns (rows=dates, columns=symbols)
            risk_limits: Optional risk constraints
            objective: 'Sharpe', 'MinRisk', or 'MaxRet'

        Returns:
            OptimizationResult with optimal weights

        Raises:
            OptimizationError: If optimization fails
            InsufficientDataError: If not enough data
        """
        if not HAS_RISKFOLIO:
            raise OptimizationError(
                method='mean_variance',
                reason='riskfolio-lib not installed. Install with: pip install riskfolio-lib'
            )

        # Validate data
        is_valid, errors = validate_returns_data(returns)
        if not is_valid:
            raise InsufficientDataError(
                required_periods=self.lookback_days,
                available_periods=len(returns),
                symbol=None
            )

        start_time = time.time()

        try:
            # Build Portfolio object
            port = rp.Portfolio(returns=returns)

            # Calculate mean and covariance
            port.assets_stats(method_mu='hist', method_cov='hist')

            # Set constraints
            if risk_limits:
                # Position limits
                if self.allow_short:
                    port.lowerrets = -risk_limits.max_position_pct
                else:
                    port.lowerrets = 0.0
                port.upperrets = risk_limits.max_position_pct

                # No leverage constraint
                if risk_limits.max_leverage <= 1.0:
                    port.sht = False  # No short selling
                    port.uppersht = 0.0
            else:
                port.lowerrets = 0.0 if not self.allow_short else -1.0
                port.upperrets = 1.0

            # Optimize
            weights = port.optimization(
                model='Classic',          # Mean-variance model
                rm='MV',                  # Standard deviation risk measure
                obj=objective,            # Objective function
                rf=self.risk_free_rate / 252,  # Risk-free rate (daily)
                l=0,                      # Risk aversion (not used for Sharpe)
                hist=True                 # Use historical scenarios
            )

            # Check if optimization succeeded
            if weights is None or weights.sum().sum() == 0:
                raise OptimizationError(
                    method='mean_variance',
                    reason='Optimization returned no valid weights'
                )

            solver_time = (time.time() - start_time) * 1000

            # Convert to OptimizationResult
            result = self._convert_to_result(
                weights=weights,
                portfolio=port,
                method='mean_variance',
                solver_time_ms=solver_time,
                returns=returns
            )

            logger.info(f"Mean-variance optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Mean-variance optimization failed: {e}")
            raise OptimizationError(
                method='mean_variance',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    # ========================================================================
    # RISK PARITY OPTIMIZATION
    # ========================================================================

    def optimize_risk_parity(
        self,
        returns: pd.DataFrame,
        risk_measure: str = 'MV'
    ) -> OptimizationResult:
        """
        Risk parity optimization (equal risk contribution).

        Args:
            returns: DataFrame of asset returns
            risk_measure: Risk measure ('MV'=volatility, 'CVaR', 'CDaR')

        Returns:
            OptimizationResult with risk parity weights
        """
        if not HAS_RISKFOLIO:
            raise OptimizationError(
                method='risk_parity',
                reason='riskfolio-lib not installed'
            )

        # Validate data
        is_valid, errors = validate_returns_data(returns)
        if not is_valid:
            raise InsufficientDataError(
                required_periods=self.lookback_days,
                available_periods=len(returns)
            )

        start_time = time.time()

        try:
            # Build Portfolio object
            port = rp.Portfolio(returns=returns)
            port.assets_stats(method_mu='hist', method_cov='hist')

            # Risk parity optimization
            weights = port.rp_optimization(
                model='Classic',
                rm=risk_measure,
                rf=self.risk_free_rate / 252,
                hist=True
            )

            if weights is None or weights.sum().sum() == 0:
                raise OptimizationError(
                    method='risk_parity',
                    reason='Optimization returned no valid weights'
                )

            solver_time = (time.time() - start_time) * 1000

            result = self._convert_to_result(
                weights=weights,
                portfolio=port,
                method='risk_parity',
                solver_time_ms=solver_time,
                returns=returns
            )

            logger.info(f"Risk parity optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Risk parity optimization failed: {e}")
            raise OptimizationError(
                method='risk_parity',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    # ========================================================================
    # MINIMUM CVaR OPTIMIZATION
    # ========================================================================

    def optimize_min_cvar(
        self,
        returns: pd.DataFrame,
        alpha: float = 0.05,
        risk_limits: Optional[RiskLimits] = None
    ) -> OptimizationResult:
        """
        Minimize Conditional Value at Risk.

        Args:
            returns: DataFrame of asset returns
            alpha: Significance level (0.05 for 95% CVaR)
            risk_limits: Optional risk constraints

        Returns:
            OptimizationResult with minimum CVaR weights
        """
        if not HAS_RISKFOLIO:
            raise OptimizationError(
                method='min_cvar',
                reason='riskfolio-lib not installed'
            )

        # Validate data
        is_valid, errors = validate_returns_data(returns)
        if not is_valid:
            raise InsufficientDataError(
                required_periods=self.lookback_days,
                available_periods=len(returns)
            )

        start_time = time.time()

        try:
            # Build Portfolio object
            port = rp.Portfolio(returns=returns)
            port.assets_stats(method_mu='hist', method_cov='hist', d=alpha)

            # Set constraints
            if risk_limits:
                if self.allow_short:
                    port.lowerrets = -risk_limits.max_position_pct
                else:
                    port.lowerrets = 0.0
                port.upperrets = risk_limits.max_position_pct
            else:
                port.lowerrets = 0.0 if not self.allow_short else -1.0
                port.upperrets = 1.0

            # Minimize CVaR
            weights = port.optimization(
                model='Classic',
                rm='CVaR',
                obj='MinRisk',
                rf=self.risk_free_rate / 252,
                l=0,
                hist=True
            )

            if weights is None or weights.sum().sum() == 0:
                raise OptimizationError(
                    method='min_cvar',
                    reason='Optimization returned no valid weights'
                )

            solver_time = (time.time() - start_time) * 1000

            result = self._convert_to_result(
                weights=weights,
                portfolio=port,
                method='min_cvar',
                solver_time_ms=solver_time,
                returns=returns
            )

            logger.info(f"Min CVaR optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Min CVaR optimization failed: {e}")
            raise OptimizationError(
                method='min_cvar',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    # ========================================================================
    # HIERARCHICAL RISK PARITY
    # ========================================================================

    def optimize_hrp(
        self,
        returns: pd.DataFrame,
        linkage: str = 'single',
        max_k: int = None
    ) -> OptimizationResult:
        """
        Hierarchical Risk Parity optimization.

        Args:
            returns: DataFrame of asset returns
            linkage: Linkage method ('single', 'complete', 'average', 'ward')
            max_k: Maximum number of clusters

        Returns:
            OptimizationResult with HRP weights
        """
        if not HAS_RISKFOLIO:
            raise OptimizationError(
                method='hrp',
                reason='riskfolio-lib not installed'
            )

        # Validate data
        is_valid, errors = validate_returns_data(returns)
        if not is_valid:
            raise InsufficientDataError(
                required_periods=self.lookback_days,
                available_periods=len(returns)
            )

        start_time = time.time()

        try:
            # Build Portfolio object
            port = rp.HCPortfolio(returns=returns)

            # HRP optimization
            weights = port.optimization(
                model='HRP',
                codependence='pearson',
                rm='MV',
                rf=self.risk_free_rate / 252,
                linkage=linkage,
                max_k=max_k,
                leaf_order=True
            )

            if weights is None or weights.sum().sum() == 0:
                raise OptimizationError(
                    method='hrp',
                    reason='Optimization returned no valid weights'
                )

            solver_time = (time.time() - start_time) * 1000

            # Convert weights DataFrame to dict
            # Riskfolio returns weights with symbols as index, not columns
            weights_dict = weights.iloc[:, 0].to_dict()

            # Calculate expected metrics
            expected_return, expected_vol = self._calculate_expected_metrics(returns, weights_dict)

            result = OptimizationResult(
                timestamp=datetime.now(),
                method='hrp',
                weights=weights_dict,
                expected_return=expected_return,
                expected_volatility=expected_vol,
                expected_sharpe=expected_return / expected_vol if expected_vol > 0 else 0.0,
                expected_var_95=0.0,  # HRP doesn't directly calculate this
                expected_cvar_95=0.0,
                max_drawdown_estimate=0.0,
                objective_value=0.0,
                convergence_status='optimal',
                solver_time_ms=solver_time
            )

            logger.info(f"HRP optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"HRP optimization failed: {e}")
            raise OptimizationError(
                method='hrp',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    # ========================================================================
    # PyPortfolioOpt METHODS (Alternative Implementations)
    # ========================================================================

    def optimize_mean_variance_pypfopt(
        self,
        prices: pd.DataFrame,
        risk_limits: Optional[RiskLimits] = None,
        objective: str = 'max_sharpe',
        covariance_method: str = 'ledoit_wolf'
    ) -> OptimizationResult:
        """
        Mean-variance optimization using PyPortfolioOpt (alternative to riskfolio).

        Args:
            prices: DataFrame of asset prices (rows=dates, columns=symbols)
            risk_limits: Optional risk constraints
            objective: 'max_sharpe', 'min_volatility', or 'max_quadratic_utility'
            covariance_method: 'sample', 'ledoit_wolf', 'exp_cov', or 'semicovariance'

        Returns:
            OptimizationResult with optimal weights

        Raises:
            OptimizationError: If optimization fails or PyPortfolioOpt not available
        """
        if not HAS_PYPFOPT:
            raise OptimizationError(
                method='mean_variance_pypfopt',
                reason='PyPortfolioOpt not installed. Install with: pip install PyPortfolioOpt'
            )

        start_time = time.time()

        try:
            # Calculate expected returns
            mu = expected_returns.mean_historical_return(prices, returns_data=False)

            # Calculate covariance matrix
            if covariance_method == 'sample':
                S = risk_models.sample_cov(prices, returns_data=False)
            elif covariance_method == 'ledoit_wolf':
                S = risk_models.CovarianceShrinkage(prices, returns_data=False).ledoit_wolf()
            elif covariance_method == 'exp_cov':
                S = risk_models.exp_cov(prices, returns_data=False)
            elif covariance_method == 'semicovariance':
                S = risk_models.semicovariance(prices, returns_data=False)
            else:
                raise ValueError(f"Invalid covariance_method: {covariance_method}")

            # Create EfficientFrontier object
            ef = EfficientFrontier(mu, S)

            # Add weight bounds if specified
            if risk_limits:
                lower_bound = -risk_limits.max_position_pct if self.allow_short else 0.0
                upper_bound = risk_limits.max_position_pct
                ef.add_constraint(lambda w: w >= lower_bound)
                ef.add_constraint(lambda w: w <= upper_bound)

            # Optimize based on objective
            if objective == 'max_sharpe':
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            elif objective == 'min_volatility':
                ef.min_volatility()
            elif objective == 'max_quadratic_utility':
                ef.max_quadratic_utility(risk_aversion=1.0)
            elif objective == 'efficient_risk':
                ef.efficient_risk(target_volatility=0.15)
            elif objective == 'efficient_return':
                ef.efficient_return(target_return=0.10)
            else:
                raise ValueError(f"Invalid objective: {objective}")

            # Get cleaned weights
            weights = ef.clean_weights()

            # Check if optimization succeeded
            if not weights or sum(weights.values()) == 0:
                raise OptimizationError(
                    method='mean_variance_pypfopt',
                    reason='Optimization returned no valid weights'
                )

            # Get performance
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            expected_return, expected_vol, expected_sharpe = perf

            solver_time = (time.time() - start_time) * 1000

            result = OptimizationResult(
                timestamp=datetime.now(),
                method=f'mean_variance_pypfopt_{objective}',
                weights=weights,
                expected_return=float(expected_return),
                expected_volatility=float(expected_vol),
                expected_sharpe=float(expected_sharpe),
                expected_var_95=float(expected_vol * 1.65),
                expected_cvar_95=float(expected_vol * 2.06),
                max_drawdown_estimate=float(expected_vol * 2.0),
                objective_value=float(expected_sharpe),
                convergence_status='optimal',
                solver_time_ms=solver_time
            )

            logger.info(f"PyPortfolioOpt mean-variance ({objective}) completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"PyPortfolioOpt mean-variance optimization failed: {e}")
            raise OptimizationError(
                method='mean_variance_pypfopt',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    def optimize_efficient_semivariance(
        self,
        prices: pd.DataFrame,
        benchmark: float = 0.0,
        risk_limits: Optional[RiskLimits] = None
    ) -> OptimizationResult:
        """
        Minimize semivariance (downside risk) using PyPortfolioOpt.

        Semivariance only considers returns below a benchmark, making it
        more suitable for risk-averse investors.

        Args:
            prices: DataFrame of asset prices
            benchmark: Benchmark return (default 0 for MAR)
            risk_limits: Optional risk constraints

        Returns:
            OptimizationResult with minimum semivariance weights
        """
        if not HAS_PYPFOPT:
            raise OptimizationError(
                method='efficient_semivariance',
                reason='PyPortfolioOpt not installed'
            )

        start_time = time.time()

        try:
            # Calculate expected returns
            mu = expected_returns.mean_historical_return(prices, returns_data=False)

            # Calculate returns for semivariance
            returns = prices.pct_change().dropna()

            # Create EfficientSemivariance object
            es = EfficientSemivariance(mu, returns, benchmark=benchmark)

            # Add weight bounds if specified
            if risk_limits:
                lower_bound = -risk_limits.max_position_pct if self.allow_short else 0.0
                upper_bound = risk_limits.max_position_pct
                es.add_constraint(lambda w: w >= lower_bound)
                es.add_constraint(lambda w: w <= upper_bound)

            # Optimize for minimum semivariance
            es.efficient_return(target_return=mu.mean())

            # Get cleaned weights
            weights = es.clean_weights()

            if not weights or sum(weights.values()) == 0:
                raise OptimizationError(
                    method='efficient_semivariance',
                    reason='Optimization returned no valid weights'
                )

            # Calculate performance metrics
            perf = es.portfolio_performance(verbose=False)
            expected_return, semivariance, _ = perf

            solver_time = (time.time() - start_time) * 1000

            # Approximate full volatility from semivariance
            expected_vol = float(np.sqrt(semivariance * 2))  # Rough approximation

            result = OptimizationResult(
                timestamp=datetime.now(),
                method='efficient_semivariance',
                weights=weights,
                expected_return=float(expected_return),
                expected_volatility=expected_vol,
                expected_sharpe=float(expected_return / expected_vol) if expected_vol > 0 else 0.0,
                expected_var_95=float(expected_vol * 1.65),
                expected_cvar_95=float(expected_vol * 2.06),
                max_drawdown_estimate=float(expected_vol * 2.0),
                objective_value=float(semivariance),
                convergence_status='optimal',
                solver_time_ms=solver_time
            )

            logger.info(f"Efficient semivariance optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Efficient semivariance optimization failed: {e}")
            raise OptimizationError(
                method='efficient_semivariance',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    def optimize_black_litterman(
        self,
        prices: pd.DataFrame,
        market_caps: Dict[str, float],
        views: Dict[str, float],
        view_confidences: Optional[Dict[str, float]] = None,
        risk_limits: Optional[RiskLimits] = None
    ) -> OptimizationResult:
        """
        Black-Litterman model combining market equilibrium with investor views.

        Args:
            prices: DataFrame of asset prices
            market_caps: Market capitalizations {symbol: market_cap}
            views: Investor views {symbol: expected_return}
            view_confidences: Confidence in views {symbol: confidence} (0-1)
            risk_limits: Optional risk constraints

        Returns:
            OptimizationResult with Black-Litterman weights
        """
        if not HAS_PYPFOPT:
            raise OptimizationError(
                method='black_litterman',
                reason='PyPortfolioOpt not installed'
            )

        start_time = time.time()

        try:
            # Calculate covariance matrix
            S = risk_models.CovarianceShrinkage(prices, returns_data=False).ledoit_wolf()

            # Create market caps array (aligned with prices columns)
            market_caps_array = [market_caps.get(col, 1.0) for col in prices.columns]

            # Create Black-Litterman model
            bl = BlackLittermanModel(S, pi=None, market_caps=market_caps_array, risk_aversion=2.5)

            # Add views
            viewdict = {}
            confidences = []
            for symbol, view in views.items():
                if symbol in prices.columns:
                    viewdict[symbol] = view
                    confidence = view_confidences.get(symbol, 0.5) if view_confidences else 0.5
                    confidences.append(confidence)

            if viewdict:
                bl.bl_views(viewdict, omega='idzorek', view_confidences=confidences)

            # Get posterior estimates
            ret_bl = bl.bl_returns()
            S_bl = bl.bl_cov()

            # Create efficient frontier with BL estimates
            ef = EfficientFrontier(ret_bl, S_bl)

            # Add weight bounds if specified
            if risk_limits:
                lower_bound = -risk_limits.max_position_pct if self.allow_short else 0.0
                upper_bound = risk_limits.max_position_pct
                ef.add_constraint(lambda w: w >= lower_bound)
                ef.add_constraint(lambda w: w <= upper_bound)

            # Maximize Sharpe ratio
            ef.max_sharpe(risk_free_rate=self.risk_free_rate)

            # Get cleaned weights
            weights = ef.clean_weights()

            if not weights or sum(weights.values()) == 0:
                raise OptimizationError(
                    method='black_litterman',
                    reason='Optimization returned no valid weights'
                )

            # Get performance
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            expected_return, expected_vol, expected_sharpe = perf

            solver_time = (time.time() - start_time) * 1000

            result = OptimizationResult(
                timestamp=datetime.now(),
                method='black_litterman',
                weights=weights,
                expected_return=float(expected_return),
                expected_volatility=float(expected_vol),
                expected_sharpe=float(expected_sharpe),
                expected_var_95=float(expected_vol * 1.65),
                expected_cvar_95=float(expected_vol * 2.06),
                max_drawdown_estimate=float(expected_vol * 2.0),
                objective_value=float(expected_sharpe),
                convergence_status='optimal',
                solver_time_ms=solver_time
            )

            logger.info(f"Black-Litterman optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Black-Litterman optimization failed: {e}")
            raise OptimizationError(
                method='black_litterman',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    def optimize_efficient_cdar(
        self,
        prices: pd.DataFrame,
        target_cdar: float = 0.05,
        risk_limits: Optional[RiskLimits] = None
    ) -> OptimizationResult:
        """
        Minimize Conditional Drawdown at Risk (CDaR) using PyPortfolioOpt.

        CDaR is the average of the worst drawdowns and is more robust than
        maximum drawdown.

        Args:
            prices: DataFrame of asset prices
            target_cdar: Target CDaR level (e.g., 0.05 for 5%)
            risk_limits: Optional risk constraints

        Returns:
            OptimizationResult with minimum CDaR weights
        """
        if not HAS_PYPFOPT:
            raise OptimizationError(
                method='efficient_cdar',
                reason='PyPortfolioOpt not installed'
            )

        start_time = time.time()

        try:
            # Calculate expected returns
            mu = expected_returns.mean_historical_return(prices, returns_data=False)

            # Calculate returns for CDaR
            returns = prices.pct_change().dropna()

            # Create EfficientCDaR object
            ec = EfficientCDaR(mu, returns, beta=0.95)

            # Add weight bounds if specified
            if risk_limits:
                lower_bound = -risk_limits.max_position_pct if self.allow_short else 0.0
                upper_bound = risk_limits.max_position_pct
                ec.add_constraint(lambda w: w >= lower_bound)
                ec.add_constraint(lambda w: w <= upper_bound)

            # Minimize CDaR
            ec.min_cdar()

            # Get cleaned weights
            weights = ec.clean_weights()

            if not weights or sum(weights.values()) == 0:
                raise OptimizationError(
                    method='efficient_cdar',
                    reason='Optimization returned no valid weights'
                )

            # Calculate performance metrics
            perf = ec.portfolio_performance(verbose=False)
            expected_return, cdar, _ = perf

            solver_time = (time.time() - start_time) * 1000

            # Estimate volatility from CDaR
            expected_vol = float(cdar * 1.5)  # Rough approximation

            result = OptimizationResult(
                timestamp=datetime.now(),
                method='efficient_cdar',
                weights=weights,
                expected_return=float(expected_return),
                expected_volatility=expected_vol,
                expected_sharpe=float(expected_return / expected_vol) if expected_vol > 0 else 0.0,
                expected_var_95=float(expected_vol * 1.65),
                expected_cvar_95=float(cdar),
                max_drawdown_estimate=float(cdar),
                objective_value=float(cdar),
                convergence_status='optimal',
                solver_time_ms=solver_time
            )

            logger.info(f"Efficient CDaR optimization completed in {solver_time:.1f}ms")
            return result

        except Exception as e:
            solver_time = (time.time() - start_time) * 1000
            logger.error(f"Efficient CDaR optimization failed: {e}")
            raise OptimizationError(
                method='efficient_cdar',
                reason=str(e),
                details={'solver_time_ms': solver_time}
            )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _convert_to_result(
        self,
        weights: pd.DataFrame,
        portfolio: any,
        method: str,
        solver_time_ms: float,
        returns: pd.DataFrame
    ) -> OptimizationResult:
        """
        Convert riskfolio-lib weights to OptimizationResult.

        Args:
            weights: Weights DataFrame from riskfolio
            portfolio: Portfolio object from riskfolio
            method: Optimization method name
            solver_time_ms: Solver time in milliseconds
            returns: Original returns DataFrame

        Returns:
            OptimizationResult object
        """
        # Convert weights DataFrame to dict
        # Riskfolio returns weights with symbols as index, not columns
        weights_dict = weights.iloc[:, 0].to_dict()

        # Calculate expected metrics
        expected_return, expected_vol = self._calculate_expected_metrics(returns, weights_dict)

        # Calculate expected Sharpe
        expected_sharpe = (expected_return - self.risk_free_rate) / expected_vol if expected_vol > 0 else 0.0

        # Estimate VaR and CVaR (simplified)
        expected_var = expected_vol * 1.65  # Approximate 95% VaR for normal dist
        expected_cvar = expected_vol * 2.06  # Approximate 95% CVaR

        # Estimate max drawdown (rule of thumb: ~2x volatility)
        max_dd_estimate = expected_vol * 2.0

        return OptimizationResult(
            timestamp=datetime.now(),
            method=method,
            weights=weights_dict,
            expected_return=expected_return,
            expected_volatility=expected_vol,
            expected_sharpe=expected_sharpe,
            expected_var_95=expected_var,
            expected_cvar_95=expected_cvar,
            max_drawdown_estimate=max_dd_estimate,
            objective_value=expected_sharpe,
            convergence_status='optimal',
            solver_time_ms=solver_time_ms
        )

    def _calculate_expected_metrics(
        self,
        returns: pd.DataFrame,
        weights: Dict[str, float]
    ) -> Tuple[float, float]:
        """
        Calculate expected return and volatility from weights.

        Args:
            returns: Historical returns DataFrame
            weights: Portfolio weights

        Returns:
            Tuple of (expected_return, expected_volatility)
        """
        # Align weights with returns columns
        weight_array = np.array([weights.get(col, 0.0) for col in returns.columns])

        # Expected return (annualized)
        mean_returns = returns.mean().values
        expected_return = float(np.dot(weight_array, mean_returns) * 252)

        # Expected volatility (annualized)
        cov_matrix = returns.cov().values
        portfolio_variance = weight_array @ cov_matrix @ weight_array
        expected_vol = float(np.sqrt(portfolio_variance * 252))

        return expected_return, expected_vol

    def calculate_rebalancing_trades(
        self,
        target_weights: Dict[str, float],
        current_positions: Dict[str, float],  # {symbol: market_value}
        portfolio_value: float,
        current_prices: Dict[str, float]
    ) -> List[Tuple[str, float]]:
        """
        Calculate trades needed to reach target weights.

        Args:
            target_weights: Target portfolio weights
            current_positions: Current positions {symbol: market_value}
            portfolio_value: Total portfolio value
            current_prices: Current prices {symbol: price}

        Returns:
            List of (symbol, target_quantity) tuples
        """
        trades = []

        # Calculate current weights
        current_weights = {
            symbol: value / portfolio_value
            for symbol, value in current_positions.items()
        }

        # All symbols (current + target)
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())

        for symbol in all_symbols:
            current_weight = current_weights.get(symbol, 0.0)
            target_weight = target_weights.get(symbol, 0.0)

            # Calculate target position value
            target_value = target_weight * portfolio_value

            # Calculate current quantity
            if symbol in current_prices:
                price = current_prices[symbol]
                target_qty = int(target_value / price)

                # Only add if there's a meaningful difference
                current_qty = int(current_positions.get(symbol, 0.0) / price) if symbol in current_positions else 0

                if abs(target_qty - current_qty) > 0:
                    trades.append((symbol, target_qty))

        return trades

