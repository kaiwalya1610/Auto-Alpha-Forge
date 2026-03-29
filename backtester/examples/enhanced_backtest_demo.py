"""
Enhanced Backtesting Orchestrator - Feature Demonstration

This example demonstrates all the new features of the enhanced backtesting system:
1. Polars integration for 5-10x performance improvement
2. Risk management with pre-order validation
3. Advanced position sizing (7 methods)
4. Rich progress bars with real-time P&L
5. Comprehensive analytics and risk metrics

Author: Zerodha Algo Trading Infrastructure
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime
from backtester.backtest_orchestrator import BacktestOrchestrator, BacktestConfig
from backtester.data_loader import Interval
from backtester.risk_manager import RiskLimits
from backtester.strategy.base_strategy import Strategy
from backtester.strategy.signal import Signal, SignalDirection
from backtester.strategy.examples.limit_order_stoploss_strategy import LimitOrderStopLossStrategy

# Visualization imports (simplified - v2.0.0)
from backtester.visualization import (
    HTMLReportGenerator,
    EquityChart,
    CandlestickChart,
)


# ============================================================================
# EXAMPLE STRATEGY: Simple Moving Average Crossover
# ============================================================================

class EnhancedMACrossover(Strategy):
    """
    Moving Average Crossover strategy with confidence scoring.

    Demonstrates:
    - Signal generation with strength and confidence
    - Using StrategyContext for data access
    - Stop-loss specification for risk-based sizing
    """

    def __init__(self, fast_period: int = 10, slow_period: int = 50):
        super().__init__()
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.name = f"MA_Crossover_{fast_period}_{slow_period}"

    def init(self, context):
        """Initialize strategy - called once before backtesting starts."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Initializing {self.name} with fast={self.fast_period}, "
            f"slow={self.slow_period}"
        )

    def on_bar(self, context):
        """
        Generate trading signals based on MA crossover.

        This demonstrates:
        - Accessing historical data via context
        - Calculating indicators
        - Generating signals with confidence scores
        - Setting stop-loss for risk management
        """
        signals = []

        for symbol in context.symbols:
            # Skip if insufficient data
            if not context.has_data(symbol, self.slow_period + 1):
                continue

            # Get historical data
            history = context.history(symbol, periods=self.slow_period + 1)
            if history is None or len(history) < self.slow_period + 1:
                continue

            # Calculate moving averages using Polars-optimized helper methods
            fast_ma = history.rolling_mean('close', self.fast_period)
            slow_ma = history.rolling_mean('close', self.slow_period)

            # Get current and previous values (last two elements)
            fast_current = fast_ma[-1]
            fast_prev = fast_ma[-2]
            slow_current = slow_ma[-1]
            slow_prev = slow_ma[-2]

            current_price = context.current_price(symbol)

            # Check for crossover
            bullish_cross = fast_prev <= slow_prev and fast_current > slow_current
            bearish_cross = fast_prev >= slow_prev and fast_current < slow_current

            if bullish_cross:
                # Calculate signal strength (how far apart the MAs are)
                separation = abs(fast_current - slow_current) / slow_current
                strength = min(separation * 10, 1.0)  # Scale to 0-1

                # Calculate confidence based on trend strength
                recent_returns = history.data['close'].pct_change().tail(5)
                confidence = min(abs(recent_returns.mean()) * 20, 1.0)

                # Calculate stop loss (2% below entry or slow MA)
                stop_loss = min(current_price * 0.98, slow_current * 0.99)

                # Calculate target price (5% above entry)
                target_price = current_price * 1.05

                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    timestamp=context.current_time,
                    strength=strength,
                    confidence=max(confidence, 0.5),  # Min 50% confidence
                    stop_loss=stop_loss,
                    target_price=target_price,
                    reasoning=f"Bullish MA crossover: Fast={fast_current:.2f}, Slow={slow_current:.2f}"
                ))

                self.logger.info(
                    f"BUY signal: {symbol} @ {current_price:.2f} "
                    f"(strength={strength:.2f}, confidence={confidence:.2f}, "
                    f"stop={stop_loss:.2f}, target={target_price:.2f})"
                )

            elif bearish_cross:
                # Close position on bearish crossover
                if context.has_position(symbol):
                    signals.append(Signal(
                        symbol=symbol,
                        direction=SignalDirection.CLOSE,
                        timestamp=context.current_time,
                        strength=0.8,
                        confidence=0.7,
                        reasoning=f"Bearish MA crossover: Fast={fast_current:.2f}, Slow={slow_current:.2f}"
                    ))

                    self.logger.info(f"CLOSE signal: {symbol} @ {current_price:.2f}")

        return signals


# ============================================================================
# EXAMPLE 1: Basic Enhanced Backtest
# ============================================================================

def example_1_basic_enhanced():
    """
    Basic example using enhanced features with default settings.

    Demonstrates:
    - Polars integration (automatic)
    - Rich progress bar
    - Enhanced results output
    """
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Enhanced Backtest")
    print("="*80 + "\n")

    # Create strategy
    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    # Configure with enhanced features (minimal config)
    config = BacktestConfig(
        initial_capital=100000,
        show_progress=True,  # Beautiful progress bar
    )

    # Run backtest
    orchestrator = BacktestOrchestrator([strategy], config)

    results = orchestrator.run(
        symbols=['SBIN', 'INFY'],  # Keep small for demo
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Display results
    print(results.summary())

    return results


# ============================================================================
# EXAMPLE 2: With Risk Management
# ============================================================================

def example_2_with_risk_management():
    """
    Backtest with comprehensive risk management enabled.

    Demonstrates:
    - Risk limits configuration
    - Pre-order risk validation
    - Risk check modes (block/warn/log)
    - Risk metrics calculation
    - Risk violation tracking
    """
    print("\n" + "="*80)
    print("EXAMPLE 2: With Risk Management")
    print("="*80 + "\n")

    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    # Configure risk limits
    risk_limits = RiskLimits(
        max_position_pct=0.15,  # Max 15% per position
        max_leverage=1.0,  # No leverage
        max_drawdown=0.20,  # 20% max drawdown
        stop_trading_drawdown=0.15,  # Circuit breaker at 15%
        max_concentrated_positions=3,  # Max 3 large positions
        max_avg_correlation=0.70
    )

    # Configure with risk management
    config = BacktestConfig(
        initial_capital=100000,
        show_progress=True,

        # Risk Management
        enable_risk_checks=True,
        risk_limits=risk_limits,
        risk_check_mode='warn',  # Log warnings but execute orders
        risk_calc_frequency=10,  # Calculate risk every 10 bars
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    results = orchestrator.run(
        symbols=['SBIN', 'INFY', 'TCS'],
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Display results with risk metrics
    print(results.summary())

    # Show risk violations
    if results.risk_events:
        print("\n" + "="*80)
        print("RISK VIOLATIONS DETECTED")
        print("="*80)
        for event in results.risk_events[:10]:  # Show first 10
            print(f"[{event.alert_level.name}] {event.message}")

    # Show risk metrics evolution
    if results.risk_metrics_history:
        print("\n" + "="*80)
        print("RISK METRICS EVOLUTION")
        print("="*80)
        print(f"Total snapshots: {len(results.risk_metrics_history)}")

        final = results.final_risk_metrics
        if final:
            print(f"\nFinal Risk Metrics:")
            print(f"  Sharpe Ratio: {final.sharpe_ratio:.3f}")
            print(f"  Sortino Ratio: {final.sortino_ratio:.3f}")
            print(f"  Calmar Ratio: {final.calmar_ratio:.3f}")
            print(f"  Max Drawdown: {final.max_drawdown*100:.2f}%")
            print(f"  Portfolio Volatility: {final.portfolio_volatility*100:.2f}%")
            print(f"  VaR (95%): Rs {final.portfolio_var_95:,.0f}")
            print(f"  CVaR (95%): Rs {final.portfolio_cvar_95:,.0f}")

    return results


# ============================================================================
# EXAMPLE 3: Advanced Position Sizing
# ============================================================================

def example_3_advanced_position_sizing():
    """
    Demonstrates advanced position sizing methods.

    Shows:
    - Kelly criterion sizing
    - Risk-based sizing
    - ATR-based sizing
    - Position sizing analytics
    """
    print("\n" + "="*80)
    print("EXAMPLE 3: Advanced Position Sizing (Kelly Criterion)")
    print("="*80 + "\n")

    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    config = BacktestConfig(
        initial_capital=100000,
        show_progress=True,

        # Advanced Position Sizing
        use_position_sizer=True,
        position_sizing_method='kelly',  # Kelly criterion
        max_position_size=0.20,  # Max 20% per position
        risk_per_trade=0.02,  # 2% risk per trade
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    results = orchestrator.run(
        symbols=['SBIN', 'INFY', 'TCS'],
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    print(results.summary())

    # Show position sizing statistics
    if results.position_sizing_stats:
        print("\n" + "="*80)
        print("POSITION SIZING STATISTICS")
        print("="*80)
        stats = results.position_sizing_stats
        print(f"Method: {stats.get('method', 'N/A')}")
        print(f"Total Decisions: {stats.get('total_decisions', 0)}")
        print(f"Avg Quantity: {stats.get('avg_quantity', 0):.2f}")
        print(f"Median Quantity: {stats.get('median_quantity', 0):.2f}")
        print(f"Avg Signal Strength: {stats.get('avg_signal_strength', 0):.2f}")
        print(f"Avg Signal Confidence: {stats.get('avg_signal_confidence', 0):.2f}")

    return results


# ============================================================================
# EXAMPLE 4: With Event Hooks
# ============================================================================

def example_4_with_event_hooks():
    """
    Demonstrates event hooks for custom logic.

    Shows:
    - on_bar_start hook
    - on_bar_end hook
    - on_risk_violation hook
    - Custom monitoring and logging
    """
    print("\n" + "="*80)
    print("EXAMPLE 4: With Event Hooks")
    print("="*80 + "\n")

    # Track some custom metrics
    custom_metrics = {
        'max_portfolio_value': 0,
        'bars_processed': 0,
        'risk_violations_critical': 0
    }

    def on_bar_start(context, bar_index):
        """Called before processing each bar."""
        if bar_index == 0:
            print(f"Backtest starting at {context.current_time}")

    def on_bar_end(context, bar_index):
        """Called after processing each bar."""
        custom_metrics['bars_processed'] += 1
        portfolio_value = context.portfolio_value()
        if portfolio_value > custom_metrics['max_portfolio_value']:
            custom_metrics['max_portfolio_value'] = portfolio_value

    def on_risk_violation(violations, order, context):
        """Called when risk violation occurs."""
        for v in violations:
            if v.alert_level.value >= 4:  # CRITICAL
                custom_metrics['risk_violations_critical'] += 1
                print(f"\n🚨 CRITICAL RISK VIOLATION: {v.message}")

    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    config = BacktestConfig(
        initial_capital=100000,
        show_progress=True,
        enable_risk_checks=True,
        risk_limits=RiskLimits.conservative(),

        # Event Hooks
        on_bar_start=on_bar_start,
        on_bar_end=on_bar_end,
        on_risk_violation=on_risk_violation,
        log_signals=True  # Log all signals
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    results = orchestrator.run(
        symbols=['SBIN', 'INFY'],
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    print(results.summary())

    # Show custom metrics
    print("\n" + "="*80)
    print("CUSTOM METRICS (from event hooks)")
    print("="*80)
    print(f"Bars Processed: {custom_metrics['bars_processed']}")
    print(f"Max Portfolio Value: Rs {custom_metrics['max_portfolio_value']:,.2f}")
    print(f"Critical Risk Violations: {custom_metrics['risk_violations_critical']}")

    return results


# ============================================================================
# EXAMPLE 5: Complete Feature Showcase
# ============================================================================

def example_5_complete_showcase():
    """
    Complete showcase using all enhanced features together.

    This is the "kitchen sink" example showing everything at once:
    - Polars performance
    - Risk management
    - Advanced position sizing
    - Event hooks
    - Comprehensive analytics
    """
    print("\n" + "="*80)
    print("EXAMPLE 5: Complete Feature Showcase")
    print("="*80 + "\n")

    # Custom risk violation handler
    violation_count = {'total': 0}

    def handle_violations(violations, order, context):
        violation_count['total'] += len(violations)
        for v in violations:
            if v.alert_level.value >= 3:  # ERROR or CRITICAL
                print(f"⚠️  {v.alert_level.name}: {v.message}")

    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    # Aggressive risk limits for demonstration
    aggressive_limits = RiskLimits(
        max_position_pct=0.25,  # 25% max per position
        max_leverage=1.5,  # 1.5x leverage
        max_drawdown=0.25,  # 25% max drawdown
        stop_trading_drawdown=0.20,  # Stop at 20%
        max_concentrated_positions=5,
        max_portfolio_volatility=0.30
    )

    config = BacktestConfig(
        initial_capital=100000,
        commission_rate=0.001,  # 0.1%
        slippage_rate=0.0005,  # 0.05%

        # Performance
        show_progress=True,

        # Risk Management
        enable_risk_checks=True,
        risk_limits=aggressive_limits,
        risk_check_mode='warn',
        risk_calc_frequency=5,  # More frequent for demo

        # Position Sizing
        use_position_sizer=True,
        position_sizing_method='risk_based',
        max_position_size=0.25,
        risk_per_trade=0.03,  # 3% risk per trade

        # Event Hooks
        on_risk_violation=handle_violations,
        log_signals=False  # Too verbose for complete example
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    results = orchestrator.run(
        symbols=['SBIN', 'INFY', 'TCS', 'RELIANCE'],
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Comprehensive results display
    print(results.summary())

    # Additional analytics
    print("\n" + "="*80)
    print("ENHANCED ANALYTICS")
    print("="*80)

    # Drawdown periods
    if results.drawdown_periods:
        print(f"\nSignificant Drawdown Periods: {len(results.drawdown_periods)}")
        for i, dd in enumerate(results.drawdown_periods[:3], 1):
            print(f"\n  Period {i}:")
            print(f"    Start: {dd['start_date']}")
            print(f"    End: {dd['end_date']}")
            print(f"    Max DD: {dd['max_drawdown']*100:.2f}% on {dd['max_dd_date']}")
            print(f"    Duration: {dd['duration_days']} days")

    # Monthly returns
    if results.monthly_returns:
        print(f"\nMonthly Returns: {len(results.monthly_returns)} months")
        print("  Recent months:")
        for month, ret in list(results.monthly_returns.items())[-3:]:
            print(f"    {month}: {ret*100:+.2f}%")

    # Trade analysis
    if results.trade_analysis:
        print("\nTrade Analysis:")
        ta = results.trade_analysis
        print(f"  Total Trades: {ta.get('total_transactions', 0)}")
        print(f"  Profitable: {ta.get('profitable_trades', 0)}")
        print(f"  Losing: {ta.get('losing_trades', 0)}")
        print(f"  Avg Profit: Rs {ta.get('avg_profit', 0):,.2f}")
        print(f"  Avg Loss: Rs {ta.get('avg_loss', 0):,.2f}")
        print(f"  Max Profit: Rs {ta.get('max_profit', 0):,.2f}")
        print(f"  Max Loss: Rs {ta.get('max_loss', 0):,.2f}")
        print(f"  Profit Factor: {ta.get('profit_factor', 0):.2f}")

    print(f"\nTotal Risk Violations: {violation_count['total']}")

    # Export results to JSON
    results_dict = results.to_dict()
    print(f"\nResults exportable to JSON with {len(results_dict)} fields")

    return results


# ============================================================================
# EXAMPLE 6: Stop-Loss and Target Exit Testing
# ============================================================================

def example_6_stoploss_and_target_test():
    """
    Demonstrates stop-loss and target exit functionality.

    This example uses the LimitOrderStopLossStrategy to test:
    - Limit orders that execute when price reaches limit
    - Stop-loss exits that trigger when price drops
    - Target exits that trigger when profit target is reached
    - Market orders with stop-loss and target protection

    This is the most comprehensive test of risk management features.
    """
    print("\n" + "="*80)
    print("EXAMPLE 6: Stop-Loss and Target Exit Testing")
    print("="*80 + "\n")

    # Create the limit order + stop-loss strategy
    strategy = LimitOrderStopLossStrategy(
        name="StopLoss_Target_Demo",
        limit_order_pct=0.98,  # Place limit order 2% below current price
        stop_loss_pct=0.96,    # Stop-loss at 4% below entry
        target_pct=1.08        # Target at 8% above entry
    )

    print("Strategy Configuration:")
    print(f"  Limit Order: 2% below current price")
    print(f"  Stop-Loss: 4% below entry price")
    print(f"  Target: 8% above entry price")
    print()

    # Configure with features that complement stop-loss testing
    config = BacktestConfig(
        initial_capital=100000,
        commission_rate=0.001,  # 0.1% commission
        slippage_rate=0.0005,   # 0.05% slippage

        # Performance
        show_progress=True,

        # Light risk management (let stop-loss/target do their job)
        enable_risk_checks=False,  # Disable to focus on stop-loss/target

        # No position sizer - strategy controls quantities
        use_position_sizer=False,

        # Logging
        log_signals=True  # See all signals including stop-loss/target triggers
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    # Run with a single symbol for clear demonstration
    results = orchestrator.run(
        symbols=['SBIN'],  # Single symbol for clarity
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Display results
    print(results.summary())

    # Detailed analysis of stop-loss and target executions
    print("\n" + "="*80)
    print("STOP-LOSS AND TARGET ANALYSIS")
    print("="*80)

    # Analyze orders
    all_orders = orchestrator.all_orders
    limit_orders = [o for o in all_orders if o.order_type.value == 'LIMIT']
    market_orders = [o for o in all_orders if o.order_type.value == 'MARKET']

    print(f"\nOrder Summary:")
    print(f"  Total Orders: {len(all_orders)}")
    print(f"  Limit Orders: {len(limit_orders)}")
    print(f"  Market Orders: {len(market_orders)}")

    # Check for orders with stop-loss and targets
    orders_with_sl = [o for o in all_orders if hasattr(o, 'position_stop_loss') and o.position_stop_loss]
    orders_with_target = [o for o in all_orders if hasattr(o, 'position_target') and o.position_target]

    print(f"  Orders with Stop-Loss: {len(orders_with_sl)}")
    print(f"  Orders with Target: {len(orders_with_target)}")

    if orders_with_sl:
        print("\n  Stop-Loss Details:")
        for i, order in enumerate(orders_with_sl[:3], 1):  # Show first 3
            print(f"    {i}. {order.symbol}: Entry ~Rs {order.average_fill_price or 0:.2f}, "
                  f"Stop @Rs {order.position_stop_loss:.2f}, "
                  f"Target @Rs {order.position_target:.2f}")

    # Analyze transactions for exits
    from backtester.portfolio_manager.models import TransactionType
    transactions = results.transactions
    buy_txns = [t for t in transactions if t.action == TransactionType.BUY]
    sell_txns = [t for t in transactions if t.action == TransactionType.SELL]

    print(f"\nTransaction Summary:")
    print(f"  Buy Transactions: {len(buy_txns)}")
    print(f"  Sell Transactions (Exits): {len(sell_txns)}")

    # Try to identify stop-loss vs target exits
    if sell_txns:
        print("\n  Exit Details:")
        for i, txn in enumerate(sell_txns, 1):
            exit_type = "Exit"
            if 'stop' in txn.notes.lower():
                exit_type = "STOP-LOSS"
            elif 'target' in txn.notes.lower():
                exit_type = "TARGET"

            print(f"    {i}. {txn.symbol} {exit_type} @Rs {txn.price:.2f} "
                  f"(Qty: {txn.quantity}, {txn.timestamp.date()})")

    # Performance metrics
    if results.total_return != 0:
        print(f"\nPerformance with Stop-Loss/Target:")
        print(f"  Initial Capital: Rs {results.initial_capital:,.2f}")
        print(f"  Final Capital: Rs {results.final_capital:,.2f}")
        print(f"  Total Return: {results.total_return:.2f}%")
        if results.final_risk_metrics and hasattr(results.final_risk_metrics, 'max_drawdown'):
            print(f"  Max Drawdown: {results.final_risk_metrics.max_drawdown*100:.2f}%")

    print("\n" + "="*80)
    print("KEY OBSERVATIONS")
    print("="*80)
    print("1. Stop-loss protection: Limits downside risk automatically")
    print("2. Target exits: Locks in profits at predefined levels")
    print("3. Limit orders: Enter positions at favorable prices")
    print("4. Conservative fills: Realistic execution simulation")
    print()

    return results


# ============================================================================
# EXAMPLE 7: Backtest with Visualization
# ============================================================================

def example_7_with_visualization():
    """
    Demonstrates visualization features with simplified API (v2.0.0).

    Shows:
    - HTML report generation with dark theme
    - Interactive equity chart with drawdown
    - OHLC Candlestick charts with buy/sell markers
    - Trade annotations

    Note: Streaming/real-time monitoring removed in v2.0.0 simplification.
    Visualization is now post-backtest only for clarity and simplicity.
    """
    print("\n" + "="*80)
    print("EXAMPLE 7: Backtest with Visualization (Simplified)")
    print("="*80 + "\n")

    # Symbols to visualize
    symbols = ['SBIN', 'INFY','TCS','RELIANCE']

    # Create strategy
    strategy = EnhancedMACrossover(fast_period=10, slow_period=50)

    # Configure backtest
    config = BacktestConfig(
        initial_capital=100000,
        show_progress=True,
        enable_risk_checks=True,
        risk_limits=RiskLimits.conservative(),
    )

    orchestrator = BacktestOrchestrator([strategy], config)

    print("Running backtest...")
    print("-" * 60)

    results = orchestrator.run(
        symbols=symbols,
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Display results summary
    print(results.summary())

    # Generate HTML Report and Charts
    print("\n" + "="*80)
    print("GENERATING VISUALIZATIONS")
    print("="*80)

    # HTML Report (comprehensive) with candlestick charts
    report_path = 'backtest_report.html'
    HTMLReportGenerator(results, data=orchestrator.data_cache).generate(report_path)
    print(f"\n  HTML Report saved to: {report_path}")
    print(f"      (includes candlestick charts for {len(symbols)} symbols)")

    # Equity Chart with Drawdown (combined)
    equity_path = 'equity_chart.html'
    EquityChart(results, show_drawdown=True).render().save(equity_path)
    print(f"  Equity Chart (with drawdown) saved to: {equity_path}")

    # Print trade details for annotation reference
    print("\n" + "-"*60)
    print("TRADE ANNOTATIONS")
    print("-"*60)

    if results.transactions:
        for i, tx in enumerate(results.transactions[:20], 1):  # Show first 20
            action = tx.action.value if hasattr(tx.action, 'value') else str(tx.action)
            marker = "🟢 BUY " if action.upper() == 'BUY' else "🔴 SELL"
            print(f"  {i:2}. {marker} {tx.symbol:8} | {tx.timestamp.strftime('%Y-%m-%d')} | "
                  f"Qty: {tx.quantity:4} | Price: Rs {tx.price:,.2f}")

        if len(results.transactions) > 20:
            print(f"  ... and {len(results.transactions) - 20} more trades")
    else:
        print("  No trades executed")

    # Summary of all generated files
    print("\n" + "="*80)
    print("VISUALIZATION COMPLETE!")
    print("="*80)
    print("\nGenerated Files:")
    print(f"  1. {report_path} - Full backtest report with metrics & trade log")
    print(f"  2. {equity_path} - Interactive equity curve with drawdown")

    print("\nChart Features:")
    print("  - Dark theme (TradingView-style)")
    print("  - Interactive Plotly charts")
    print("  - Equity curve with drawdown analysis")
    print("  - Candlestick charts with trade markers for each symbol")
    print("  - Volume bars and buy/sell annotations")
    print("  - Zoom, pan, and hover for detailed analysis")

    print("\nTip: Open the HTML report in your browser to see all interactive charts!")

    return results


# ============================================================================
# MAIN - Run All Examples
# ============================================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║         ENHANCED BACKTESTING ORCHESTRATOR - FEATURE DEMONSTRATION        ║
╚══════════════════════════════════════════════════════════════════════════╝

This script demonstrates all the new features of the enhanced backtesting system:

1. Basic Enhanced Backtest - Polars + Progress Bar
2. With Risk Management - Limits, Validation, Metrics
3. Advanced Position Sizing - Kelly, Risk-based, ATR
4. With Event Hooks - Custom monitoring and logic
5. Complete Showcase - All features together
6. Stop-Loss and Target Testing - Limit orders, stop-loss, target exits
7. WITH VISUALIZATION - Real-time monitoring + HTML reports + Charts

NOTE: This is a demonstration. Actual performance depends on:
      - Available market data
      - Network connectivity (for data fetching)
      - System resources

Press Ctrl+C to skip any example.
    """)

    # Run examples (comment out any you don't want to run)
    try:
        # # Example 1: Basic
        # results1 = example_1_basic_enhanced()
        # input("\nPress Enter to continue to Example 2...")

        # # Example 2: Risk Management
        # results2 = example_2_with_risk_management()
        # input("\nPress Enter to continue to Example 3...")

        # # Example 3: Position Sizing
        # results3 = example_3_advanced_position_sizing()
        # input("\nPress Enter to continue to Example 4...")

        # # Example 4: Event Hooks
        # results4 = example_4_with_event_hooks()
        # input("\nPress Enter to continue to Example 5...")

        # # Example 5: Complete Showcase
        # results5 = example_5_complete_showcase()
        # input("\nPress Enter to continue to Example 6...")

        # # Example 6: Stop-Loss and Target Testing
        # results6 = example_6_stoploss_and_target_test()
        input("\nPress Enter to continue to Example 7 (Visualization)...")

        # # Example 7: Visualization
        results7 = example_7_with_visualization()

        print("\n" + "="*80)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\nKey Takeaways:")
        print("✅ Polars integration provides 5-10x performance improvement")
        print("✅ Risk management prevents excessive drawdowns")
        print("✅ Advanced position sizing optimizes capital allocation")
        print("✅ Event hooks enable custom monitoring and logic")
        print("✅ Comprehensive analytics for better decision making")
        print("✅ Stop-loss and target exits provide automated risk management")
        print("✅ Visualization enables real-time monitoring and HTML reports")

    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        print("\nNote: Examples require market data to be available.")
        print("If data fetching fails, check your internet connection and API credentials.")
