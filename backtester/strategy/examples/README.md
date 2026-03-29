# Strategy Examples

This directory contains example strategies that demonstrate various features of the backtesting framework.

## Available Strategies

### 1. BuyAndHold
**File:** `buy_and_hold.py`

Simple buy-and-hold strategy that purchases securities at the start and holds them throughout the backtest period.

**Test:** `test_buy_and_hold.py`

```bash
python backtester/strategy/examples/test_buy_and_hold.py
```

### 2. MovingAverageCrossover
**File:** `ma_crossover.py`

Classic moving average crossover strategy that generates signals based on fast and slow moving average crossovers.

### 3. LimitOrderStopLossStrategy
**File:** `limit_order_stoploss_strategy.py`

Demonstration strategy for testing advanced order types and exit functionality:
- **Limit Orders**: Place orders that execute when price reaches a specific level
- **Stop-Loss Exits**: Automatic position exit when price drops to stop-loss level
- **Target Exits**: Automatic position exit when price reaches profit target
- **Market Orders with Exits**: Immediate execution with automatic stop-loss and target tracking

**Test:** `test_limit_order_stoploss.py`

```bash
python backtester/strategy/examples/test_limit_order_stoploss.py
```

**Features Demonstrated:**
- ✅ Limit order queuing and execution
- ✅ Conservative fill simulation (fills at limit price, not better)
- ✅ Stop-loss automatic exits using actual stop price
- ✅ Target automatic exits using actual target price
- ✅ Gap handling (fills at open if gap through limit/stop/target)
- ✅ Market orders with position-level exits

## Running Tests

Each strategy has an accompanying test file that validates its functionality:

```bash
# Test buy and hold strategy
python backtester/strategy/examples/test_buy_and_hold.py

# Test limit order and stop-loss functionality
python backtester/strategy/examples/test_limit_order_stoploss.py
```

Alternatively, run as modules:

```bash
python -m backtester.strategy.examples.test_buy_and_hold
python -m backtester.strategy.examples.test_limit_order_stoploss
```

## Test Output

The test scripts provide comprehensive validation including:
- ✅ Strategy initialization
- ✅ Backtest execution
- ✅ Signal generation
- ✅ Order placement and execution
- ✅ Transaction recording
- ✅ Position tracking
- ✅ Performance metrics
- ✅ Equity curve tracking

Example output:
```
================================================================================
  TEST 1: Strategy Initialization
================================================================================
[OK] Strategy created with defaults: LimitOrderStopLoss
✅ PASSED: Strategy Initialization
```

## Creating Your Own Strategy

To create a new strategy:

1. **Inherit from `Strategy` base class:**
   ```python
   from backtester.strategy.base_strategy import Strategy

   class MyStrategy(Strategy):
       def init(self, context):
           # Initialize your strategy
           pass

       def on_bar(self, context):
           # Generate signals
           return []
   ```

2. **Generate signals with order details:**
   ```python
   from backtester.strategy.signal import Signal, SignalDirection

   signal = Signal(
       symbol='SBIN',
       direction=SignalDirection.BUY,
       timestamp=context.current_time,
       strength=1.0,
       confidence=1.0,
       order_type='LIMIT',      # 'MARKET', 'LIMIT', 'SL', 'SL-M'
       limit_price=500.0,       # Required for LIMIT orders
       stop_loss=475.0,         # Optional: position stop-loss
       target_price=550.0       # Optional: position target
   )
   ```

3. **Test your strategy:**
   ```python
   config = BacktestConfig(initial_capital=100000)
   orchestrator = BacktestOrchestrator(
       strategies=[MyStrategy()],
       config=config
   )
   results = orchestrator.run(
       symbols=['SBIN'],
       start_date='2024-01-01',
       end_date='2024-12-31',
       interval=Interval.DAY
   )
   ```

## Order Types

The framework supports multiple order types:

### Market Orders
Execute immediately at current price:
```python
order_type='MARKET'
```

### Limit Orders
Execute when price reaches limit:
```python
order_type='LIMIT',
limit_price=500.0  # Buy only if price <= 500
```

### Stop-Loss Orders (SL)
Trigger at stop price, execute at limit:
```python
order_type='SL',
stop_price=500.0,   # Trigger when price hits 500
limit_price=505.0   # Execute at 505
```

### Stop-Loss Market Orders (SL-M)
Trigger at stop price, execute at market:
```python
order_type='SL-M',
stop_price=500.0    # Trigger and execute at ~500
```

## Exit Strategies

### Position-Level Exits
Set stop-loss and target on entry order:
```python
Signal(
    ...,
    stop_loss=475.0,     # Auto-exit if price <= 475
    target_price=550.0   # Auto-exit if price >= 550
)
```

**Note:** Automatic exits only support LONG positions currently. Short position exits require inverse logic.

### Manual Exits
Close position with CLOSE signal:
```python
Signal(
    symbol='SBIN',
    direction=SignalDirection.CLOSE,
    ...
)
```

## Conservative Fill Simulation

The framework uses conservative fill logic to prevent over-optimistic backtest results:

- **Limit Orders**: Fill at limit price (not better, even if available)
- **Stop-Loss**: Fill at stop price (or worse on gap downs)
- **Targets**: Fill at target price (or better on gap ups, conservatively at open)
- **No Intrabar Optimization**: Uses OHLC data only

This ensures backtest results are realistic and don't benefit from unrealistic "perfect" fills.

## Need Help?

- Check the example strategies for reference implementations
- Run the test scripts to see expected behavior
- Review the inline documentation in each strategy file
