# Risk Management Module

A comprehensive risk management framework for the Zerodha backtesting engine. Provides pre-trade risk assessment, portfolio optimization, real-time monitoring, and post-trade analytics.

## Features

- **Pre-Trade Risk Assessment**: Evaluate signals before execution
- **Dynamic Position Sizing**: Multiple strategies (Kelly, risk-based, volatility-targeting, risk parity)
- **Portfolio Optimization**: Mean-variance, risk parity, minimum CVaR, HRP using riskfolio-lib
- **Real-Time Monitoring**: Continuous risk limit enforcement
- **Risk Metrics**: VaR, CVaR, volatility, drawdown, Sharpe/Sortino/Calmar ratios
- **Flexible Risk Frameworks**: VaR/CVaR, drawdown-based, risk parity, volatility targeting, Kelly criterion

## Installation

The risk manager requires riskfolio-lib for portfolio optimization:

```bash
pip install riskfolio-lib
```

## Module Structure

```
risk_manager/
├── __init__.py                  # Public API exports
├── models.py                    # Core data structures
├── exceptions.py                # Custom exceptions
├── utils.py                     # Helper utilities
├── risk_calculator.py           # Risk metrics calculation
├── position_sizer.py            # Position sizing strategies
├── portfolio_optimizer.py       # Portfolio optimization (riskfolio-lib)
├── risk_monitor.py              # Real-time monitoring & limits
└── README.md                    # This file
```

## Quick Start

### 1. Define Risk Limits

```python
from backtester.risk_manager import RiskLimits

# Conservative risk profile
risk_limits = RiskLimits(
    max_position_pct=0.10,          # Max 10% per position
    max_sector_pct=0.30,            # Max 30% per sector
    max_leverage=1.0,               # No leverage
    max_drawdown=0.15,              # Max 15% drawdown
    stop_trading_drawdown=0.12,     # Stop at 12% DD
    max_portfolio_volatility=0.20,  # Max 20% volatility
    min_positions=5                 # Minimum 5 positions
)
```

### 2. Position Sizing

```python
from backtester.risk_manager import PositionSizer

sizer = PositionSizer(risk_limits)

# Risk-based sizing
quantity = sizer.calculate_position_size(
    symbol='SBIN',
    current_price=500.0,
    portfolio_value=100000.0,
    available_cash=50000.0,
    method='risk_based',
    stop_distance=20.0,    # ₹20 stop loss
    risk_percent=0.01      # Risk 1% per trade
)

# Kelly criterion sizing
quantity = sizer.calculate_position_size(
    symbol='SBIN',
    current_price=500.0,
    portfolio_value=100000.0,
    available_cash=50000.0,
    method='kelly',
    win_rate=0.55,
    avg_win=0.08,
    avg_loss=0.04,
    kelly_fraction=0.5     # Half Kelly for safety
)

# Volatility targeting
quantity = sizer.calculate_position_size(
    symbol='SBIN',
    current_price=500.0,
    portfolio_value=100000.0,
    available_cash=50000.0,
    method='volatility_target',
    asset_volatility=0.25,  # 25% annualized vol
    target_volatility=0.15  # Target 15% contribution
)
```

### 3. Risk Calculation

```python
from backtester.risk_manager.risk_calculator import RiskCalculator
import pandas as pd

calculator = RiskCalculator(
    lookback_periods=252,
    confidence_level=0.95,
    annualization_factor=252
)

# Calculate portfolio VaR
positions = {'SBIN': 50000, 'INFY': 30000, 'TCS': 20000}
returns_df = pd.DataFrame(...)  # Historical returns

portfolio_var = calculator.calculate_portfolio_var(
    positions=positions,
    returns=returns_df
)

# Calculate portfolio volatility
portfolio_vol = calculator.calculate_portfolio_volatility(
    positions=positions,
    returns=returns_df,
    use_covariance=True
)

# Comprehensive risk metrics
risk_metrics = calculator.calculate_comprehensive_risk_metrics(
    positions=positions,
    returns=returns_df,
    equity_curve=equity_curve_array,
    portfolio_returns=portfolio_returns_array
)
```

### 4. Portfolio Optimization

```python
from backtester.risk_manager.portfolio_optimizer import PortfolioOptimizer

optimizer = PortfolioOptimizer(lookback_days=252)

# Mean-variance optimization (max Sharpe)
result = optimizer.optimize_max_sharpe(
    returns=returns_df,
    risk_limits=risk_limits
)

print(f"Optimal weights: {result.weights}")
print(f"Expected Sharpe: {result.expected_sharpe:.3f}")
print(f"Expected volatility: {result.expected_volatility*100:.2f}%")

# Risk parity optimization
result = optimizer.optimize_risk_parity(
    returns=returns_df,
    risk_measure='MV'  # or 'CVaR', 'CDaR'
)

# Minimum CVaR optimization
result = optimizer.optimize_min_cvar(
    returns=returns_df,
    alpha=0.05,  # 95% CVaR
    risk_limits=risk_limits
)

# Hierarchical Risk Parity
result = optimizer.optimize_hrp(
    returns=returns_df,
    linkage='ward'
)
```

### 5. Risk Monitoring

```python
from backtester.risk_manager.risk_monitor import RiskMonitor
from backtester.risk_manager import RiskMetrics

monitor = RiskMonitor(
    risk_limits=risk_limits,
    halt_on_critical=True
)

# Monitor current risk metrics
violations = monitor.monitor_risk(risk_metrics)

for violation in violations:
    print(f"[{violation.alert_level.name}] {violation.message}")

# Check if trading halted
if monitor.is_trading_halted():
    print("Trading halted due to risk limits!")

# Get limit utilization
utilization = monitor.get_utilization(risk_metrics)
print(f"Risk limit utilization: {utilization}")
```

## Risk Profiles

The module provides pre-configured risk profiles:

### Conservative

```python
conservative = RiskLimits.conservative()
# - Max 5% per position
# - Max 20% per sector
# - No leverage
# - Max 10% drawdown
# - Max 15% volatility
# - Minimum 10 positions
```

### Aggressive

```python
aggressive = RiskLimits.aggressive()
# - Max 20% per position
# - Max 50% per sector
# - 2x leverage allowed
# - Max 30% drawdown
# - Max 40% volatility
# - Minimum 3 positions
```

## Position Sizing Methods

The PositionSizer supports multiple sizing strategies:

| Method | Description | Parameters |
|--------|-------------|------------|
| `fixed_pct` | Fixed percentage of portfolio | `percent` |
| `risk_based` | Based on stop loss distance | `stop_distance`, `risk_percent` |
| `atr_based` | Based on Average True Range | `atr`, `atr_multiplier` |
| `volatility_target` | Target volatility contribution | `asset_volatility`, `target_volatility` |
| `kelly` | Kelly criterion | `win_rate`, `avg_win`, `avg_loss` |
| `risk_parity` | Equal risk contribution | `asset_volatility`, `num_positions` |
| `optimal` | From portfolio optimization | `optimization_result` |

## Portfolio Optimization Methods

The PortfolioOptimizer supports multiple optimization objectives:

| Method | Description | Risk Measure |
|--------|-------------|--------------|
| `optimize_max_sharpe` | Maximize Sharpe ratio | Standard deviation |
| `optimize_mean_variance` | Classic mean-variance | Standard deviation |
| `optimize_risk_parity` | Equal risk contribution | Volatility, CVaR, CDaR |
| `optimize_min_cvar` | Minimize tail risk | CVaR |
| `optimize_hrp` | Hierarchical clustering | HRP algorithm |

## Risk Metrics Calculated

### Portfolio Level
- **Volatility**: Annualized portfolio volatility
- **VaR**: Value at Risk (95%, 99%)
- **CVaR**: Conditional VaR / Expected Shortfall
- **Drawdown**: Current, maximum, average, CDaR
- **Sharpe Ratio**: Risk-adjusted return
- **Sortino Ratio**: Downside risk-adjusted return
- **Calmar Ratio**: Return / max drawdown

### Position Level
- **Position VaR**: Individual position risk
- **Marginal VaR**: Marginal contribution to portfolio VaR
- **Component VaR**: Total contribution to portfolio VaR
- **Beta**: Correlation with portfolio
- **Risk Contribution**: Percentage of total risk

## Data Structures

### RiskMetrics (Immutable)
Complete portfolio risk snapshot including volatility, VaR, drawdown, and position-level decomposition.

### RiskLimits (Mutable)
Risk constraint definitions for position limits, leverage, drawdown, volatility, and diversification.

### PositionRisk (Immutable)
Risk metrics for individual positions including VaR, volatility, beta, and risk contribution.

### OptimizationResult (Immutable)
Portfolio optimization output with optimal weights, expected metrics, and rebalancing trades.

### RiskEvent (Immutable)
Risk limit violation or alert with severity level and details.

## Performance Targets

| Operation | Target | Acceptable |
|-----------|--------|------------|
| Signal evaluation | < 1ms | < 5ms |
| Position size calculation | < 5ms | < 10ms |
| Risk metrics update | < 10ms | < 50ms |
| Portfolio optimization | < 100ms | < 500ms |
| Full risk report | < 500ms | < 2s |

## Dependencies

- numpy >= 1.24.0
- pandas >= 2.0.0
- scipy >= 1.10.0
- riskfolio-lib >= 7.0.1 (for portfolio optimization)

## Integration with Backtester

The risk manager integrates seamlessly with:
- **PortfolioManager**: Pre-execution risk checks, post-execution updates
- **StrategyContext**: Risk-aware position sizing methods
- **Signal Module**: Risk evaluation before order generation

See `risk_arch.md` for detailed integration architecture.

## Logging

The module uses Python's logging framework. Configure logging level:

```python
import logging
logging.getLogger('backtester.risk_manager').setLevel(logging.INFO)
```

Log levels:
- **INFO**: Normal operations, utilization warnings
- **WARNING**: Soft limit breaches
- **ERROR**: Hard limit violations
- **CRITICAL**: Circuit breaker triggers

## Testing

Run unit tests:

```bash
python -m pytest backtester/risk_manager/test_risk_manager.py
```

## Future Enhancements

Phase 6+ roadmap:
- Machine Learning risk models
- Regime detection
- Multi-strategy risk budgeting
- Real-time market risk integration
- Stress testing & Monte Carlo simulation
- Factor risk models (Fama-French)
- Liquidity risk modeling

## Support

For issues or questions:
- Check documentation in `risk_arch.md`
- Review code examples in strategy modules
- Refer to inline docstrings
