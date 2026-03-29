"""
Plotly rendering for interactive charts.

Dark theme only, hardcoded for simplicity.
"""

from typing import Optional
import polars as pl

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None
    make_subplots = None


# Dark theme configuration (TradingView-style dark)
THEME = {
    'background': '#1E1E1E',
    'text': '#D9D9D9',
    'grid': '#2B2B43',
    'border': '#2B2B43',
    'bullish_color': '#00C853',      # Green for up candles/buys
    'bearish_color': '#FF1744',      # Red for down candles/sells
    'line_color': '#2196F3',         # Blue
    'fill_color': 'rgba(33, 150, 243, 0.1)',
    'volume_up': 'rgba(0, 200, 83, 0.5)',
    'volume_down': 'rgba(255, 23, 68, 0.5)',
    'equity_line': '#2196F3',
    'equity_fill': 'rgba(33, 150, 243, 0.1)',
    'drawdown_line': '#FF5722',
    'drawdown_fill': 'rgba(255, 87, 34, 0.3)',
}


def render_candlestick(df: pl.DataFrame, trades: Optional[pl.DataFrame] = None) -> 'go.Figure':
    """
    Render OHLCV candlestick chart with volume subplot.

    Uses dark theme. Adds trade markers if provided.

    Args:
        df: OHLCV DataFrame (datetime, open, high, low, close, volume)
        trades: Optional trade markers DataFrame

    Returns:
        Plotly Figure with candlestick and volume
    """
    if not PLOTLY_AVAILABLE:
        raise ImportError("Plotly not installed. Install with: pip install plotly>=5.18.0")

    # Convert Polars to pandas for Plotly
    pdf = df.to_pandas()

    # Determine datetime column
    datetime_col = 'datetime' if 'datetime' in pdf.columns else pdf.columns[0]

    # Create subplots: candlestick + volume
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # Candlestick trace
    fig.add_trace(
        go.Candlestick(
            x=pdf[datetime_col],
            open=pdf['open'],
            high=pdf['high'],
            low=pdf['low'],
            close=pdf['close'],
            name='OHLC',
            increasing=dict(
                line=dict(color=THEME['bullish_color']),
                fillcolor=THEME['bullish_color']
            ),
            decreasing=dict(
                line=dict(color=THEME['bearish_color']),
                fillcolor=THEME['bearish_color']
            ),
        ),
        row=1, col=1
    )

    # Volume bars
    if 'volume' in pdf.columns:
        colors = [
            THEME['volume_up'] if c >= o else THEME['volume_down']
            for c, o in zip(pdf['close'], pdf['open'])
        ]

        fig.add_trace(
            go.Bar(
                x=pdf[datetime_col],
                y=pdf['volume'],
                name='Volume',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )

    # Add trade markers if provided
    if trades is not None and len(trades) > 0:
        fig = add_trade_markers(fig, trades, row=1, col=1)

    # Apply theme and layout
    fig = apply_theme(fig)
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        xaxis2_title="Date",
        yaxis_title="Price",
        yaxis2_title="Volume",
    )

    return fig


def render_equity_curve(df: pl.DataFrame, show_drawdown: bool = True) -> 'go.Figure':
    """
    Render equity curve with optional drawdown subplot.

    Uses dark theme.

    Args:
        df: Equity DataFrame from adapt_equity (timestamp, total_value, drawdown)
        show_drawdown: Whether to show drawdown subplot

    Returns:
        Plotly Figure with equity and drawdown
    """
    if not PLOTLY_AVAILABLE:
        raise ImportError("Plotly not installed. Install with: pip install plotly>=5.18.0")

    pdf = df.to_pandas()
    timestamp_col = 'timestamp' if 'timestamp' in pdf.columns else pdf.columns[0]

    if show_drawdown and 'drawdown' in pdf.columns:
        # Create subplots: equity + drawdown
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('Portfolio Value', 'Drawdown %')
        )

        # Equity curve
        fig.add_trace(
            go.Scatter(
                x=pdf[timestamp_col],
                y=pdf['total_value'],
                name='Portfolio Value',
                mode='lines',
                line=dict(color=THEME['equity_line'], width=2),
                fill='tozeroy',
                fillcolor=THEME['equity_fill'],
            ),
            row=1, col=1
        )

        # Drawdown
        fig.add_trace(
            go.Scatter(
                x=pdf[timestamp_col],
                y=pdf['drawdown'],
                name='Drawdown',
                mode='lines',
                line=dict(color=THEME['drawdown_line'], width=1.5),
                fill='tozeroy',
                fillcolor=THEME['drawdown_fill'],
            ),
            row=2, col=1
        )

        fig.update_yaxes(title_text="Value (Rs)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown %", row=2, col=1)

    else:
        # Single chart - equity only
        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=pdf[timestamp_col],
                y=pdf['total_value'],
                mode='lines',
                name='Portfolio Value',
                line=dict(color=THEME['equity_line'], width=2),
                fill='tozeroy',
                fillcolor=THEME['equity_fill'],
            )
        )

        fig.update_yaxes(title_text="Value (Rs)")

    fig = apply_theme(fig)
    fig.update_layout(title='Equity Curve')

    return fig


def add_trade_markers(
    figure: 'go.Figure',
    trades: pl.DataFrame,
    row: int = 1,
    col: int = 1
) -> 'go.Figure':
    """
    Add buy/sell markers to existing chart.

    Args:
        figure: Existing Plotly figure
        trades: Trade data from adapt_trades
        row: Subplot row
        col: Subplot column

    Returns:
        Updated figure with trade markers
    """
    if trades is None or len(trades) == 0:
        return figure

    pdf = trades.to_pandas()
    timestamp_col = 'timestamp' if 'timestamp' in pdf.columns else pdf.columns[0]

    # Separate buys and sells
    buys = pdf[pdf['action'] == 'BUY']
    sells = pdf[pdf['action'] == 'SELL']

    # Buy markers (green triangles up)
    if len(buys) > 0:
        figure.add_trace(
            go.Scatter(
                x=buys[timestamp_col],
                y=buys['price'],
                mode='markers',
                name='Buy',
                marker=dict(
                    symbol='triangle-up',
                    size=buys['marker_size'] if 'marker_size' in buys.columns else 12,
                    color=THEME['bullish_color'],
                    line=dict(color='white', width=1)
                ),
                text=buys.get('annotation_text', buys['price'].apply(lambda x: f"Buy @ {x:.2f}")),
                hovertemplate='%{text}<extra></extra>'
            ),
            row=row, col=col
        )

    # Sell markers (red triangles down)
    if len(sells) > 0:
        figure.add_trace(
            go.Scatter(
                x=sells[timestamp_col],
                y=sells['price'],
                mode='markers',
                name='Sell',
                marker=dict(
                    symbol='triangle-down',
                    size=sells['marker_size'] if 'marker_size' in sells.columns else 12,
                    color=THEME['bearish_color'],
                    line=dict(color='white', width=1)
                ),
                text=sells.get('annotation_text', sells['price'].apply(lambda x: f"Sell @ {x:.2f}")),
                hovertemplate='%{text}<extra></extra>'
            ),
            row=row, col=col
        )

    return figure


def apply_theme(figure: 'go.Figure', width: int = 1200, height: int = 600) -> 'go.Figure':
    """
    Apply dark theme styling to Plotly figure.

    Args:
        figure: Plotly figure
        width: Figure width in pixels
        height: Figure height in pixels

    Returns:
        Styled figure
    """
    # Apply dark theme
    figure.update_layout(
        template='plotly_dark',
        paper_bgcolor=THEME['background'],
        plot_bgcolor=THEME['background'],
        font=dict(color=THEME['text']),
    )

    # Common layout settings
    figure.update_layout(
        width=width,
        height=height,
        showlegend=True,
        hovermode='x unified',
    )

    # Grid settings
    figure.update_xaxes(
        showgrid=True,
        gridcolor=THEME['grid'],
    )
    figure.update_yaxes(
        showgrid=True,
        gridcolor=THEME['grid'],
    )

    return figure
