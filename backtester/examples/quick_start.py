"""
Quick Start - Enhanced Backtesting Orchestrator

A minimal example to get started with the enhanced backtesting system.
This demonstrates the simplest way to use the new features.

Usage:
    python quick_start.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtester.backtest_orchestrator import BacktestOrchestrator, BacktestConfig
from backtester.data_loader import Interval
from backtester.risk_manager import RiskLimits
from backtester.strategy.examples.buy_and_hold import BuyAndHold


def main():
    """Run a simple enhanced backtest."""

    print("""
╔══════════════════════════════════════════════════════════════╗
║        ENHANCED BACKTESTING ORCHESTRATOR - QUICK START       ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # Step 1: Create a strategy (using built-in buy-and-hold)
    strategy = BuyAndHold()

    # Step 2: Configure the backtest with enhanced features
    config = BacktestConfig(
        # Basic settings
        initial_capital=100000,
        commission_rate=0.001,  # 0.1%

        # Enhanced features (NEW!)
        show_progress=True,  # 📊 Beautiful progress bar

        # Optional: Add risk management
        enable_risk_checks=True,
        risk_limits=RiskLimits.conservative(),
        risk_check_mode='warn',  # Log warnings but don't block orders

        # Optional: Advanced position sizing
        use_position_sizer=True,
        position_sizing_method='equal',  # Equal weighting
        max_position_size=0.20  # Max 20% per position
    )

    # Step 3: Create orchestrator
    orchestrator = BacktestOrchestrator([strategy], config)

    # Step 4: Run backtest
    print("Running backtest...\n")

    results = orchestrator.run(
        symbols=['SBIN', 'INFY'],  # Add more symbols as needed
        start_date='2024-01-01',
        end_date='2024-06-30',
        interval=Interval.DAY,
        exchange='NSE'
    )

    # Step 5: View results
    print("\n" + results.summary())

    # Step 6: Access detailed analytics (NEW!)
    if results.final_risk_metrics:
        print("\n📊 Risk Metrics:")
        print(f"   Sharpe Ratio: {results.final_risk_metrics.sharpe_ratio:.3f}")
        print(f"   Max Drawdown: {results.final_risk_metrics.max_drawdown*100:.2f}%")
        print(f"   Volatility: {results.final_risk_metrics.portfolio_volatility*100:.2f}%")

    if results.monthly_returns:
        print(f"\n📅 Monthly Returns: {len(results.monthly_returns)} months calculated")

    if results.drawdown_periods:
        print(f"\n📉 Drawdown Periods: {len(results.drawdown_periods)} significant periods identified")

    # Step 7: Export if needed
    # results_dict = results.to_dict()
    # import json
    # with open('backtest_results.json', 'w') as f:
    #     json.dump(results_dict, f, indent=2, default=str)

   

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  - Check internet connection (for data fetching)")
        print("  - Verify API credentials in .env file")
        print("  - Ensure data is available for the date range")
        import traceback
        traceback.print_exc()
