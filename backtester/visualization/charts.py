"""
Chart classes for visualization.

Simple wrappers around adapters and renderers.
Dark theme only, no abstract bases.
"""

from typing import Any, Optional

from .adapters import adapt_equity, adapt_ohlcv, adapt_trades
from .renderer import render_equity_curve, render_candlestick


class EquityChart:
    """
    Portfolio equity visualization with optional drawdown.

    Renders portfolio value over time with cumulative returns
    and drawdown analysis. Dark theme only.

    Example:
        # Simple usage
        chart = EquityChart(results)
        chart.render().show()

        # Without drawdown
        chart = EquityChart(results, show_drawdown=False)
        chart.render().save('equity.html')
    """

    def __init__(self, results: Any, show_drawdown: bool = True):
        """
        Initialize equity chart.

        Args:
            results: BacktestResults or equity DataFrame
            show_drawdown: Whether to show drawdown subplot
        """
        self.results = results
        self.show_drawdown = show_drawdown
        self._figure = None

    def render(self) -> 'EquityChart':
        """
        Render the equity chart.

        Returns:
            Self for method chaining
        """
        # Adapt data
        df = adapt_equity(self.results)

        # Render figure
        self._figure = render_equity_curve(df, self.show_drawdown)

        return self

    def show(self):
        """Display the chart in browser."""
        if self._figure is None:
            raise ValueError("Call render() first")
        self._figure.show()

    def save(self, path: str):
        """
        Save chart to HTML file.

        Args:
            path: Output file path (e.g., 'equity.html')
        """
        if self._figure is None:
            raise ValueError("Call render() first")
        self._figure.write_html(path)

    def to_html(self) -> str:
        """
        Get HTML string with embedded Plotly.js.

        Returns:
            Complete HTML string
        """
        if self._figure is None:
            raise ValueError("Call render() first")
        return self._figure.to_html(include_plotlyjs='cdn')


class CandlestickChart:
    """
    OHLCV candlestick chart with optional trade markers.

    Displays price action with volume. Can overlay buy/sell markers.
    Dark theme only.

    Example:
        # Simple candlestick
        chart = CandlestickChart(price_data)
        chart.render().show()

        # With trade markers
        chart = CandlestickChart(price_data)
        chart.add_trades(results.transactions)
        chart.render().show()
    """

    def __init__(self, data: Any, symbol: Optional[str] = None):
        """
        Initialize candlestick chart.

        Args:
            data: OHLCV DataFrame, list of dicts, or data cache
            symbol: Symbol to extract (required if data is cache dict)
        """
        self.data = data
        self.symbol = symbol
        self._trades = None
        self._figure = None

    def add_trades(self, trades: Any, symbol_filter: Optional[str] = None) -> 'CandlestickChart':
        """
        Add trade markers to chart.

        Args:
            trades: BacktestResults or list of Transaction objects
            symbol_filter: Filter trades by symbol (None = all)

        Returns:
            Self for method chaining
        """
        self._trades = trades
        self._symbol_filter = symbol_filter
        return self

    def render(self) -> 'CandlestickChart':
        """
        Render the candlestick chart.

        Returns:
            Self for method chaining
        """
        # Adapt OHLCV data
        df = adapt_ohlcv(self.data, symbol=self.symbol)

        # Adapt trades if provided
        trades_df = None
        if self._trades is not None:
            symbol_filter = getattr(self, '_symbol_filter', None)
            trades_df = adapt_trades(self._trades, symbol_filter=symbol_filter)

        # Render figure
        self._figure = render_candlestick(df, trades_df)

        return self

    def show(self):
        """Display the chart in browser."""
        if self._figure is None:
            raise ValueError("Call render() first")
        self._figure.show()

    def save(self, path: str):
        """
        Save chart to HTML file.

        Args:
            path: Output file path (e.g., 'candlestick.html')
        """
        if self._figure is None:
            raise ValueError("Call render() first")
        self._figure.write_html(path)

    def to_html(self) -> str:
        """
        Get HTML string with embedded Plotly.js.

        Returns:
            Complete HTML string
        """
        if self._figure is None:
            raise ValueError("Call render() first")
        return self._figure.to_html(include_plotlyjs='cdn')
