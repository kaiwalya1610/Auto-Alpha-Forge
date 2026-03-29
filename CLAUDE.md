# CLAUDE.md - AI Assistant Guide for Zerodha Algorithmic Trading Infrastructure

This document provides comprehensive guidance for AI assistants working with this codebase. It covers architecture, conventions, workflows, and best practices.

## Table of Contents
1. [Project Overview](#project-overview)
2. [Codebase Structure](#codebase-structure)
3. [Core Modules](#core-modules)
4. [Development Workflows](#development-workflows)
5. [Design Patterns & Architecture](#design-patterns--architecture)
6. [Coding Conventions](#coding-conventions)
7. [Testing Guidelines](#testing-guidelines)
8. [Common Tasks](#common-tasks)
9. [Important Notes for AI Assistants](#important-notes-for-ai-assistants)

---

## Project Overview

**Purpose**: Production-ready algorithmic trading infrastructure for Zerodha Kite Connect API

**Key Features**:
- Dual authentication system (TOTP automated, OAuth manual)
- Comprehensive backtesting framework with event-driven architecture
- Risk management and position sizing
- Order placement and trade management
- Data scraping utilities
- Real-time streaming support

**Technology Stack**:
- Python 3.7+
- Kite Connect API
- Pandas/Polars for data manipulation
- Requests for HTTP operations
- PyOTP for TOTP generation

---

## Codebase Structure

```
ZerodhaAlgoTradingInfra/
├── auth/                          # Authentication module (MODULAR, REFACTORED)
│   ├── zerodha_login.py          # Main auth class (enctoken/OAuth)
│   ├── session_manager.py        # HTTP session with retry logic
│   ├── token_cache.py            # Token caching and validation
│   ├── enctoken_login.py         # Enctoken authentication
│   ├── oauth_login.py            # OAuth authentication
│   └── totp_helper.py            # TOTP code generation
│
├── library/                       # Trading operations library
│   ├── api_client.py             # Base HTTP client with auth
│   ├── constants.py              # Trading constants (OrderConstants)
│   ├── orders.py                 # Order management (OrderManager)
│   ├── trades.py                 # Trade retrieval (TradeManager)
│   ├── utils.py                  # Helper functions
│   └── validators.py             # Input validation
│
├── backtester/                    # Comprehensive backtesting framework
│   ├── backtest_orchestrator.py  # Main backtesting engine
│   ├── results.py                # Results and analytics
│   │
│   ├── strategy/                 # Strategy framework
│   │   ├── base_strategy.py      # Abstract Strategy class
│   │   ├── signal.py             # Signal definitions
│   │   ├── strategy_context.py   # Read-only context for strategies
│   │   ├── market_data.py        # Market data structures
│   │   ├── position_info.py      # Position information
│   │   ├── portfolio_snapshot.py # Portfolio state
│   │   ├── historical_window.py  # Historical data access
│   │   └── examples/             # Example strategies
│   │
│   ├── portfolio_manager/        # Position & portfolio management
│   │   ├── portfolio_manager.py  # Main portfolio manager
│   │   ├── models.py             # Order, Position, Transaction models
│   │   ├── utils.py              # Commission, slippage calculation
│   │   └── exceptions.py         # Custom exceptions
│   │
│   ├── risk_manager/             # Risk management system
│   │   ├── risk_calculator.py    # Risk metric calculations
│   │   ├── position_sizer.py     # Position sizing (8 methods)
│   │   ├── portfolio_optimizer.py # Portfolio optimization
│   │   ├── risk_monitor.py       # Real-time risk monitoring
│   │   ├── models.py             # Risk models and limits
│   │   └── exceptions.py         # Risk exceptions
│   │
│   ├── data_loader/              # Historical data fetching
│   │   ├── DataOrchestrator.py   # Main data orchestrator
│   │   ├── KiteDataFetcher.py    # Kite API data fetcher
│   │   └── cache/                # Data caching
│   │
│   └── utils/                    # Utility functions
│       └── dataframe_utils.py    # Pandas/Polars conversion
│
├── scripts/                       # Utility scripts
│   ├── scrape_fii_buying.py      # Screener.in scraper
│   └── example_usage.py
│
├── examples/                      # Live trading examples
│   └── streaming/                # Real-time data streaming
│
├── zerodha_login.py              # Backward-compatible auth wrapper
├── putOrder.py                   # Legacy order placement (37KB)
├── requirements.txt              # Python dependencies
├── README.md                     # Project documentation
└── CLAUDE.md                     # This file
```

### Module Organization Pattern

**Standard module structure**:
```
module/
├── __init__.py       # Public API exports with __all__
├── models.py         # Data models, dataclasses, and enums
├── exceptions.py     # Custom exception classes
├── utils.py          # Helper functions
└── main_class.py     # Core functionality
```

---

## Core Modules

### 1. Authentication Module (`auth/`)

**Location**: `auth/`

**Purpose**: Modular authentication supporting two methods

**Key Classes**:
- `ZerodhaLogin` (`zerodha_login.py`): Main authentication interface
  - Methods: `enctoken` (TOTP-based), `oauth` (browser-based)
  - Smart token caching with validation
  - Automatic token refresh on expiry

- `SessionManager` (`session_manager.py`): HTTP session with retry strategy
  - Handles 429, 500, 502, 503, 504 errors
  - Configurable retry logic

- `TokenCache` (`token_cache.py`): JSON-based token persistence
  - Validates tokens before use
  - Checks daily expiry for OAuth tokens

**Design Pattern**: Strategy pattern for authentication methods

**When to Modify**:
- Adding new authentication methods
- Changing token caching strategy
- Updating retry logic

**DO NOT**:
- Hardcode credentials
- Skip token validation
- Bypass the caching mechanism

---

### 2. Trading Library (`library/`)

**Location**: `library/`

**Purpose**: Clean API for order placement and trade retrieval

**Key Classes**:

#### OrderManager (`orders.py`)
Inherits from `APIClient` for shared authentication.

**Methods**:
- `place_order()` - Generic order placement
- `place_market_order()` - Market orders
- `place_limit_order()` - Limit orders
- `place_stoploss_order()` - Stop-loss orders
- `place_stoploss_market_order()` - SL-M orders
- `modify_order()` - Modify existing orders
- `cancel_order()` - Cancel orders

**Example Usage**:
```python
from library.orders import OrderManager

# Auto-authenticates on initialization
order_manager = OrderManager()

# Place a market order
order_id = order_manager.place_market_order(
    tradingsymbol="INFY",
    exchange="NSE",
    transaction_type="BUY",
    quantity=1,
    product="CNC"
)
```

#### TradeManager (`trades.py`)
Retrieves order and trade information.

**Methods**:
- `get_orders()` - Fetch all orders
- `get_order_history()` - Order state transitions
- `get_trades()` - All executed trades
- `get_order_trades()` - Trades for specific order

#### OrderConstants (`constants.py`)
Centralized constants for trading operations.

**Categories**:
- Exchanges: `EXCHANGE_NSE`, `EXCHANGE_BSE`, `EXCHANGE_NFO`, etc.
- Order types: `ORDER_TYPE_MARKET`, `ORDER_TYPE_LIMIT`, `ORDER_TYPE_SL`, etc.
- Products: `PRODUCT_CNC`, `PRODUCT_MIS`, `PRODUCT_NRML`
- Validity: `VALIDITY_DAY`, `VALIDITY_IOC`
- Transaction types: `TRANSACTION_TYPE_BUY`, `TRANSACTION_TYPE_SELL`

**When to Modify**:
- Adding new order types or exchanges
- Changing API endpoints
- Adding validation rules

---

### 3. Backtesting Framework (`backtester/`)

**Location**: `backtester/`

**Purpose**: Comprehensive event-driven backtesting engine

**Architecture**: Event-driven with bar-by-bar processing

#### BacktestOrchestrator (`backtest_orchestrator.py`)

**Main backtesting engine** - Entry point for all backtests.

**Workflow**:
1. Initialize: Data loader, portfolio manager, strategies
2. Load Data: Fetch and align historical data
3. Event Loop: Process each bar chronologically
4. Generate Results: Performance metrics and analytics

**Key Features**:
- Polars DataFrame support (5-10x faster than Pandas)
- Rich progress bar with live P&L display
- Position sizing integration (8 methods)
- Risk management integration
- Stop-loss/target order support
- Limit/stop order simulation
- Short selling support

**Configuration Options**:
```python
config = BacktestConfig(
    initial_capital=100000,
    commission_pct=0.001,
    slippage_pct=0.0005,
    use_polars=True,           # Enable Polars for performance
    show_progress=True,         # Display progress bar
    enable_risk_checks=True,    # Enable risk management
    use_position_sizer=True,    # Enable advanced position sizing
    enable_rebalancing=False,   # Portfolio rebalancing
)
```

#### Strategy Framework (`strategy/`)

**Base Strategy Class** (`base_strategy.py`):
```python
from backtester.strategy import Strategy, Signal

class MyStrategy(Strategy):
    def init(self):
        """Initialize strategy (called once)"""
        self.lookback = 20

    def on_bar(self, context):
        """Called for each bar"""
        # Get current price
        price = context.current_price("INFY")

        # Get historical data
        hist = context.history("INFY", bars=self.lookback)

        # Calculate indicator
        sma = context.simple_moving_average("INFY", period=20)

        # Generate signal
        if price > sma:
            return Signal.buy("INFY", quantity=10)
        elif price < sma:
            return Signal.sell("INFY", quantity=10)

        return Signal.hold()
```

**Signal Class** (`signal.py`):
```python
# Basic signals
Signal.buy(symbol, quantity=10)
Signal.sell(symbol, quantity=10)
Signal.hold()
Signal.close(symbol)  # Close position

# Advanced signals with stop-loss/target
Signal.buy(
    symbol="INFY",
    quantity=10,
    stop_loss=950,      # Stop-loss price
    target=1050,        # Target price
    order_type="LIMIT",
    limit_price=1000
)
```

**StrategyContext** (`strategy_context.py`):
Read-only interface for strategies to access market data and portfolio state.

**Methods**:
- `current_bar(symbol)` - Current OHLCV bar
- `current_price(symbol)` - Current close price
- `history(symbol, bars)` - Historical data
- `history_multi(symbols, bars)` - Multi-symbol history
- `position(symbol)` - Current position info
- `positions()` - All positions
- `cash()` - Available cash
- `portfolio_value()` - Total portfolio value
- `simple_moving_average(symbol, period)` - SMA helper
- `exponential_moving_average(symbol, period)` - EMA helper
- `calculate_position_size(...)` - Position sizing

#### Portfolio Manager (`portfolio_manager/`)

**Models** (`models.py`):
- `Order`: Order lifecycle management
- `Position`: Track open positions with P&L
- `Transaction`: Completed trades
- `EquityPoint`: Portfolio value snapshots

**Enums**:
- `TransactionType`: BUY, SELL
- `OrderType`: MARKET, LIMIT, SL, SL_M
- `OrderStatus`: PENDING, OPEN, FILLED, PARTIAL, CANCELLED, REJECTED

**Features**:
- Real-time P&L calculation
- Commission and slippage simulation
- Short selling support
- Stop-loss and target tracking

#### Risk Manager (`risk_manager/`)

**Components**:
1. **RiskCalculator** (`risk_calculator.py`): Portfolio metrics
   - VaR (Value at Risk), CVaR (Conditional VaR)
   - Sharpe ratio, Sortino ratio
   - Maximum drawdown, drawdown duration
   - Win rate, profit factor

2. **PositionSizer** (`position_sizer.py`): 8 sizing methods
   - `equal`: Equal allocation
   - `risk_based`: Fixed risk per trade
   - `kelly`: Kelly criterion
   - `volatility_target`: Volatility targeting
   - `atr`: ATR-based sizing
   - `fixed_percent`: Fixed percentage
   - `signal_strength`: Signal-based
   - `optimal_f`: Optimal F

3. **PortfolioOptimizer** (`portfolio_optimizer.py`)
   - Mean-variance optimization
   - Risk parity
   - Equal weight

4. **RiskMonitor** (`risk_monitor.py`): Real-time limit enforcement

**Risk Limits** (`models.py`):
```python
# Pre-configured risk profiles
RiskLimits.conservative()  # 2% max position, 5% max drawdown
RiskLimits.moderate()      # 5% max position, 10% max drawdown
RiskLimits.aggressive()    # 10% max position, 20% max drawdown
```

#### Data Loader (`data_loader/`)

**DataOrchestrator** (`DataOrchestrator.py`):
- Main data management interface
- Fetches historical data from Kite API
- Supports multiple timeframes (day, minute intervals)
- Caching support for performance

**Interval Enum**:
- `DAY`, `MINUTE_1`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`, `HOUR`, etc.

---

### 4. Scripts Module (`scripts/`)

**Location**: `scripts/`

**Purpose**: Data collection and processing utilities

#### ScreenerScraper (`scrape_fii_buying.py`)

**Flexible web scraper** for screener.in with three usage patterns:

```python
# Pattern 1: Simple function
from scripts.scrape_fii_buying import scrape_url
df = scrape_url("https://www.screener.in/screens/343087/fii-buying/")

# Pattern 2: Class-based
from scripts.scrape_fii_buying import ScreenerScraper
scraper = ScreenerScraper()
df = scraper.scrape("https://www.screener.in/screens/...")

# Pattern 3: Command line
# python scripts/scrape_fii_buying.py --url "..." --output data.csv
```

---

## Development Workflows

### Authentication Workflow

```
1. Initialize ZerodhaLogin
   ↓
2. Check cache for existing token
   ↓
3. If cached & valid → Use cached token
   ↓
4. If expired/missing → Perform fresh login
   ├─ Enctoken: POST credentials → POST TOTP → Extract enctoken
   └─ OAuth: Generate URL → User login → Exchange request_token
   ↓
5. Save token to cache
   ↓
6. Return authentication headers
```

**Key Files**:
- `auth/zerodha_login.py:40-80` (main login logic)
- `auth/token_cache.py:15-45` (caching)

### Order Placement Workflow

```
1. Create OrderManager (auto-authenticates)
   ↓
2. Call order method (e.g., place_market_order)
   ↓
3. Validate parameters (validators.py)
   ↓
4. Build order data dictionary
   ↓
5. Make HTTP request via APIClient
   ├─ If 403 error → Refresh token → Retry
   ├─ If other error → Raise exception
   └─ If success → Parse response
   ↓
6. Return order_id and response data
```

**Key Files**:
- `library/orders.py:50-150` (order methods)
- `library/validators.py:10-60` (validation)
- `library/api_client.py:30-100` (HTTP client)

### Backtesting Workflow

```
1. Create Strategy instances
   ↓
2. Configure BacktestConfig
   ├─ Capital, commission, slippage
   ├─ Risk management settings
   └─ Position sizing method
   ↓
3. Create BacktestOrchestrator
   ↓
4. Run backtest
   ├─ Load data for all symbols
   ├─ Align timestamps
   ├─ Initialize PortfolioManager
   └─ Event Loop:
       For each bar:
         ├─ Check position exits (stop-loss/targets)
         ├─ Process pending orders (limit/stop)
         ├─ Create StrategyContext
         ├─ Get signals from all strategies
         ├─ Convert signals to orders
         ├─ Apply position sizing
         ├─ Check risk limits
         ├─ Execute orders
         ├─ Update portfolio prices
         └─ Record equity point
   ↓
5. Generate BacktestResults
   ├─ Calculate performance metrics
   ├─ Generate risk analytics
   ├─ Create equity curve
   └─ Compile trade statistics
```

**Key Files**:
- `backtester/backtest_orchestrator.py:100-500` (main engine)
- `backtester/strategy/base_strategy.py:20-60` (strategy interface)
- `backtester/portfolio_manager/portfolio_manager.py:50-300` (portfolio)

---

## Design Patterns & Architecture

### Design Patterns Used

#### 1. Strategy Pattern
**Where**: Authentication methods, position sizing, portfolio optimization

**Example**:
```python
# Different authentication strategies
auth.login(method='enctoken')  # Strategy 1
auth.login(method='oauth')      # Strategy 2

# Different position sizing strategies
position_sizer = PositionSizer(method='kelly')
position_sizer = PositionSizer(method='risk_based')
```

#### 2. Template Method Pattern
**Where**: Strategy base class

**Example**:
```python
class Strategy(ABC):
    def init(self):
        """Override in subclass"""
        pass

    @abstractmethod
    def on_bar(self, context):
        """Must override in subclass"""
        pass
```

#### 3. Factory Pattern
**Where**: Risk limits creation

**Example**:
```python
RiskLimits.conservative()  # Factory method
RiskLimits.moderate()      # Factory method
RiskLimits.aggressive()    # Factory method
```

#### 4. Facade Pattern
**Where**: StrategyContext

**Example**:
```python
# Complex subsystems hidden behind simple interface
context.current_price("INFY")  # Facade
context.history("INFY", bars=20)  # Facade
context.position("INFY")  # Facade
```

#### 5. Observer Pattern
**Where**: Event-driven backtesting

**Callbacks**:
- `on_bar_start`
- `on_bar_end`
- `on_risk_violation`

### Architectural Principles

#### 1. Separation of Concerns
- Authentication separate from trading logic
- Strategy separate from execution
- Data access abstracted through context

#### 2. Immutability & Safety
- StrategyContext is read-only
- Strategies cannot directly modify portfolio
- All changes through signals

#### 3. Performance Optimization
- Polars DataFrame support (5-10x faster)
- Intelligent caching (context-level, instance-level)
- Lazy data loading

#### 4. Extensibility
- Abstract base classes for strategies
- Plugin-like architecture for risk managers
- Multiple position sizing algorithms

#### 5. Error Handling
- Custom exception hierarchies
- Graceful degradation (returns None vs raising)
- Automatic retry logic

---

## Coding Conventions

### Naming Conventions

**Classes**: PascalCase
```python
OrderManager, StrategyContext, BacktestOrchestrator
```

**Functions/Methods**: snake_case
```python
place_order(), current_price(), simple_moving_average()
```

**Constants**: UPPER_SNAKE_CASE
```python
EXCHANGE_NSE, ORDER_TYPE_MARKET, TRANSACTION_TYPE_BUY
```

**Private attributes**: Leading underscore
```python
self._cache, self._portfolio_manager, self._api_client
```

### Import Conventions

**Style**:
- Absolute imports preferred
- `__all__` exports in `__init__.py` for clean public API
- Type hints with `TYPE_CHECKING` to avoid circular imports

**Example**:
```python
# Good
from backtester.strategy import Signal, Strategy
from backtester.portfolio_manager import PortfolioManager

# Avoid
from ..strategy import Signal  # Relative import
```

### Documentation Standards

**Docstring Style**: Google-style

**Example**:
```python
def place_order(self, symbol: str, quantity: int) -> str:
    """Place a market order.

    Args:
        symbol: Trading symbol (e.g., "INFY")
        quantity: Number of shares

    Returns:
        Order ID as string

    Raises:
        OrderError: If order placement fails

    Example:
        >>> order_id = manager.place_order("INFY", 10)
        >>> print(order_id)
        '2301140000001'
    """
```

**Type Hints**: Extensive use throughout

```python
from typing import Optional, List, Dict, Any

def get_trades(self, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
    pass
```

### Error Handling Patterns

#### Custom Exception Hierarchies

```python
# Portfolio exceptions
PortfolioError
├── InsufficientFundsError
├── InvalidOrderError
└── PositionNotFoundError

# Risk exceptions
RiskManagerError
├── RiskLimitViolation
├── OptimizationError
└── InvalidRiskParametersError
```

#### Graceful Degradation

```python
# Return None for missing data instead of raising
def current_price(self, symbol: str) -> Optional[float]:
    if symbol not in self._data:
        return None
    return self._data[symbol]['close']
```

#### Automatic Recovery

```python
# Token refresh on 403 errors
try:
    response = self._request('POST', endpoint, data)
except AuthenticationError:
    self._refresh_token()
    response = self._request('POST', endpoint, data)
```

### Logging Standards

**Module-level loggers**:
```python
import logging
logger = logging.getLogger(__name__)
```

**Log levels**:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Non-critical issues
- `ERROR`: Critical failures

**Example**:
```python
logger.info(f"Placing order: {symbol} x {quantity}")
logger.warning(f"Token expired, refreshing...")
logger.error(f"Order placement failed: {error}")
```

---

## Testing Guidelines

### Test Organization

**Co-located with modules**:
```
backtester/
├── strategy/
│   ├── signal.py
│   └── test_signal.py
└── portfolio_manager/
    ├── portfolio_manager.py
    └── test_portfolio_manager.py
```

### Test Types

1. **Unit Tests**: Individual component testing
   - `test_signal.py`: Signal creation and validation
   - `test_portfolio_manager.py`: Position tracking

2. **Integration Tests**: Component interaction
   - `test_interoperability.py`: Cross-module integration
   - `test_refactoring.py`: Refactoring validation

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest backtester/strategy/test_signal.py

# Run with coverage
pytest --cov=backtester --cov-report=html
```

---

## Common Tasks

### Task 1: Adding a New Strategy

**Steps**:
1. Create new file in `backtester/strategy/examples/`
2. Inherit from `Strategy` base class
3. Implement `init()` and `on_bar()` methods
4. Return `Signal` objects

**Example**:
```python
from backtester.strategy import Strategy, Signal

class RSIStrategy(Strategy):
    def init(self):
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70

    def on_bar(self, context):
        # Calculate RSI (simplified)
        rsi = self._calculate_rsi(context, self.rsi_period)

        if rsi < self.oversold:
            return Signal.buy(self.symbol, quantity=10)
        elif rsi > self.overbought:
            return Signal.sell(self.symbol, quantity=10)

        return Signal.hold()

    def _calculate_rsi(self, context, period):
        hist = context.history(self.symbol, bars=period + 1)
        # RSI calculation logic
        return rsi_value
```

**File Location**: `backtester/strategy/examples/rsi_strategy.py`

### Task 2: Adding New Order Type

**Steps**:
1. Add constant to `library/constants.py`
2. Add validation in `library/validators.py`
3. Add method to `library/orders.py`
4. Update documentation

**Example**:
```python
# 1. Add to constants.py
class OrderConstants:
    ORDER_TYPE_ICEBERG = "ICEBERG"

# 2. Add validator
def validate_iceberg_order(quantity, disclosed_quantity):
    if disclosed_quantity >= quantity:
        raise ValueError("Disclosed quantity must be less than total")

# 3. Add to OrderManager
def place_iceberg_order(self, symbol, quantity, disclosed_quantity, price):
    validate_iceberg_order(quantity, disclosed_quantity)
    return self.place_order(
        symbol=symbol,
        quantity=quantity,
        order_type=OrderConstants.ORDER_TYPE_ICEBERG,
        price=price,
        disclosed_quantity=disclosed_quantity
    )
```

### Task 3: Adding New Position Sizing Method

**Steps**:
1. Add method to `backtester/risk_manager/position_sizer.py`
2. Update enum if necessary
3. Add tests

**Example**:
```python
class PositionSizer:
    def calculate_size(self, method: str, **kwargs) -> int:
        if method == 'custom_momentum':
            return self._custom_momentum(**kwargs)
        # ... existing methods

    def _custom_momentum(self, symbol, base_size, momentum_factor):
        """Custom momentum-based sizing"""
        momentum = self._calculate_momentum(symbol)
        adjusted_size = int(base_size * momentum_factor * momentum)
        return adjusted_size
```

### Task 4: Modifying Authentication

**Steps**:
1. Edit `auth/zerodha_login.py` for main logic
2. Edit specific method files (`enctoken_login.py`, `oauth_login.py`)
3. Update `auth/token_cache.py` if caching changes
4. Test with both auth methods

**Example** (adding new auth method):
```python
# auth/zerodha_login.py
def login(self, method='enctoken', **kwargs):
    if method == 'enctoken':
        return self._enctoken_login(**kwargs)
    elif method == 'oauth':
        return self._oauth_login(**kwargs)
    elif method == 'api_key':  # NEW
        return self._api_key_login(**kwargs)
    else:
        raise ValueError(f"Unknown method: {method}")
```

### Task 5: Running a Backtest

**Steps**:
1. Create strategy instance(s)
2. Configure backtest parameters
3. Create orchestrator
4. Run and analyze results

**Example**:
```python
from backtester import BacktestOrchestrator, BacktestConfig
from backtester.strategy.examples import MACrossoverStrategy

# 1. Create strategy
strategy = MACrossoverStrategy(
    symbols=["INFY", "TCS"],
    short_period=10,
    long_period=20
)

# 2. Configure backtest
config = BacktestConfig(
    initial_capital=100000,
    commission_pct=0.001,
    slippage_pct=0.0005,
    use_polars=True,
    show_progress=True,
    enable_risk_checks=True,
    position_sizing_method='risk_based',
    risk_per_trade=0.02
)

# 3. Create orchestrator
orchestrator = BacktestOrchestrator(
    strategies=[strategy],
    config=config,
    start_date="2023-01-01",
    end_date="2023-12-31"
)

# 4. Run backtest
results = orchestrator.run()

# 5. Analyze results
print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")

# Plot equity curve
results.plot_equity_curve()
```

---

## Important Notes for AI Assistants

### Critical DO's

1. **ALWAYS use absolute imports**
   ```python
   # Good
   from backtester.strategy import Signal

   # Bad
   from ..strategy import Signal
   ```

2. **ALWAYS validate inputs** using `library/validators.py`
   ```python
   from library.validators import validate_order_params
   validate_order_params(symbol, quantity, price)
   ```

3. **ALWAYS use type hints**
   ```python
   def place_order(self, symbol: str, quantity: int) -> str:
       pass
   ```

4. **ALWAYS check for None** when accessing optional data
   ```python
   price = context.current_price(symbol)
   if price is None:
       return Signal.hold()
   ```

5. **ALWAYS use constants** from `library/constants.py`
   ```python
   # Good
   from library.constants import OrderConstants
   order_type = OrderConstants.ORDER_TYPE_MARKET

   # Bad
   order_type = "MARKET"
   ```

6. **ALWAYS document** with Google-style docstrings
   ```python
   def method(self, arg: str) -> int:
       """Brief description.

       Args:
           arg: Description

       Returns:
           Description
       """
   ```

7. **ALWAYS handle authentication errors** with refresh logic
   ```python
   try:
       response = self._api_call()
   except AuthenticationError:
       self._refresh_token()
       response = self._api_call()
   ```

8. **ALWAYS prefer Polars** for backtesting performance
   ```python
   config = BacktestConfig(use_polars=True)
   ```

### Critical DON'Ts

1. **NEVER hardcode credentials**
   ```python
   # Bad
   api_key = "abc123"

   # Good
   api_key = os.getenv("API_KEY")
   ```

2. **NEVER skip validation**
   ```python
   # Bad
   self._execute_order(symbol, quantity)

   # Good
   validate_order_params(symbol, quantity, exchange)
   self._execute_order(symbol, quantity)
   ```

3. **NEVER modify StrategyContext** inside strategies
   ```python
   # Bad - Context is read-only
   context._portfolio_value = 100000

   # Good - Use signals
   return Signal.buy(symbol, quantity=10)
   ```

4. **NEVER bypass the signal system** in backtesting
   ```python
   # Bad - Direct portfolio modification
   portfolio.add_position(symbol, quantity)

   # Good - Use signals
   return Signal.buy(symbol, quantity)
   ```

5. **NEVER use relative imports**
   ```python
   # Bad
   from ..orders import OrderManager

   # Good
   from library.orders import OrderManager
   ```

6. **NEVER ignore exceptions** without logging
   ```python
   # Bad
   try:
       result = risky_operation()
   except Exception:
       pass

   # Good
   try:
       result = risky_operation()
   except Exception as e:
       logger.error(f"Operation failed: {e}")
       raise
   ```

7. **NEVER mix Pandas and Polars** without conversion
   ```python
   # Bad
   polars_df.iloc[0]  # iloc doesn't exist in Polars

   # Good
   from backtester.utils.dataframe_utils import to_pandas
   pandas_df = to_pandas(polars_df)
   pandas_df.iloc[0]
   ```

8. **NEVER create strategies without `init()` and `on_bar()`**
   ```python
   # Bad
   class MyStrategy(Strategy):
       def custom_method(self):
           pass

   # Good
   class MyStrategy(Strategy):
       def init(self):
           self.param = 10

       def on_bar(self, context):
           return Signal.hold()
   ```

### Performance Considerations

1. **Use Polars for large datasets**
   - 5-10x faster than Pandas
   - Better memory efficiency
   - Set `config.use_polars = True`

2. **Cache expensive calculations**
   ```python
   class MyStrategy(Strategy):
       def init(self):
           self._indicator_cache = {}

       def on_bar(self, context):
           if 'sma' not in self._indicator_cache:
               self._indicator_cache['sma'] = context.simple_moving_average(...)
   ```

3. **Use `history_multi()` for multiple symbols**
   ```python
   # Bad - Multiple calls
   infy = context.history("INFY", bars=20)
   tcs = context.history("TCS", bars=20)

   # Good - Single call
   data = context.history_multi(["INFY", "TCS"], bars=20)
   ```

4. **Prefer vectorized operations**
   ```python
   # Bad - Loop
   for bar in history:
       result.append(bar['close'] * 2)

   # Good - Vectorized
   result = history['close'] * 2
   ```

### Security Considerations

1. **Use environment variables** for sensitive data
   ```python
   import os
   from dotenv import load_dotenv

   load_dotenv()
   api_key = os.getenv("API_KEY")
   ```

2. **Never log sensitive data**
   ```python
   # Bad
   logger.info(f"API key: {api_key}")

   # Good
   logger.info("Authentication successful")
   ```

3. **Validate all external inputs**
   ```python
   from library.validators import validate_symbol
   validate_symbol(user_input_symbol)
   ```

### Debugging Tips

1. **Enable detailed logging**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Use progress bars** for long backtests
   ```python
   config = BacktestConfig(show_progress=True)
   ```

3. **Check backtest results** for anomalies
   ```python
   results = orchestrator.run()
   print(results.trade_count)  # Suspiciously low?
   print(results.win_rate)     # Too good to be true?
   print(results.trades)       # Review individual trades
   ```

4. **Validate data quality**
   ```python
   # Check for missing data
   if data is None or len(data) == 0:
       logger.warning(f"No data for {symbol}")
       return Signal.hold()
   ```

### Module-Specific Guidelines

#### When Working with `auth/`

- Always check token validity before use
- Implement proper retry logic for network failures
- Cache tokens appropriately
- Support both TOTP and OAuth methods
- Handle token expiry gracefully

#### When Working with `library/`

- Use OrderConstants for all constants
- Validate all order parameters
- Inherit from APIClient for shared functionality
- Handle API errors with specific exception types
- Retry on 403 (authentication) errors

#### When Working with `backtester/`

- Strategies must be stateless across bars
- Use StrategyContext for all data access
- Never modify portfolio directly
- Always use Signal objects for actions
- Consider performance (use Polars)
- Test with small date ranges first
- Validate results for reasonableness

#### When Working with `scripts/`

- Handle network failures gracefully
- Validate scraped data structure
- Log warnings for missing elements
- Provide clear error messages
- Support command-line and programmatic use

---

## File References

Quick reference for commonly modified files:

| Task | Primary Files | Supporting Files |
|------|---------------|------------------|
| Authentication | `auth/zerodha_login.py` | `auth/token_cache.py`, `auth/session_manager.py` |
| Order Placement | `library/orders.py` | `library/validators.py`, `library/constants.py` |
| New Strategy | `backtester/strategy/examples/` | `backtester/strategy/base_strategy.py` |
| Position Sizing | `backtester/risk_manager/position_sizer.py` | `backtester/risk_manager/models.py` |
| Risk Management | `backtester/risk_manager/risk_monitor.py` | `backtester/risk_manager/risk_calculator.py` |
| Data Loading | `backtester/data_loader/DataOrchestrator.py` | `backtester/data_loader/KiteDataFetcher.py` |
| Backtesting | `backtester/backtest_orchestrator.py` | `backtester/results.py` |

---

## Dependencies

**Core Dependencies** (from `requirements.txt`):
- `kiteconnect>=4.0.0` - Zerodha API client
- `requests>=2.28.0` - HTTP requests
- `pyotp>=2.8.0` - TOTP code generation
- `python-dotenv>=1.0.0` - Environment variables
- `pandas>=2.0.0` - Data manipulation
- `beautifulsoup4>=4.12.0` - Web scraping
- `lxml>=4.9.0` - HTML parsing
- `html5lib>=1.1` - HTML parsing

**Optional Dependencies** (highly recommended):
- `polars` - High-performance DataFrames (5-10x faster)
- `numpy` - Numerical operations
- `rich` - Progress bars and formatting
- `matplotlib` - Plotting equity curves

**Development Dependencies**:
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting

---

## Environment Setup

**Required Environment Variables** (`.env` file):
```env
# API Credentials
API_KEY=your_kite_api_key
API_SECRET=your_kite_api_secret

# User Credentials (for TOTP auth)
USER_ID=your_zerodha_user_id
USER_PASSWORD=your_zerodha_password
TOTP_KEY=your_totp_secret_key

# OAuth Settings (for OAuth auth)
CALLBACK_PORT=8000
```

**Security Notes**:
- Never commit `.env` to version control
- Never commit `access_token.txt` or token cache files
- Regularly rotate API secrets
- Use different credentials for development/production

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     USER / AI ASSISTANT                      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│  Live Trading   │             │   Backtesting   │
│                 │             │                 │
│  ┌───────────┐  │             │  ┌───────────┐  │
│  │  Orders   │  │             │  │ Strategy  │  │
│  │  Manager  │  │             │  │ Framework │  │
│  └─────┬─────┘  │             │  └─────┬─────┘  │
│        │        │             │        │        │
│        ▼        │             │        ▼        │
│  ┌───────────┐  │             │  ┌───────────┐  │
│  │   Trades  │  │             │  │Portfolio  │  │
│  │  Manager  │  │             │  │ Manager   │  │
│  └─────┬─────┘  │             │  └─────┬─────┘  │
│        │        │             │        │        │
└────────┼────────┘             └────────┼────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
              ┌─────────────────┐
              │  Authentication │
              │                 │
              │  ┌───────────┐  │
              │  │  TOTP     │  │
              │  │  OAuth    │  │
              │  └─────┬─────┘  │
              │        │        │
              │  ┌─────▼─────┐  │
              │  │  Token    │  │
              │  │  Cache    │  │
              │  └───────────┘  │
              └─────────────────┘
```

---

## Version History

**Version**: 1.0 (2024)
- Refactored authentication system (modular design)
- Comprehensive backtesting framework
- Risk management integration
- Position sizing algorithms
- Polars support for performance
- Short selling support

**Recent Commits** (as of analysis):
```
74d65c7 - refactor(backtester): streamline imports and enhance context management
ca2df77 - feat(backtester): add comprehensive short selling support
0a45711 - feat(backtester): remove outdated documentation and images
f22fff2 - feat(auth): refactor Zerodha authentication system with modular design
0bda46a - feat(examples): add real-time streaming examples and stop-loss/target exit demo
```

---

## Additional Resources

**Internal Documentation**:
- `README.md` - Project overview and quick start
- `scripts/README.md` - Scripts documentation
- Strategy examples in `backtester/strategy/examples/`
- Backtest examples in `backtester/examples/`

**External Documentation**:
- [Kite Connect Documentation](https://kite.trade/docs/connect/v3/)
- [PyKiteConnect GitHub](https://github.com/zerodha/pykiteconnect)
- [Polars Documentation](https://pola-rs.github.io/polars/)

---

## Contact & Support

This is a personal algorithmic trading infrastructure. For issues or questions:
1. Check existing code examples
2. Review this CLAUDE.md file
3. Examine test files for usage patterns
4. Review recent commit history

---

**Last Updated**: 2024
**Maintained By**: Project owner
**AI Assistant Version**: 1.0
