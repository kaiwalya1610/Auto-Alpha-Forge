"""
Visualization module for backtesting results.

Simplified, dark-theme only. No streaming, no abstractions.

Usage:
    from backtester.visualization import EquityChart, CandlestickChart, HTMLReportGenerator

    # Equity curve
    EquityChart(results).render().show()

    # Candlestick with trades
    CandlestickChart(price_data).add_trades(results.transactions).render().show()

    # Full HTML report
    HTMLReportGenerator(results).generate('report.html')
"""

from .charts import EquityChart, CandlestickChart
from .report import HTMLReportGenerator

__all__ = [
    'EquityChart',
    'CandlestickChart',
    'HTMLReportGenerator',
]

__version__ = '2.0.0'  # Simplified version
