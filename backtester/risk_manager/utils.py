"""
Risk Manager Utility Functions

Helper functions for risk calculations, data processing, and formatting.
Refactored to use industry-standard libraries: empyrical, PyPortfolioOpt, polars.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
import logging

# Industry-standard libraries
try:
    import empyrical as ep
    HAS_EMPYRICAL = True
except ImportError:
    HAS_EMPYRICAL = False

try:
    from pypfopt import risk_models
    HAS_PYPFOPT = True
except ImportError:
    HAS_PYPFOPT = False

try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False

logger = logging.getLogger(__name__)


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

if HAS_POLARS:
    DataFrameType = Union[pd.DataFrame, pl.DataFrame]
    SeriesType = Union[pd.Series, pl.Series]
else:
    DataFrameType = pd.DataFrame
    SeriesType = pd.Series


# ============================================================================
# RETURN CALCULATIONS
# ============================================================================

def calculate_returns(prices: np.ndarray, method: str = 'simple') -> np.ndarray:
    """
    Calculate returns from price series using empyrical.

    Args:
        prices: Array of prices
        method: 'simple' or 'log' returns

    Returns:
        Array of returns (length = len(prices) - 1)
    """
    if len(prices) < 2:
        return np.array([])

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        logger.warning("empyrical not available, using manual calculation")
        if method == 'simple':
            return np.diff(prices) / prices[:-1]
        elif method == 'log':
            return np.diff(np.log(prices))
        else:
            raise ValueError(f"method must be 'simple' or 'log', got {method}")

    # Use empyrical (much faster and battle-tested)
    if method == 'simple':
        # empyrical expects prices series, returns simple returns
        return ep.simple_returns(pd.Series(prices)).values
    elif method == 'log':
        # empyrical expects prices series, returns log returns
        returns = ep.log_returns(pd.Series(prices))
        return returns.values if isinstance(returns, pd.Series) else returns
    else:
        raise ValueError(f"method must be 'simple' or 'log', got {method}")


def calculate_returns_from_df(
    df: DataFrameType,
    price_col: str = 'close',
    method: str = 'simple'
) -> Union[pd.Series, 'pl.Series']:
    """
    Calculate returns from DataFrame (supports pandas and polars).

    Args:
        df: DataFrame with price data (pandas or polars)
        price_col: Column name for prices
        method: 'simple' or 'log' returns

    Returns:
        Series of returns (same type as input)
    """
    # Handle polars DataFrame
    if HAS_POLARS and isinstance(df, pl.DataFrame):
        if price_col not in df.columns:
            raise ValueError(f"Column '{price_col}' not found in DataFrame")

        # Use polars native operations (5-10x faster than pandas)
        if method == 'simple':
            returns = df.select(pl.col(price_col).pct_change())
        elif method == 'log':
            returns = df.select(pl.col(price_col).log().diff())
        else:
            raise ValueError(f"method must be 'simple' or 'log', got {method}")

        # Drop first null row and return series
        return returns[price_col][1:]

    # Handle pandas DataFrame
    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")

    prices = df[price_col].values
    returns = calculate_returns(prices, method)

    # Create series with proper index (excluding first row)
    return pd.Series(returns, index=df.index[1:])


def calculate_portfolio_returns(
    weights: Dict[str, float],
    asset_returns: Union[pd.DataFrame, 'pl.DataFrame']
) -> Union[pd.Series, 'pl.Series']:
    """
    Calculate portfolio returns given weights and asset returns.

    Args:
        weights: Dictionary of {symbol: weight}
        asset_returns: DataFrame with returns (rows=dates, cols=symbols)

    Returns:
        Series of portfolio returns
    """
    # Handle polars DataFrame
    if HAS_POLARS and isinstance(asset_returns, pl.DataFrame):
        # Convert weights to array aligned with columns
        weight_array = np.array([weights.get(col, 0.0) for col in asset_returns.columns])

        # Calculate weighted returns using polars
        weighted = asset_returns.with_columns([
            (pl.col(col) * weight).alias(f"weighted_{col}")
            for col, weight in zip(asset_returns.columns, weight_array)
        ])

        # Sum weighted returns
        weighted_cols = [f"weighted_{col}" for col in asset_returns.columns]
        portfolio_returns = weighted.select(pl.sum_horizontal(weighted_cols))

        return portfolio_returns.to_series()

    # Handle pandas DataFrame
    weight_array = np.array([weights.get(col, 0.0) for col in asset_returns.columns])
    portfolio_returns = asset_returns.values @ weight_array

    return pd.Series(portfolio_returns, index=asset_returns.index)


# ============================================================================
# COVARIANCE AND CORRELATION
# ============================================================================

def calculate_covariance_matrix(
    returns: Union[pd.DataFrame, 'pl.DataFrame'],
    method: str = 'sample'
) -> np.ndarray:
    """
    Calculate covariance matrix from returns using PyPortfolioOpt.

    Args:
        returns: DataFrame of asset returns
        method: 'sample', 'shrinkage', 'exponential', or 'semicovariance'

    Returns:
        Covariance matrix as numpy array
    """
    # Convert polars to pandas if needed
    if HAS_POLARS and isinstance(returns, pl.DataFrame):
        returns = returns.to_pandas()

    if not HAS_PYPFOPT:
        logger.warning("PyPortfolioOpt not available, using pandas covariance")
        if method == 'sample':
            return returns.cov().values
        elif method == 'exponential':
            return returns.ewm(span=60).cov().iloc[-len(returns.columns):].values
        else:
            return returns.cov().values

    # Use PyPortfolioOpt (more robust than custom implementations)
    if method == 'sample':
        # Basic sample covariance
        return risk_models.sample_cov(returns, returns_data=True)

    elif method == 'shrinkage':
        # Ledoit-Wolf shrinkage (better for small sample sizes)
        return risk_models.CovarianceShrinkage(returns, returns_data=True).ledoit_wolf()

    elif method == 'exponential':
        # Exponentially weighted covariance (more weight to recent data)
        return risk_models.exp_cov(returns, returns_data=True, span=60)

    elif method == 'semicovariance':
        # Semi-covariance (only considers downside correlation)
        return risk_models.semicovariance(returns, returns_data=True)

    else:
        raise ValueError(
            f"method must be 'sample', 'shrinkage', 'exponential', or 'semicovariance', got {method}"
        )


def calculate_correlation_matrix(
    returns: Union[pd.DataFrame, 'pl.DataFrame']
) -> np.ndarray:
    """
    Calculate correlation matrix from returns.

    Args:
        returns: DataFrame of asset returns

    Returns:
        Correlation matrix as numpy array
    """
    # Use polars if available (5-10x faster)
    if HAS_POLARS and isinstance(returns, pl.DataFrame):
        # Polars native correlation
        corr_df = returns.corr()
        return corr_df.to_numpy()

    # Use pandas
    return returns.corr().values


# ============================================================================
# VOLATILITY CALCULATIONS (Now using empyrical)
# ============================================================================

def calculate_volatility(returns: np.ndarray, annualization_factor: int = 252) -> float:
    """
    Calculate annualized volatility using empyrical.

    Args:
        returns: Array of returns
        annualization_factor: Number of periods per year (252 for daily, 52 for weekly)

    Returns:
        Annualized volatility
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        return float(np.std(returns, ddof=1) * np.sqrt(annualization_factor))

    # Use empyrical (faster and more reliable)
    return float(ep.annual_volatility(returns, period=annualization_factor))


def calculate_downside_volatility(
    returns: np.ndarray,
    target_return: float = 0.0,
    annualization_factor: int = 252
) -> float:
    """
    Calculate annualized downside volatility using empyrical.

    Args:
        returns: Array of returns
        target_return: Target/minimum acceptable return
        annualization_factor: Number of periods per year

    Returns:
        Annualized downside volatility
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        downside_returns = returns[returns < target_return]
        if len(downside_returns) == 0:
            return 0.0
        return float(np.std(downside_returns, ddof=1) * np.sqrt(annualization_factor))

    # Use empyrical downside_risk (more accurate)
    # Note: empyrical's downside_risk is already annualized
    return float(ep.downside_risk(returns, required_return=target_return, period=annualization_factor))


def calculate_rolling_volatility(
    returns: Union[pd.Series, np.ndarray],
    window: int,
    annualization_factor: int = 252
) -> np.ndarray:
    """
    Calculate rolling volatility using pandas/polars rolling windows.

    Args:
        returns: Array or Series of returns
        window: Rolling window size
        annualization_factor: Number of periods per year

    Returns:
        Array of rolling volatilities
    """
    if isinstance(returns, np.ndarray):
        returns = pd.Series(returns)

    if len(returns) < window:
        return np.array([])

    # Use pandas rolling (optimized in C)
    rolling_std = returns.rolling(window=window).std()
    rolling_vol = rolling_std * np.sqrt(annualization_factor)

    # Remove NaN values from the beginning
    return rolling_vol.dropna().values


# ============================================================================
# DRAWDOWN CALCULATIONS
# ============================================================================

def calculate_drawdowns(equity_curve: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate drawdown series and running maximum.

    Note: This is kept as-is since it's simple and efficient.

    Args:
        equity_curve: Array of portfolio values over time

    Returns:
        Tuple of (drawdowns, running_max)
        - drawdowns: Array of drawdown percentages at each point
        - running_max: Array of running maximum values
    """
    if len(equity_curve) == 0:
        return np.array([]), np.array([])

    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max

    return drawdowns, running_max


def calculate_max_drawdown(equity_curve: np.ndarray) -> float:
    """
    Calculate maximum drawdown using empyrical.

    Args:
        equity_curve: Array of portfolio values over time

    Returns:
        Maximum drawdown as positive decimal (e.g., 0.15 for 15% DD)
    """
    if len(equity_curve) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        drawdowns, _ = calculate_drawdowns(equity_curve)
        return float(abs(np.min(drawdowns)))

    # Use empyrical (handles edge cases better)
    # Convert equity curve to returns first
    returns = np.diff(equity_curve) / equity_curve[:-1]
    max_dd = ep.max_drawdown(returns)

    return float(abs(max_dd))


def calculate_average_drawdown(equity_curve: np.ndarray) -> float:
    """
    Calculate average drawdown.

    Args:
        equity_curve: Array of portfolio values over time

    Returns:
        Average drawdown as positive decimal
    """
    if len(equity_curve) == 0:
        return 0.0

    drawdowns, _ = calculate_drawdowns(equity_curve)
    negative_drawdowns = drawdowns[drawdowns < 0]

    if len(negative_drawdowns) == 0:
        return 0.0

    return float(abs(np.mean(negative_drawdowns)))


# ============================================================================
# RATIO CALCULATIONS (Now using empyrical)
# ============================================================================

def calculate_sharpe_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.0,
    annualization_factor: int = 252
) -> float:
    """
    Calculate Sharpe ratio using empyrical.

    Args:
        returns: Array of returns
        risk_free_rate: Risk-free rate (annualized)
        annualization_factor: Number of periods per year

    Returns:
        Sharpe ratio
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        excess_returns = returns - (risk_free_rate / annualization_factor)
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)
        if std_excess == 0:
            return 0.0
        return float((mean_excess / std_excess) * np.sqrt(annualization_factor))

    # Use empyrical (industry standard)
    return float(ep.sharpe_ratio(returns, risk_free=risk_free_rate, period=annualization_factor))


def calculate_sortino_ratio(
    returns: np.ndarray,
    target_return: float = 0.0,
    risk_free_rate: float = 0.0,
    annualization_factor: int = 252
) -> float:
    """
    Calculate Sortino ratio using empyrical.

    Args:
        returns: Array of returns
        target_return: Target/minimum acceptable return
        risk_free_rate: Risk-free rate (annualized)
        annualization_factor: Number of periods per year

    Returns:
        Sortino ratio
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        excess_returns = returns - (risk_free_rate / annualization_factor)
        mean_excess = np.mean(excess_returns)
        downside_vol = calculate_downside_volatility(returns, target_return, annualization_factor)
        if downside_vol == 0:
            return 0.0
        return float((mean_excess * annualization_factor) / downside_vol)

    # Use empyrical (more accurate)
    return float(
        ep.sortino_ratio(
            returns,
            required_return=target_return,
            period=annualization_factor
        )
    )


def calculate_calmar_ratio(
    returns: np.ndarray,
    equity_curve: Optional[np.ndarray] = None,
    annualization_factor: int = 252
) -> float:
    """
    Calculate Calmar ratio using empyrical.

    Args:
        returns: Array of returns
        equity_curve: Array of portfolio values (optional, will compute from returns if not provided)
        annualization_factor: Number of periods per year

    Returns:
        Calmar ratio
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        annualized_return = np.mean(returns) * annualization_factor
        if equity_curve is not None:
            max_dd = calculate_max_drawdown(equity_curve)
        else:
            # Compute equity curve from returns
            equity = np.cumprod(1 + returns)
            max_dd = calculate_max_drawdown(equity)

        if max_dd == 0:
            return 0.0
        return float(annualized_return / max_dd)

    # Use empyrical (handles edge cases better)
    return float(ep.calmar_ratio(returns, period=annualization_factor))


def annualize_return(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """
    Annualize returns using empyrical.

    Args:
        returns: Array of returns
        periods_per_year: Number of periods per year

    Returns:
        Annualized return
    """
    if len(returns) == 0:
        return 0.0

    if not HAS_EMPYRICAL:
        # Fallback to manual calculation
        total_return = np.prod(1 + returns)
        n_periods = len(returns)
        annualization_factor = periods_per_year / n_periods
        return float((total_return ** annualization_factor) - 1)

    # Use empyrical
    return float(ep.annual_return(returns, period=periods_per_year))


# ============================================================================
# RISK REPORT FORMATTING (Kept as-is - custom logic)
# ============================================================================

def format_risk_report(risk_metrics: Dict, title: str = "Risk Report") -> str:
    """
    Format risk metrics as readable text report.

    Args:
        risk_metrics: Dictionary of risk metrics
        title: Report title

    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 70)
    lines.append(f"{title:^70}")
    lines.append("=" * 70)
    lines.append("")

    # Portfolio State
    lines.append("PORTFOLIO STATE")
    lines.append("-" * 70)
    lines.append(f"  Portfolio Value:     ${risk_metrics.get('portfolio_value', 0):,.2f}")
    lines.append(f"  Cash:                ${risk_metrics.get('cash', 0):,.2f}")
    lines.append(f"  Positions Value:     ${risk_metrics.get('positions_value', 0):,.2f}")
    lines.append(f"  Leverage:            {risk_metrics.get('leverage', 0):.2f}x")
    lines.append("")

    # Risk Metrics
    lines.append("RISK METRICS")
    lines.append("-" * 70)
    lines.append(f"  Volatility:          {risk_metrics.get('portfolio_volatility', 0)*100:.2f}%")
    lines.append(f"  VaR (95%):           ${risk_metrics.get('portfolio_var_95', 0):,.2f}")
    lines.append(f"  CVaR (95%):          ${risk_metrics.get('portfolio_cvar_95', 0):,.2f}")
    lines.append(f"  Current Drawdown:    {risk_metrics.get('current_drawdown', 0)*100:.2f}%")
    lines.append(f"  Max Drawdown:        {risk_metrics.get('max_drawdown', 0)*100:.2f}%")
    lines.append("")

    # Performance Metrics
    lines.append("PERFORMANCE METRICS")
    lines.append("-" * 70)
    lines.append(f"  Sharpe Ratio:        {risk_metrics.get('sharpe_ratio', 0):.3f}")
    lines.append(f"  Sortino Ratio:       {risk_metrics.get('sortino_ratio', 0):.3f}")
    lines.append(f"  Calmar Ratio:        {risk_metrics.get('calmar_ratio', 0):.3f}")
    lines.append("")

    # Violations
    violations = risk_metrics.get('violations', [])
    if violations:
        lines.append("RISK VIOLATIONS")
        lines.append("-" * 70)
        for v in violations:
            lines.append(f"  [{v.get('alert_level', 'UNKNOWN')}] {v.get('message', '')}")
        lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


# ============================================================================
# DATA VALIDATION (Kept as-is - custom validation logic)
# ============================================================================

def validate_returns_data(
    returns: Union[pd.DataFrame, 'pl.DataFrame']
) -> Tuple[bool, List[str]]:
    """
    Validate returns DataFrame for risk calculations.

    Args:
        returns: DataFrame of asset returns (pandas or polars)

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Convert polars to pandas for validation
    if HAS_POLARS and isinstance(returns, pl.DataFrame):
        returns_pd = returns.to_pandas()
    else:
        returns_pd = returns

    if returns_pd.empty:
        errors.append("Returns DataFrame is empty")
        return False, errors

    if returns_pd.shape[0] < 2:
        errors.append(f"Insufficient data: need at least 2 rows, have {returns_pd.shape[0]}")

    # Check for NaN values
    if returns_pd.isna().any().any():
        nan_cols = returns_pd.columns[returns_pd.isna().any()].tolist()
        errors.append(f"NaN values found in columns: {nan_cols}")

    # Check for infinite values
    if np.isinf(returns_pd.values).any():
        errors.append("Infinite values found in returns data")

    # Check for extreme returns (>100% in a day is suspicious)
    extreme_returns = (returns_pd.abs() > 1.0).any()
    if extreme_returns.any():
        extreme_cols = returns_pd.columns[extreme_returns].tolist()
        logger.warning(f"Extreme returns (>100%) found in columns: {extreme_cols}")

    return len(errors) == 0, errors


def validate_weights(weights: Dict[str, float], tolerance: float = 1e-6) -> Tuple[bool, List[str]]:
    """
    Validate portfolio weights.

    Args:
        weights: Dictionary of {symbol: weight}
        tolerance: Tolerance for weight sum validation

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    if not weights:
        errors.append("Weights dictionary is empty")
        return False, errors

    # Check weight sum
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > tolerance:
        errors.append(f"Weights sum to {weight_sum:.6f}, expected 1.0")

    # Check for negative weights (unless shorting is allowed)
    negative_weights = {s: w for s, w in weights.items() if w < 0}
    if negative_weights:
        logger.warning(f"Negative weights found (shorting): {negative_weights}")

    # Check for NaN or inf
    invalid_weights = {s: w for s, w in weights.items() if np.isnan(w) or np.isinf(w)}
    if invalid_weights:
        errors.append(f"Invalid weights (NaN/inf): {invalid_weights}")

    return len(errors) == 0, errors


# ============================================================================
# LIBRARY STATUS CHECK
# ============================================================================

def get_library_status() -> Dict[str, bool]:
    """
    Check which optional libraries are available.

    Returns:
        Dictionary of library availability
    """
    return {
        'empyrical': HAS_EMPYRICAL,
        'pypfopt': HAS_PYPFOPT,
        'polars': HAS_POLARS,
    }


def log_library_status():
    """Log which libraries are available."""
    status = get_library_status()
    logger.info("Library Status:")
    logger.info(f"  empyrical: {'✓' if status['empyrical'] else '✗ (using fallback)'}")
    logger.info(f"  PyPortfolioOpt: {'✓' if status['pypfopt'] else '✗ (using fallback)'}")
    logger.info(f"  polars: {'✓' if status['polars'] else '✗ (pandas only)'}")
