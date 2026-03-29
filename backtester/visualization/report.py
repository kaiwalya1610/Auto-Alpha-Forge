"""
HTML report generator for comprehensive backtest visualization.

Generates a complete, self-contained HTML report with:
- Summary metrics cards
- Interactive equity curve
- Trade log table
- Risk metrics (if available)

Dark theme only.
"""

from typing import Any
from datetime import datetime
from pathlib import Path
import json
import polars as pl

from .renderer import THEME, render_candlestick
from .adapters import adapt_equity, adapt_ohlcv, adapt_trades


class HTMLReportGenerator:
    """
    Generates comprehensive HTML report from BacktestResults.

    Creates a complete, self-contained HTML file with:
    - Performance summary (12+ KPIs)
    - Interactive equity curve with drawdown
    - Trade log table
    - Risk metrics section

    Example:
        report = HTMLReportGenerator(results)
        report.generate('backtest_report.html')

        # Or get HTML string
        html = report.to_html()
    """

    def __init__(self, results: Any, data: Any = None):
        """
        Initialize report generator.

        Args:
            results: BacktestResults from backtest
            data: Optional OHLCV data (dict or DataFrame) for candlestick charts
                  If dict: {symbol: DataFrame} or {symbol: {interval: DataFrame}}
        """
        self.results = results
        self.data = data

    def generate(self, output_path: str) -> str:
        """
        Generate HTML report and save to file.

        Args:
            output_path: Path to save HTML file

        Returns:
            Absolute path to generated file
        """
        html = self.to_html()

        path = Path(output_path)
        path.write_text(html, encoding='utf-8')

        return str(path.absolute())

    def to_html(self) -> str:
        """
        Generate HTML report as string.

        Returns:
            Complete HTML string
        """
        # Generate sections
        metrics_html = self._generate_metrics_section()
        equity_html = self._generate_equity_section()
        candlestick_html = self._generate_candlestick_section()
        trades_html = self._generate_trades_section()
        risk_html = self._generate_risk_section()

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report - {self.results.strategy_name}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        {self._get_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Backtest Report</h1>
            <p class="strategy-name">{self.results.strategy_name}</p>
            <p class="date-range">{self.results.start_date.strftime('%Y-%m-%d')} to {self.results.end_date.strftime('%Y-%m-%d')}</p>
            <p class="duration">{(self.results.end_date - self.results.start_date).days} days</p>
        </header>

        {metrics_html}
        {equity_html}
        {candlestick_html}
        {risk_html}
        {trades_html}

        <footer>
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Powered by ZerodhaAlgoTradingInfra Backtester</p>
        </footer>
    </div>
</body>
</html>
"""

    def _generate_metrics_section(self) -> str:
        """Generate summary metrics cards."""
        r = self.results
        m = r.metrics

        # Determine colors based on values
        pnl_class = "positive" if r.total_pnl >= 0 else "negative"
        return_class = "positive" if r.total_return >= 0 else "negative"

        # Get risk metrics if available
        sharpe = m.get('sharpe_ratio', 0)
        if r.final_risk_metrics:
            sharpe = r.final_risk_metrics.sharpe_ratio

        return f"""
        <section class="metrics-section">
            <h2>Performance Summary</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <span class="metric-label">Initial Capital</span>
                    <span class="metric-value">Rs {r.initial_capital:,.0f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Final Capital</span>
                    <span class="metric-value">Rs {r.final_capital:,.0f}</span>
                </div>
                <div class="metric-card {pnl_class}">
                    <span class="metric-label">Total P&L</span>
                    <span class="metric-value">Rs {r.total_pnl:,.0f}</span>
                </div>
                <div class="metric-card {return_class}">
                    <span class="metric-label">Total Return</span>
                    <span class="metric-value">{r.total_return:+.2f}%</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Sharpe Ratio</span>
                    <span class="metric-value">{sharpe:.3f}</span>
                </div>
                <div class="metric-card negative">
                    <span class="metric-label">Max Drawdown</span>
                    <span class="metric-value">{m.get('max_drawdown', 0):.2f}%</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Win Rate</span>
                    <span class="metric-value">{m.get('win_rate', 0) * 100:.1f}%</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Total Trades</span>
                    <span class="metric-value">{m.get('total_trades', len(r.transactions))}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Profit Factor</span>
                    <span class="metric-value">{m.get('profit_factor', 0):.2f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Avg Win</span>
                    <span class="metric-value positive">Rs {m.get('avg_win', 0):,.0f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Avg Loss</span>
                    <span class="metric-value negative">Rs {m.get('avg_loss', 0):,.0f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Total Signals</span>
                    <span class="metric-value">{len(r.signals)}</span>
                </div>
            </div>
        </section>
        """

    def _generate_equity_section(self) -> str:
        """Generate equity curve chart section."""
        # Adapt equity data
        equity_df = adapt_equity(self.results)
        pdf = equity_df.to_pandas()

        timestamp_col = 'timestamp' if 'timestamp' in pdf.columns else pdf.columns[0]

        # Create Plotly chart data
        equity_trace = {
            'x': pdf[timestamp_col].astype(str).tolist(),
            'y': pdf['total_value'].tolist(),
            'type': 'scatter',
            'mode': 'lines',
            'name': 'Portfolio Value',
            'line': {'color': THEME['equity_line'], 'width': 2},
            'fill': 'tozeroy',
            'fillcolor': THEME['equity_fill'],
        }

        drawdown_trace = {
            'x': pdf[timestamp_col].astype(str).tolist(),
            'y': pdf['drawdown'].tolist(),
            'type': 'scatter',
            'mode': 'lines',
            'name': 'Drawdown %',
            'line': {'color': THEME['drawdown_line'], 'width': 1.5},
            'fill': 'tozeroy',
            'fillcolor': THEME['drawdown_fill'],
            'yaxis': 'y2',
        }

        layout = {
            'title': 'Portfolio Performance',
            'paper_bgcolor': THEME['background'],
            'plot_bgcolor': THEME['background'],
            'font': {'color': THEME['text']},
            'showlegend': True,
            'legend': {'x': 0, 'y': 1.1, 'orientation': 'h'},
            'xaxis': {
                'title': 'Date',
                'gridcolor': THEME['grid'],
                'showgrid': True,
            },
            'yaxis': {
                'title': 'Portfolio Value (Rs)',
                'gridcolor': THEME['grid'],
                'showgrid': True,
                'side': 'left',
            },
            'yaxis2': {
                'title': 'Drawdown %',
                'gridcolor': THEME['grid'],
                'showgrid': False,
                'overlaying': 'y',
                'side': 'right',
            },
            'height': 500,
            'margin': {'t': 50, 'b': 50, 'l': 60, 'r': 60},
        }

        traces_json = json.dumps([equity_trace, drawdown_trace])
        layout_json = json.dumps(layout)

        return f"""
        <section class="chart-section">
            <h2>Equity Curve</h2>
            <div id="equity-chart" class="chart-container"></div>
            <script>
                Plotly.newPlot('equity-chart', {traces_json}, {layout_json}, {{responsive: true}});
            </script>
        </section>
        """

    def _generate_candlestick_section(self) -> str:
        """Generate candlestick chart sections for each symbol."""
        if not self.data:
            return ""

        # Determine symbols from data structure
        symbols = []
        if isinstance(self.data, dict):
            symbols = list(self.data.keys())
        else:
            # If single DataFrame, no symbol info available
            return ""

        if not symbols:
            return ""

        # Generate a candlestick chart for each symbol
        chart_htmls = []

        for symbol in symbols:
            try:
                # Adapt OHLCV data
                ohlcv_df = adapt_ohlcv(self.data, symbol=symbol)

                # Filter trades for this symbol
                symbol_trades = [t for t in self.results.transactions if t.symbol == symbol]
                trades_df = None
                if symbol_trades:
                    trades_df = adapt_trades(symbol_trades)

                # Convert to pandas for Plotly
                pdf = ohlcv_df.to_pandas()
                datetime_col = 'datetime' if 'datetime' in pdf.columns else pdf.columns[0]

                # Build candlestick trace
                candlestick_trace = {
                    'x': pdf[datetime_col].astype(str).tolist(),
                    'open': pdf['open'].tolist(),
                    'high': pdf['high'].tolist(),
                    'low': pdf['low'].tolist(),
                    'close': pdf['close'].tolist(),
                    'type': 'candlestick',
                    'name': 'OHLC',
                    'increasing': {'line': {'color': THEME['bullish_color']}, 'fillcolor': THEME['bullish_color']},
                    'decreasing': {'line': {'color': THEME['bearish_color']}, 'fillcolor': THEME['bearish_color']},
                }

                # Build volume trace
                colors = [
                    THEME['volume_up'] if c >= o else THEME['volume_down']
                    for c, o in zip(pdf['close'], pdf['open'])
                ]

                volume_trace = {
                    'x': pdf[datetime_col].astype(str).tolist(),
                    'y': pdf['volume'].tolist(),
                    'type': 'bar',
                    'name': 'Volume',
                    'marker': {'color': colors},
                    'yaxis': 'y2',
                    'showlegend': False,
                }

                traces = [candlestick_trace, volume_trace]

                # Add trade markers if available
                if trades_df is not None and len(trades_df) > 0:
                    tpdf = trades_df.to_pandas()
                    timestamp_col = 'timestamp' if 'timestamp' in tpdf.columns else tpdf.columns[0]

                    # Buy markers
                    buys = tpdf[tpdf['action'] == 'BUY']
                    if len(buys) > 0:
                        buy_trace = {
                            'x': buys[timestamp_col].astype(str).tolist(),
                            'y': buys['price'].tolist(),
                            'type': 'scatter',
                            'mode': 'markers',
                            'name': 'Buy',
                            'marker': {
                                'symbol': 'triangle-up',
                                'size': 12,
                                'color': THEME['bullish_color'],
                                'line': {'color': 'white', 'width': 1}
                            },
                            'text': [f"Buy @ Rs {p:.2f}" for p in buys['price']],
                            'hovertemplate': '%{text}<extra></extra>',
                        }
                        traces.append(buy_trace)

                    # Sell markers
                    sells = tpdf[tpdf['action'] == 'SELL']
                    if len(sells) > 0:
                        sell_trace = {
                            'x': sells[timestamp_col].astype(str).tolist(),
                            'y': sells['price'].tolist(),
                            'type': 'scatter',
                            'mode': 'markers',
                            'name': 'Sell',
                            'marker': {
                                'symbol': 'triangle-down',
                                'size': 12,
                                'color': THEME['bearish_color'],
                                'line': {'color': 'white', 'width': 1}
                            },
                            'text': [f"Sell @ Rs {p:.2f}" for p in sells['price']],
                            'hovertemplate': '%{text}<extra></extra>',
                        }
                        traces.append(sell_trace)

                # Layout
                layout = {
                    'title': f'{symbol} - OHLC with Trade Markers',
                    'paper_bgcolor': THEME['background'],
                    'plot_bgcolor': THEME['background'],
                    'font': {'color': THEME['text']},
                    'showlegend': True,
                    'legend': {'x': 0, 'y': 1.1, 'orientation': 'h'},
                    'xaxis': {
                        'title': 'Date',
                        'gridcolor': THEME['grid'],
                        'showgrid': True,
                        'rangeslider': {'visible': False},
                    },
                    'yaxis': {
                        'title': 'Price (Rs)',
                        'gridcolor': THEME['grid'],
                        'showgrid': True,
                        'side': 'left',
                    },
                    'yaxis2': {
                        'title': 'Volume',
                        'gridcolor': THEME['grid'],
                        'showgrid': False,
                        'overlaying': 'y',
                        'side': 'right',
                        'domain': [0, 0.2],
                    },
                    'height': 600,
                    'margin': {'t': 50, 'b': 50, 'l': 60, 'r': 60},
                }

                traces_json = json.dumps(traces)
                layout_json = json.dumps(layout)

                chart_id = f"candlestick-{symbol.lower().replace(' ', '-')}"

                chart_htmls.append(f"""
                <div class="chart-section">
                    <h3>{symbol}</h3>
                    <div id="{chart_id}" class="chart-container"></div>
                    <script>
                        Plotly.newPlot('{chart_id}', {traces_json}, {layout_json}, {{responsive: true}});
                    </script>
                </div>
                """)

            except Exception as e:
                # Skip symbols with errors
                print(f"Warning: Could not generate candlestick for {symbol}: {e}")
                continue

        if not chart_htmls:
            return ""

        return f"""
        <section class="candlestick-section">
            <h2>Price Charts</h2>
            {''.join(chart_htmls)}
        </section>
        """

    def _generate_trades_section(self) -> str:
        """Generate trades table section."""
        transactions = self.results.transactions
        max_trades_shown = 100

        if not transactions:
            return """
            <section class="trades-section">
                <h2>Trade Log</h2>
                <p class="no-data">No trades executed during this backtest.</p>
            </section>
            """

        # Build table rows
        rows = []
        for i, tx in enumerate(transactions[:max_trades_shown]):
            action = tx.action.value if hasattr(tx.action, 'value') else str(tx.action)
            action_class = "buy" if action.upper() == 'BUY' else "sell"

            rows.append(f"""
                <tr>
                    <td>{i + 1}</td>
                    <td>{tx.timestamp.strftime('%Y-%m-%d %H:%M')}</td>
                    <td>{tx.symbol}</td>
                    <td class="{action_class}">{action.upper()}</td>
                    <td>{tx.quantity}</td>
                    <td>Rs {tx.price:,.2f}</td>
                    <td>Rs {tx.quantity * tx.price:,.2f}</td>
                </tr>
            """)

        note = ""
        if len(transactions) > max_trades_shown:
            note = f'<p class="table-note">Showing {max_trades_shown} of {len(transactions)} trades</p>'

        return f"""
        <section class="trades-section">
            <h2>Trade Log</h2>
            <div class="table-wrapper">
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Time</th>
                            <th>Symbol</th>
                            <th>Action</th>
                            <th>Qty</th>
                            <th>Price</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>
            {note}
        </section>
        """

    def _generate_risk_section(self) -> str:
        """Generate risk metrics section."""
        if not self.results.final_risk_metrics:
            return ""

        rm = self.results.final_risk_metrics

        # Risk violations
        violations_html = ""
        if self.results.risk_events:
            violation_items = []
            for v in self.results.risk_events[:10]:
                level = v.alert_level.name.lower() if hasattr(v.alert_level, 'name') else 'warning'
                violation_items.append(f'<li class="{level}">{v.message}</li>')

            violations_html = f"""
            <div class="violations">
                <h3>Risk Violations ({len(self.results.risk_events)} total)</h3>
                <ul>{''.join(violation_items)}</ul>
            </div>
            """
        else:
            violations_html = '<p class="success">No risk violations during backtest.</p>'

        return f"""
        <section class="risk-section">
            <h2>Risk Metrics</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <span class="metric-label">Sharpe Ratio</span>
                    <span class="metric-value">{rm.sharpe_ratio:.3f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Sortino Ratio</span>
                    <span class="metric-value">{rm.sortino_ratio:.3f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">VaR (95%)</span>
                    <span class="metric-value negative">Rs {rm.portfolio_var_95:,.0f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">CVaR (95%)</span>
                    <span class="metric-value negative">Rs {rm.portfolio_cvar_95:,.0f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Volatility (Ann.)</span>
                    <span class="metric-value">{rm.portfolio_volatility * 100:.2f}%</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Max Drawdown</span>
                    <span class="metric-value negative">{rm.max_drawdown * 100:.2f}%</span>
                </div>
            </div>
            {violations_html}
        </section>
        """

    def _get_styles(self) -> str:
        """Get CSS styles for the report."""
        return f"""
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: {THEME['background']};
            color: {THEME['text']};
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 30px;
        }}

        header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid {THEME['grid']};
        }}

        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            color: {THEME['text']};
        }}

        .strategy-name {{
            font-size: 1.3rem;
            color: {THEME['line_color']};
            font-weight: 600;
        }}

        .date-range, .duration {{
            color: {THEME['text']}99;
            font-size: 0.95rem;
        }}

        section {{
            margin-bottom: 40px;
        }}

        section h2 {{
            font-size: 1.5rem;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid {THEME['grid']};
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }}

        .metric-card {{
            background: {THEME['grid']};
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            transition: transform 0.2s;
        }}

        .metric-card:hover {{
            transform: translateY(-2px);
        }}

        .metric-label {{
            display: block;
            font-size: 0.85rem;
            color: {THEME['text']}99;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .metric-value {{
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
        }}

        .positive {{ color: {THEME['bullish_color']}; }}
        .negative {{ color: {THEME['bearish_color']}; }}

        .chart-section {{
            margin-bottom: 40px;
        }}

        .chart-container {{
            background: {THEME['grid']};
            border-radius: 10px;
            padding: 15px;
            min-height: 400px;
        }}

        .table-wrapper {{
            overflow-x: auto;
        }}

        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}

        .trades-table th,
        .trades-table td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid {THEME['grid']};
        }}

        .trades-table th {{
            background: {THEME['grid']};
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
        }}

        .trades-table tr:hover {{
            background: {THEME['grid']}80;
        }}

        .buy {{ color: {THEME['bullish_color']}; font-weight: 600; }}
        .sell {{ color: {THEME['bearish_color']}; font-weight: 600; }}

        .table-note {{
            margin-top: 10px;
            font-size: 0.85rem;
            color: {THEME['text']}80;
            text-align: center;
        }}

        .no-data {{
            text-align: center;
            color: {THEME['text']}80;
            padding: 30px;
        }}

        .violations {{
            margin-top: 20px;
        }}

        .violations h3 {{
            font-size: 1.1rem;
            margin-bottom: 10px;
        }}

        .violations ul {{
            list-style: none;
        }}

        .violations li {{
            padding: 8px 15px;
            margin-bottom: 5px;
            border-radius: 5px;
            background: {THEME['grid']};
        }}

        .violations .critical {{
            border-left: 4px solid {THEME['bearish_color']};
        }}

        .violations .warning {{
            border-left: 4px solid #FFA726;
        }}

        .success {{
            color: {THEME['bullish_color']};
            text-align: center;
            padding: 20px;
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid {THEME['grid']};
            color: {THEME['text']}60;
            font-size: 0.85rem;
        }}

        @media (max-width: 768px) {{
            .container {{ padding: 15px; }}
            header h1 {{ font-size: 1.8rem; }}
            .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .metric-value {{ font-size: 1.2rem; }}
        }}
        """
