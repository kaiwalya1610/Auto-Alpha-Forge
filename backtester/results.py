"""
Backtest Results

This module contains the BacktestResults dataclass which stores comprehensive
backtest results including performance metrics, risk analytics, and trade details.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import polars as pl

from backtester.portfolio_manager import Transaction
from backtester.strategy import Signal
from backtester.risk_manager import RiskMetrics, RiskEvent, RiskAlertLevel
from backtester.utils import polars_to_pandas


@dataclass
class BacktestResults:
    """
    Complete backtest results with comprehensive performance and risk metrics.

    Attributes:
        strategy_name: Name of the strategy
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Starting capital
        final_capital: Ending capital
        total_return: Total return percentage
        total_pnl: Total profit/loss
        transactions: List of all transactions
        equity_curve: DataFrame with equity over time (Polars or Pandas)
        metrics: Dictionary of performance metrics
        signals: List of all generated signals
        config: Backtest configuration used

        # Risk Metrics (NEW)
        risk_metrics_history: List of RiskMetrics snapshots over time
        final_risk_metrics: Final risk snapshot
        risk_events: All risk violations that occurred
        position_sizing_stats: Statistics about position sizing decisions

        # Additional Analytics
        monthly_returns: Monthly return breakdown
        drawdown_periods: List of drawdown period details
        trade_analysis: Detailed trade statistics
    """
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_pnl: float
    transactions: List[Transaction]
    equity_curve: pl.DataFrame  # Changed to Polars for performance
    metrics: Dict
    signals: List[Signal] = field(default_factory=list)
    config: Optional['BacktestConfig'] = None  # Forward reference

    # Risk Management Results
    risk_metrics_history: List[RiskMetrics] = field(default_factory=list)
    final_risk_metrics: Optional[RiskMetrics] = None
    risk_events: List[RiskEvent] = field(default_factory=list)
    position_sizing_stats: Dict = field(default_factory=dict)

    # Additional Analytics
    monthly_returns: Optional[Dict] = None
    drawdown_periods: List[Dict] = field(default_factory=list)
    trade_analysis: Dict = field(default_factory=dict)

    def summary(self) -> str:
        """Generate human-readable summary"""
        risk_summary = ""
        if self.final_risk_metrics is not None:
            risk_summary = f"""
Risk Metrics:
  Sharpe Ratio: {self.final_risk_metrics.sharpe_ratio:.3f}
  Sortino Ratio: {self.final_risk_metrics.sortino_ratio:.3f}
  Max Drawdown: {self.final_risk_metrics.max_drawdown*100:.2f}%
  Portfolio Volatility: {self.final_risk_metrics.portfolio_volatility*100:.2f}%
  VaR (95%): Rs {self.final_risk_metrics.portfolio_var_95:,.2f}
  CVaR (95%): Rs {self.final_risk_metrics.portfolio_cvar_95:,.2f}
  Risk Violations: {len(self.risk_events)}
"""

        return f"""
╔══════════════════════════════════════════════════════════════╗
║                  BACKTEST RESULTS SUMMARY                     ║
╚══════════════════════════════════════════════════════════════╝

Strategy: {self.strategy_name}
Period: {self.start_date.date()} to {self.end_date.date()}
Duration: {(self.end_date - self.start_date).days} days

Portfolio Performance:
  Initial Capital: Rs {self.initial_capital:,.2f}
  Final Capital: Rs {self.final_capital:,.2f}
  Total Return: {self.total_return:.2f}%
  Total P&L: Rs {self.total_pnl:,.2f}

Trading Activity:
  Total Signals: {len(self.signals)}
  Total Trades: {len(self.transactions)}
  Win Rate: {self.metrics.get('win_rate', 0)*100:.2f}%
  Profit Factor: {self.metrics.get('profit_factor', 0):.2f}
{risk_summary}
Performance Metrics:
{self._format_metrics()}
"""

    def _format_metrics(self) -> str:
        """Format metrics dictionary"""
        lines = []
        # Skip metrics already shown in summary
        skip_keys = {'win_rate', 'profit_factor', 'total_trades', 'winning_trades', 'losing_trades'}

        for key, value in self.metrics.items():
            if key in skip_keys:
                continue

            if isinstance(value, float):
                if 'ratio' in key.lower() or 'sharpe' in key.lower() or 'sortino' in key.lower():
                    lines.append(f"  {key}: {value:.3f}")
                elif 'pct' in key.lower() or 'return' in key.lower() or 'drawdown' in key.lower():
                    lines.append(f"  {key}: {value:.2f}%")
                else:
                    lines.append(f"  {key}: {value:.4f}")
            else:
                lines.append(f"  {key}: {value}")

        return "\n".join(lines) if lines else "  (No additional metrics)"

    def get_equity_curve_pandas(self):
        """
        Get equity curve as Pandas DataFrame.

        Convenience method for compatibility with existing code and libraries
        that require Pandas (e.g., plotting libraries).

        Returns:
            Pandas DataFrame with equity curve
        """
        if isinstance(self.equity_curve, pl.DataFrame):
            return polars_to_pandas(self.equity_curve, set_index='timestamp')
        return self.equity_curve

    def get_risk_violations_by_level(self, level: RiskAlertLevel) -> List[RiskEvent]:
        """Get risk violations of specific severity level."""
        return [event for event in self.risk_events if event.alert_level == level]

    def get_critical_violations(self) -> List[RiskEvent]:
        """Get critical risk violations."""
        return self.get_risk_violations_by_level(RiskAlertLevel.CRITICAL)

    def has_risk_violations(self) -> bool:
        """Check if any risk violations occurred."""
        return len(self.risk_events) > 0

    def to_dict(self) -> Dict:
        """
        Convert results to dictionary for serialization.

        Returns:
            Dictionary with all results data
        """
        return {
            'strategy_name': self.strategy_name,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': self.total_return,
            'total_pnl': self.total_pnl,
            'metrics': self.metrics,
            'num_transactions': len(self.transactions),
            'num_signals': len(self.signals),
            'risk_events': [event.to_dict() for event in self.risk_events],
            'final_risk_metrics': self.final_risk_metrics.to_dict() if self.final_risk_metrics else None,
            'position_sizing_stats': self.position_sizing_stats,
            'monthly_returns': self.monthly_returns,
            'drawdown_periods': self.drawdown_periods,
            'trade_analysis': self.trade_analysis
        }
