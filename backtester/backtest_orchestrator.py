"""
Backtest Orchestrator - Main backtesting engine

This module contains the BacktestOrchestrator class which coordinates all components
of the backtesting system:
- Data loading and management
- Portfolio tracking
- Strategy execution
- Signal-to-order conversion
- Results generation

The orchestrator follows the event-driven architecture pattern, processing
market data bar-by-bar and allowing strategies to generate signals at each step.
"""

from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd
import polars as pl
import numpy as np
import logging
import gc

from backtester.data_loader import DataOrchestrator, Interval
from backtester.portfolio_manager import PortfolioManager, Order, Transaction
from backtester.portfolio_manager.models import TransactionType, OrderType, OrderStatus
from backtester.strategy import Strategy, Signal, SignalDirection, StrategyContext
from backtester.risk_manager import (
    RiskCalculator, PositionSizer, PortfolioOptimizer, RiskMonitor,
    RiskLimits, RiskMetrics, RiskEvent, RiskAlertLevel, PositionRisk
)
from backtester.utils import (
    pandas_to_polars, polars_to_pandas,
    create_equity_curve_polars,
    setup_backtest_logging,
)
from backtester.config import BacktestConfig
from backtester.results import BacktestResults

logger = logging.getLogger(__name__)


class BacktestOrchestrator:
    """
    Main backtesting engine that coordinates all components.

    The orchestrator follows this workflow:
    1. Initialize: Set up data loader, portfolio manager, and strategies
    2. Load Data: Fetch and align historical data for all symbols
    3. Event Loop: Process each bar chronologically
       - Create StrategyContext
       - Get signals from strategies
       - Convert signals to orders
       - Execute orders through portfolio manager
       - Record equity snapshot
    4. Generate Results: Compile performance metrics and analytics

    Example:
        ```python
        # Create strategy
        strategy = MovingAverageCrossover(fast=10, slow=50)

        # Configure backtest
        config = BacktestConfig(
            initial_capital=100000,
            commission_rate=0.001
        )

        # Create orchestrator
        orchestrator = BacktestOrchestrator(
            strategies=[strategy],
            config=config
        )

        # Run backtest
        results = orchestrator.run(
            symbols=['SBIN', 'INFY', 'TCS'],
            start_date='2024-01-01',
            end_date='2024-12-31',
            interval=Interval.DAY
        )

        # Analyze results
        print(results.summary())
        ```
    """

    def __init__(
        self,
        strategies: List[Strategy],
        config: Optional[BacktestConfig] = None,
        data_orchestrator: Optional[DataOrchestrator] = None
    ):
        """
        Initialize BacktestOrchestrator.

        Args:
            strategies: List of Strategy instances to backtest
            config: Backtest configuration (uses defaults if not provided)
            data_orchestrator: DataOrchestrator instance (creates new if not provided)
        """
        self.strategies:list = strategies
        self.config = config if config is not None else BacktestConfig()
        self.data_orchestrator = data_orchestrator if data_orchestrator is not None else DataOrchestrator()

        # Set up dedicated log file for this backtest run
        self._log_file = setup_backtest_logging()
        logger.info("Backtest log file: %s", self._log_file)

        # Will be initialized in run()
        self.portfolio_manager: Optional[PortfolioManager] = None
        self.symbols: List[str] = []
        # Multi-timeframe data cache: {symbol: {interval: DataFrame}}
        self.data_cache: Dict[str, Dict[Interval, pl.DataFrame]] = {}
        self.aligned_timestamps: List[datetime] = []
        
        # Multi-timeframe settings
        self.primary_interval: Optional[Interval] = None  # Drives the event loop
        self.all_intervals: List[Interval] = []  # All intervals loaded

        # Track signals and orders
        self.all_signals: List[Signal] = []
        self.all_orders: List[Order] = []
        self.pending_orders: List[Order] = []  # Orders waiting to be filled

        # Risk Management Components
        self.risk_calculator: Optional[RiskCalculator] = None
        self.position_sizer: Optional[PositionSizer] = None
        self.portfolio_optimizer: Optional[PortfolioOptimizer] = None
        self.risk_monitor: Optional[RiskMonitor] = None

        # Risk tracking
        self.risk_metrics_history: List[RiskMetrics] = []
        self.risk_events: List[RiskEvent] = []
        self.position_sizing_decisions: List[Dict] = []

        # Initialize risk components if enabled
        if self.config.enable_risk_checks:
            self.risk_calculator = RiskCalculator()
            self.risk_monitor = RiskMonitor(
                risk_limits=self.config.risk_limits,
                halt_on_critical=(self.config.risk_check_mode == 'block')
            )
            logger.info("Risk management enabled with mode: %s", self.config.risk_check_mode)

        # Initialize position sizer if enabled
        if self.config.use_position_sizer:
            # Ensure risk_limits exists, create defaults if needed
            risk_limits = self.config.risk_limits if self.config.risk_limits is not None else RiskLimits.conservative()
            self.position_sizer = PositionSizer(risk_limits=risk_limits)
            logger.info("Position sizer enabled with method: %s", self.config.position_sizing_method)

        # Initialize portfolio optimizer if rebalancing enabled
        if self.config.enable_rebalancing:
            self.portfolio_optimizer = PortfolioOptimizer()
            logger.info(
                "Portfolio rebalancing enabled: every %s bars using %s",
                self.config.rebalance_frequency, self.config.optimization_method
            )

        logger.info(
            f"BacktestOrchestrator initialized with {len(strategies)} "
            f"strateg{'y' if len(strategies) == 1 else 'ies'} (using Polars for performance)"
        )

    def run(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        interval: Interval,
        exchange: str = "NSE"
    ) -> BacktestResults:
        """
        Run backtest for specified symbols and date range.

        Args:
            symbols: List of symbols to trade
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            interval: Data interval (from Interval enum)
            exchange: Exchange name (default: NSE)

        Returns:
            BacktestResults with complete performance data

        Raises:
            ValueError: If no data available or invalid parameters
        """
        logger.info(f"Starting backtest: {start_date} to {end_date}")
        logger.info(f"Symbols: {symbols}")
        logger.info(f"Interval: {interval.value}")

        # Store configuration
        self.symbols = symbols

        # Step 1: Load and align data
        self._load_data(symbols, exchange, start_date, end_date, interval)

        # Step 2: Initialize portfolio manager
        self.portfolio_manager = PortfolioManager(
            initial_capital=self.config.initial_capital,
            commission_rate=self.config.commission_rate,
            slippage_rate=self.config.slippage_rate
        )

        # Step 3: Run event loop
        self._run_event_loop()

        # Step 4: Generate and return results
        return self._generate_results(start_date, end_date)

    def _collect_required_intervals(self, primary_interval: Interval) -> List[Interval]:
        """
        Collect all intervals required by strategies plus the primary interval.
        
        Scans all strategies for their declared `timeframes` attribute and
        combines them with the primary interval to determine all data that
        needs to be loaded.
        
        Args:
            primary_interval: The interval that drives the event loop
            
        Returns:
            List of unique Interval values needed for the backtest
        """
        intervals = {primary_interval}
        
        for strategy in self.strategies:
            if hasattr(strategy, 'timeframes') and strategy.timeframes:
                for tf in strategy.timeframes:
                    intervals.add(tf)
                    
        interval_list = list(intervals)
        logger.info(f"Required intervals: {[i.value for i in interval_list]}")
        return interval_list

    def _load_data(
        self,
        symbols: List[str],
        exchange: str,
        start_date: str,
        end_date: str,
        interval: Interval
    ):
        """
        Load and align data for all symbols across all required timeframes.

        Loads data for the primary interval and any additional intervals
        requested by strategies. Data is stored in nested structure:
        {symbol: {interval: DataFrame}}

        Args:
            symbols: List of symbols
            exchange: Exchange name
            start_date: Start date string
            end_date: End date string
            interval: Primary data interval (passed to run())
        """
        # Determine primary interval (from config or parameter)
        self.primary_interval = self.config.primary_interval or interval
        
        # Collect all intervals needed (primary + strategy-requested)
        self.all_intervals = self._collect_required_intervals(self.primary_interval)
        
        logger.info(f"Loading data for {len(symbols)} symbols across {len(self.all_intervals)} timeframes...")

        # Initialize nested data cache: {symbol: {interval: df}}
        self.data_cache = {symbol: {} for symbol in symbols}
        
        # Load data for each interval and symbol combination
        for tf in self.all_intervals:
            logger.info(f"Loading {tf.value} data...")
            
            for symbol in symbols:
                try:
                    df = self.data_orchestrator.get_data(
                        symbol=symbol,
                        exchange=exchange,
                        start_date=start_date,
                        end_date=end_date,
                        interval=tf
                    )

                    if df is None or df.height == 0:
                        logger.warning(f"No {tf.value} data available for {symbol}")
                        continue

                    self.data_cache[symbol][tf] = df
                    logger.debug(f"Loaded {df.height} {tf.value} bars for {symbol}")

                except Exception as e:
                    logger.error(f"Error loading {tf.value} data for {symbol}: {e}")

        # Check if we have any data for the primary interval
        symbols_with_primary_data = [
            s for s in symbols 
            if self.primary_interval in self.data_cache.get(s, {})
        ]
        
        if not symbols_with_primary_data:
            raise ValueError(f"No data loaded for primary interval {self.primary_interval.value}")

        # Log summary
        for symbol in symbols:
            intervals_loaded = list(self.data_cache.get(symbol, {}).keys())
            if intervals_loaded:
                interval_str = ", ".join(i.value for i in intervals_loaded)
                logger.info(f"{symbol}: loaded [{interval_str}]")

        # Align timestamps using PRIMARY interval only
        self._align_timestamps()

        logger.info(
            f"Data loaded successfully: {len(self.aligned_timestamps)} "
            f"aligned timestamps (primary: {self.primary_interval.value})"
        )

    def _align_timestamps(self):
        """
        Create aligned timestamp list from primary interval data.

        Uses union of all timestamps from the PRIMARY interval only.
        Higher timeframe data is accessed by looking up the appropriate bar
        for each primary timestamp.
        
        All data is in Polars format at this point.
        """
        all_timestamps = set()

        # Iterate through all symbols, using PRIMARY interval data for alignment
        for symbol, interval_data in self.data_cache.items():
            if self.primary_interval in interval_data:
                df = interval_data[self.primary_interval]
                # Polars DataFrame (uses 'datetime' column from DataOrchestrator)
                all_timestamps.update(df['datetime'].to_list())

        # Convert to sorted list
        self.aligned_timestamps = sorted(all_timestamps)

        logger.info(
            f"Aligned {len(self.aligned_timestamps)} unique timestamps "
            f"from {self.primary_interval.value} data"
        )

    def _run_event_loop(self):
        """
        Main event loop - processes each bar chronologically with rich progress display.

        For each timestamp:
        1. Call on_bar_start hook (if configured)
        2. Create StrategyContext
        3. Get signals from all strategies
        4. Convert signals to orders
        5. Execute orders with risk checks
        6. Update portfolio prices and record equity
        7. Calculate risk metrics (periodically)
        8. Call on_bar_end hook (if configured)
        """
        logger.info("Starting event loop...")

        total_bars = len(self.aligned_timestamps)

        # Use rich progress bar if enabled
        if self.config.show_progress:
            self._run_event_loop_with_progress(total_bars)
        else:
            self._run_event_loop_simple(total_bars)

        logger.info(f"Event loop completed: processed {total_bars} bars")

    def _run_event_loop_simple(self, total_bars: int):
        """Event loop without progress bar (for logging/debugging)."""
        for bar_index, timestamp in enumerate[datetime](self.aligned_timestamps):
            self._process_bar(bar_index, timestamp, total_bars)

            # Log progress periodically
            if (bar_index + 1) % 100 == 0 or bar_index == total_bars - 1:
                progress = (bar_index + 1) / total_bars * 100
                portfolio_value = self.portfolio_manager.get_portfolio_value() if self.portfolio_manager else 0
                logger.info(
                    f"Progress: {progress:.1f}% ({bar_index + 1}/{total_bars} bars), "
                    f"Portfolio Value: Rs {portfolio_value:,.2f}"
                )

    def _run_event_loop_with_progress(self, total_bars: int):
        """Event loop with rich progress bar."""
        try:
            from rich.progress import (
                Progress, BarColumn, TextColumn, TimeRemainingColumn,
                TimeElapsedColumn, MofNCompleteColumn
            )
            from rich.console import Console
            import time

            console = Console()

            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                TextColumn("• {task.fields[pnl]}"),
                console=console,
                expand=False
            ) as progress:

                task = progress.add_task(
                    "[cyan]Backtesting...",
                    total=total_bars,
                    pnl="P&L: Rs 0"
                )

                start_time = time.time()

                for bar_index, timestamp in enumerate(self.aligned_timestamps):
                    self._process_bar(bar_index, timestamp, total_bars)

                    # Update progress bar
                    portfolio_value = self.portfolio_manager.get_portfolio_value() if self.portfolio_manager else 0
                    pnl = portfolio_value - self.config.initial_capital
                    pnl_pct = (pnl / self.config.initial_capital * 100) if self.config.initial_capital > 0 else 0

                    pnl_color = "green" if pnl >= 0 else "red"
                    pnl_str = f"P&L: [bold {pnl_color}]Rs {pnl:,.0f} ({pnl_pct:+.2f}%)[/bold {pnl_color}]"

                    progress.update(task, advance=1, pnl=pnl_str)

                elapsed = time.time() - start_time
                bars_per_sec = total_bars / elapsed if elapsed > 0 else 0

                console.print(f"\n[bold green]✓[/bold green] Backtest completed in {elapsed:.2f}s ({bars_per_sec:.1f} bars/sec)")

        except ImportError:
            logger.warning("rich library not available, falling back to simple progress")
            self._run_event_loop_simple(total_bars)

    def _process_bar(self, bar_index: int, timestamp: datetime, total_bars: int):
        """
        Process a single bar in the event loop.

        Args:
            bar_index: Current bar index
            timestamp: Current timestamp
            total_bars: Total number of bars
        """
        # Create context for current bar
        context = self._create_context(timestamp, bar_index, total_bars)

        # Call on_bar_start hook
        if self.config.on_bar_start is not None:
            try:
                self.config.on_bar_start(context, bar_index)
            except Exception as e:
                logger.error(f"Error in on_bar_start hook: {e}")

        # Check for position exits (stop-loss/targets) BEFORE processing new signals
        self._check_position_exits(context)

        # Process pending orders (check if limit/stop orders should fill)
        self._process_pending_orders(context)

        # Get signals from all strategies
        bar_signals = []
        for strategy in self.strategies:
            try:
                signals = strategy._on_bar_wrapper(context)
                bar_signals.extend(signals)
            except Exception as e:
                logger.error(f"Error in strategy {strategy.name}: {e}")

        # Log signals if configured
        if self.config.log_signals and bar_signals:
            for signal in bar_signals:
                logger.info(
                    f"Signal: {signal.direction.value} {signal.symbol} "
                    f"(strength={signal.strength:.2f}, confidence={signal.confidence:.2f})"
                )

        # Store signals
        self.all_signals.extend(bar_signals)

        # Convert signals to orders and execute
        if bar_signals:
            self._process_signals(bar_signals, context)

        # Update portfolio prices and record equity
        self._update_portfolio_prices(context)

        # Calculate risk metrics (periodically)
        if self.config.enable_risk_checks:
            self._calculate_risk_metrics(bar_index, context)

        # Call on_bar_end hook
        if self.config.on_bar_end is not None:
            try:
                self.config.on_bar_end(context, bar_index)
            except Exception as e:
                logger.error(f"Error in on_bar_end hook: {e}")

    def _create_context(self, timestamp: datetime, bar_index: int, total_bars: int = None) -> StrategyContext:
        """
        Create StrategyContext for a specific bar.

        Args:
            timestamp: Current timestamp
            bar_index: Current bar index
            total_bars: Total number of bars in the backtest

        Returns:
            StrategyContext instance with multi-timeframe data access
        """
        return StrategyContext(
            data_orchestrator=self.data_orchestrator,
            portfolio_manager=self.portfolio_manager,
            current_timestamp=timestamp,
            bar_index=bar_index,
            symbols=self.symbols,
            current_data_cache=self.data_cache,
            primary_interval=self.primary_interval,
            total_bars=total_bars
        )

    def _process_signals(self, signals: List[Signal], context: StrategyContext):
        """
        Convert signals to orders and execute them.

        Args:
            signals: List of signals from strategies
            context: Current StrategyContext
        """
        for signal in signals:
            try:
                order = self._signal_to_order(signal, context)
                if order is not None:
                    self._execute_order_or_queue(order, context)
            except Exception as e:
                logger.error(f"Error processing signal for {signal.symbol}: {e}")

    def _signal_to_order(self, signal: Signal, context: StrategyContext) -> Optional[Order]:
        """
        Convert a Signal to an Order.

        Args:
            signal: Signal from strategy
            context: Current StrategyContext

        Returns:
            Order object or None if signal cannot be converted
        """
        # Get current price
        current_price = context.current_price(signal.symbol)
        if current_price is None:
            logger.warning(f"No price available for {signal.symbol}, skipping signal")
            return None

        # Determine transaction type
        if signal.direction == SignalDirection.BUY:
            action = TransactionType.BUY
        elif signal.direction in (SignalDirection.SELL, SignalDirection.CLOSE):
            action = TransactionType.SELL
        elif signal.direction == SignalDirection.HOLD:
            return None  # No action needed
        else:
            logger.warning(f"Unknown signal direction: {signal.direction}")
            return None

        # Determine quantity
        quantity = self._calculate_quantity(signal, context, current_price)
        if quantity <= 0:
            return None

        # Determine order type and prices
        order_type = OrderType.MARKET  # Default to market orders
        limit_price = None
        stop_price = None

        if signal.order_type == 'LIMIT' and signal.limit_price is not None:
            order_type = OrderType.LIMIT
            limit_price = signal.limit_price
        elif signal.order_type == 'SL' and signal.stop_loss is not None:
            order_type = OrderType.SL
            stop_price = signal.stop_loss
            limit_price = signal.limit_price

        # Create order
        order = Order(
            symbol=signal.symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            timestamp=signal.timestamp,
            limit_price=limit_price,
            stop_price=stop_price,
            position_stop_loss=signal.stop_loss,
            position_target=signal.target_price,
            notes=f"Generated from signal (strength={signal.strength:.2f})"
        )

        return order

    def _calculate_quantity(
        self,
        signal: Signal,
        context: StrategyContext,
        current_price: float
    ) -> int:
        """
        Calculate order quantity based on position sizing rules.

        Integrates PositionSizer component when enabled for sophisticated
        sizing methods (Kelly, risk-based, ATR, etc.).

        Args:
            signal: Trading signal
            context: Current context
            current_price: Current price of the symbol

        Returns:
            Number of shares to trade
        """
        # If signal specifies quantity, use it (strategy override)
        if signal.quantity is not None and signal.quantity > 0:
            return signal.quantity

        # For CLOSE signals, close entire position
        if signal.direction == SignalDirection.CLOSE:
            position = context.position(signal.symbol)
            if position is not None:
                return abs(position.quantity)
            return 0

        portfolio_value = context.portfolio_value()

        # Use PositionSizer if enabled and available
        if self.config.use_position_sizer and self.position_sizer is not None:
            try:
                quantity = self._calculate_quantity_with_sizer(
                    signal, context, current_price, portfolio_value
                )

                # Track position sizing decision for analytics
                self.position_sizing_decisions.append({
                    'timestamp': signal.timestamp,
                    'symbol': signal.symbol,
                    'method': self.config.position_sizing_method,
                    'quantity': quantity,
                    'price': current_price,
                    'signal_strength': signal.strength,
                    'signal_confidence': signal.confidence
                })

                return quantity

            except Exception as e:
                logger.warning(
                    f"Error in PositionSizer for {signal.symbol}: {e}. "
                    f"Falling back to simple sizing."
                )

        # Fallback: Simple position sizing based on max_position_size
        position_value = portfolio_value * self.config.max_position_size
        quantity = int(position_value / current_price)

        return max(quantity, 1)  # At least 1 share

    def _calculate_quantity_with_sizer(
        self,
        signal: Signal,
        context: StrategyContext,
        current_price: float,
        portfolio_value: float
    ) -> int:
        """
        Calculate quantity using PositionSizer component.

        Supports multiple sizing methods: equal, risk_based, kelly,
        volatility_target, atr, fixed_percent, signal_strength.

        Args:
            signal: Trading signal
            context: Current context
            current_price: Current price
            portfolio_value: Total portfolio value

        Returns:
            Calculated quantity
        """
        method = self.config.position_sizing_method
        symbol = signal.symbol

        # Get historical data for volatility/ATR calculations
        history = context.history(symbol, periods=30, include_current=True)

        # Common parameters
        common_params = {
            'symbol': symbol,
            'price': current_price,
            'portfolio_value': portfolio_value
        }

        # Method-specific quantity calculation
        if method == 'equal':
            # Equal dollar amount per position
            percent = self.config.max_position_size
            quantity = self.position_sizer.size_fixed_percent(
                **common_params,
                percent=percent
            )

        elif method == 'fixed_percent':
            # Fixed percentage with signal strength weighting
            percent = self.config.max_position_size * signal.confidence
            quantity = self.position_sizer.size_fixed_percent(
                **common_params,
                percent=percent
            )

        elif method == 'risk_based':
            # Risk-based sizing using stop-loss distance
            stop_distance = self._calculate_stop_distance(signal, current_price, history)
            quantity = self.position_sizer.size_risk_based(
                **common_params,
                stop_distance=stop_distance,
                risk_pct=self.config.risk_per_trade
            )

        elif method == 'atr':
            # ATR-based sizing
            if history is not None and len(history.data) >= 14:
                atr = self._calculate_atr(history, period=14)
                quantity = self.position_sizer.size_atr_based(
                    **common_params,
                    atr=atr,
                    atr_multiplier=2.0,
                    risk_pct=self.config.risk_per_trade
                )
            else:
                # Fallback if insufficient data
                quantity = self.position_sizer.size_fixed_percent(
                    **common_params,
                    percent=self.config.max_position_size
                )

        elif method == 'volatility_target':
            # Target volatility contribution
            if history is not None and len(history.data) >= 20:
                volatility = history.data['close'].std() / current_price
                quantity = self.position_sizer.size_volatility_target(
                    **common_params,
                    asset_volatility=volatility,
                    target_volatility=0.02  # 2% target contribution
                )
            else:
                quantity = self.position_sizer.size_fixed_percent(
                    **common_params,
                    percent=self.config.max_position_size
                )

        elif method == 'kelly':
            # Kelly criterion (requires win rate stats)
            # Use signal confidence as proxy for win probability
            win_rate = signal.confidence
            avg_win = 0.05  # Assume 5% average win
            avg_loss = 0.03  # Assume 3% average loss

            quantity = self.position_sizer.size_kelly(
                **common_params,
                win_rate=win_rate,
                avg_win_pct=avg_win,
                avg_loss_pct=avg_loss,
                fraction=0.5  # Half-Kelly for safety
            )

        elif method == 'signal_strength':
            # Weight by signal strength and confidence
            base_percent = self.config.max_position_size
            adjusted_percent = base_percent * signal.strength * signal.confidence
            quantity = self.position_sizer.size_fixed_percent(
                **common_params,
                percent=adjusted_percent
            )

        else:
            # Default fallback
            quantity = self.position_sizer.size_fixed_percent(
                **common_params,
                percent=self.config.max_position_size
            )

        return quantity

    def _calculate_stop_distance(
        self,
        signal: Signal,
        current_price: float,
        history
    ) -> float:
        """
        Calculate stop-loss distance for risk-based sizing.

        Args:
            signal: Trading signal (may contain stop_loss)
            current_price: Current price
            history: Historical price data

        Returns:
            Stop distance in currency units
        """
        # If signal specifies stop loss, use it
        if signal.stop_loss is not None and signal.stop_loss > 0:
            return abs(current_price - signal.stop_loss)

        # Otherwise use ATR-based stop (2x ATR)
        if history is not None and len(history.data) >= 14:
            atr = self._calculate_atr(history, period=14)
            return 2.0 * atr

        # Default: 2% of price
        return current_price * 0.02

    def _calculate_atr(self, history, period: int = 14) -> float:
        """
        Calculate Average True Range using Polars.

        Args:
            history: HistoricalWindow with OHLC data
            period: ATR period

        Returns:
            ATR value
        """
        try:
            df = history.data  # Now returns Polars DataFrame

            # True Range calculation using Polars
            df_with_tr = df.select([
                pl.col('high'),
                pl.col('low'),
                pl.col('close'),
                # TR1: High - Low
                (pl.col('high') - pl.col('low')).alias('tr1'),
                # TR2: |High - Previous Close|
                (pl.col('high') - pl.col('close').shift(1)).abs().alias('tr2'),
                # TR3: |Low - Previous Close|
                (pl.col('low') - pl.col('close').shift(1)).abs().alias('tr3')
            ])

            # Calculate True Range as max of tr1, tr2, tr3
            df_with_atr = df_with_tr.select([
                pl.max_horizontal('tr1', 'tr2', 'tr3').alias('tr')
            ])

            # Calculate ATR as rolling mean of TR
            atr_series = df_with_atr.select(
                pl.col('tr').rolling_mean(window_size=period)
            )

            # Get last value
            atr_value = atr_series[-1, 'tr']

            return float(atr_value) if atr_value is not None else 0.0

        except Exception as e:
            logger.debug(f"Error calculating ATR: {e}")
            return 0.0

    def _execute_order(self, order: Order, context: StrategyContext):
        """
        Execute order through portfolio manager with risk validation.

        Performs pre-order risk checks when risk management is enabled.
        Handles violations according to configured risk_check_mode:
        - 'block': Reject order if violations detected
        - 'warn': Log warnings but execute order
        - 'log': Silent logging only

        Args:
            order: Order to execute
            context: Current context
        """
        current_price = context.current_price(order.symbol)
        if current_price is None:
            logger.warning(f"Cannot execute order for {order.symbol}: no price")
            return

        # Pre-order risk checks
        if self.config.enable_risk_checks and self.risk_monitor is not None:
            violations = self._check_order_risk(order, current_price, context)

            if violations:
                # Track all violations
                self.risk_events.extend(violations)

                # Trigger callback if configured
                if self.config.on_risk_violation is not None:
                    try:
                        self.config.on_risk_violation(violations, order, context)
                    except Exception as e:
                        logger.error(f"Error in on_risk_violation callback: {e}")

                # Handle according to risk check mode
                if self.config.risk_check_mode == 'block':
                    # Reject order
                    critical_violations = [v for v in violations if v.alert_level == RiskAlertLevel.CRITICAL]
                    error_violations = [v for v in violations if v.alert_level == RiskAlertLevel.ERROR]

                    if critical_violations or error_violations:
                        logger.warning(
                            f"Order blocked due to {len(critical_violations + error_violations)} "
                            f"risk violation(s): {order.symbol}"
                        )
                        for v in critical_violations + error_violations:
                            logger.warning(f"  - {v.message}")
                        return  # Don't execute order

                elif self.config.risk_check_mode == 'warn':
                    # Log warnings but continue
                    for v in violations:
                        if v.alert_level == RiskAlertLevel.CRITICAL:
                            logger.error(f"Risk violation: {v.message}")
                        elif v.alert_level == RiskAlertLevel.ERROR:
                            logger.warning(f"Risk violation: {v.message}")

                # 'log' mode: silent logging (violations already tracked)

        try:
            # Process order through portfolio manager
            transaction = self.portfolio_manager.process_order(
                order=order,
                current_price=current_price,
                timestamp=context.current_time
            )

            if transaction is not None:
                self.all_orders.append(order)
                logger.debug(
                    f"Order executed: {order.action.value} {order.quantity} "
                    f"{order.symbol} @ Rs {current_price:.2f}"
                )
            else:
                logger.debug(f"Order not executed: {order.symbol}")

        except Exception as e:
            logger.error(f"Error executing order for {order.symbol}: {e}")

    def _execute_order_or_queue(self, order: Order, context: StrategyContext):
        """
        Execute market orders immediately or add limit/stop orders to pending queue.

        Args:
            order: Order to process
            context: Current strategy context
        """
        # Market orders execute immediately
        if order.order_type == OrderType.MARKET:
            self._execute_order(order, context)
        else:
            # Limit and stop orders go to pending queue
            order.status = OrderStatus.OPEN
            self.pending_orders.append(order)
            logger.debug(
                f"Order queued: {order.order_type.value} {order.action.value} "
                f"{order.quantity} {order.symbol}"
            )

    def _calculate_order_fill_price(self, order: Order, bar) -> Optional[float]:
        """
        Calculate realistic fill price for a pending order based on bar data.

        Conservative approach: Assume limit price fill, or worse if gap occurs.

        Args:
            order: The pending order
            bar: Current OHLC bar data

        Returns:
            Fill price if order should execute, None otherwise
        """
        if order.order_type == OrderType.LIMIT:
            if order.action == TransactionType.BUY:
                # Limit buy: Fill if price drops to or below limit
                if bar.low <= order.limit_price:
                    # Conservative: Use limit price (don't benefit from lower prices)
                    return order.limit_price
            else:  # SELL
                # Limit sell: Fill if price rises to or above limit
                if bar.high >= order.limit_price:
                    # Conservative: Use limit price (don't benefit from higher prices)
                    return order.limit_price

        elif order.order_type in (OrderType.SL, OrderType.SL_M):
            if order.action == TransactionType.BUY:
                # Stop buy: Trigger if price rises to or above stop
                if bar.high >= order.stop_price:
                    if order.order_type == OrderType.SL and order.limit_price:
                        # SL order: Use limit price after stop is hit
                        return order.limit_price
                    else:
                        # SL-M order: Fill at stop price (market after trigger)
                        return order.stop_price
            else:  # SELL
                # Stop sell: Trigger if price drops to or below stop
                if bar.low <= order.stop_price:
                    if order.order_type == OrderType.SL and order.limit_price:
                        # SL order: Use limit price after stop is hit
                        return order.limit_price
                    else:
                        # SL-M order: Fill at stop price (market after trigger)
                        return order.stop_price

        return None  # Order not filled this bar

    def _process_pending_orders(self, context: StrategyContext):
        """
        Check pending orders and execute if price conditions are met.

        Uses current bar's OHLC data to determine if orders should trigger.
        Conservative fill simulation: limit orders fill at limit price, not better.

        Args:
            context: Current strategy context
        """
        orders_to_remove = []

        for order in self.pending_orders:
            bar = context.current_bar(order.symbol)
            if bar is None:
                continue

            # Calculate fill price (None if order doesn't fill)
            execution_price = self._calculate_order_fill_price(order, bar)

            if execution_price is not None:
                # Execute the order at the determined price
                try:
                    transaction = self.portfolio_manager.process_order(
                        order=order,
                        current_price=execution_price,
                        timestamp=context.current_time
                    )

                    if transaction is not None:
                        order.status = OrderStatus.FILLED
                        self.all_orders.append(order)
                        logger.debug(
                            f"Pending order filled: {order.order_type.value} {order.action.value} "
                            f"{order.quantity} {order.symbol} @ Rs {execution_price:.2f}"
                        )

                    orders_to_remove.append(order)

                except Exception as e:
                    logger.error(f"Error executing pending order for {order.symbol}: {e}")
                    # Keep order in queue on error (don't remove)
                    # orders_to_remove.append(order)

        # Remove successfully executed orders from pending queue
        for order in orders_to_remove:
            self.pending_orders.remove(order)

    def _check_position_exits(self, context: StrategyContext):
        """
        Check all positions for stop-loss or target hits and generate exit orders.

        Supports both LONG and SHORT positions with appropriate exit logic:
        - LONG: Stop when price drops, target when price rises
        - SHORT: Stop when price rises, target when price drops

        Args:
            context: Current strategy context
        """
        exit_orders = []

        for symbol, position in list(self.portfolio_manager.positions.items()):
            bar = context.current_bar(symbol)
            if bar is None:
                continue

            # Skip if no exit levels defined
            if position.stop_loss_price is None and position.target_price is None:
                continue

            # Determine execution price if exits are hit
            # Use the actual stop/target price, not the close price
            stop_triggered = False
            target_triggered = False
            execution_price = None

            if position.is_long:
                # LONG POSITION EXITS
                # Check stop-loss: exit when price DROPS to stop level
                if position.stop_loss_price is not None and bar.low <= position.stop_loss_price:
                    stop_triggered = True
                    # Conservative: assume fill at stop price (or open if gap down)
                    if bar.open < position.stop_loss_price:
                        execution_price = bar.open  # Gap down - filled at open
                    else:
                        execution_price = position.stop_loss_price  # Normal stop fill

                # Check target: exit when price RISES to target level
                if position.target_price is not None and bar.high >= position.target_price:
                    target_triggered = True
                    # Conservative: assume fill at target price (or open if gap up)
                    if bar.open > position.target_price:
                        execution_price = bar.open  # Gap up - filled at open
                    else:
                        execution_price = position.target_price  # Normal target fill

            else:  # position.is_short
                # SHORT POSITION EXITS
                # Check stop-loss: exit when price RISES to stop level (bad for shorts!)
                if position.stop_loss_price is not None and bar.high >= position.stop_loss_price:
                    stop_triggered = True
                    # Conservative: assume fill at stop price (or open if gap up)
                    if bar.open > position.stop_loss_price:
                        execution_price = bar.open  # Gap up - filled at open
                    else:
                        execution_price = position.stop_loss_price  # Normal stop fill

                # Check target: exit when price DROPS to target level (good for shorts!)
                if position.target_price is not None and bar.low <= position.target_price:
                    target_triggered = True
                    # Conservative: assume fill at target price (or open if gap down)
                    if bar.open < position.target_price:
                        execution_price = bar.open  # Gap down - filled at open
                    else:
                        execution_price = position.target_price  # Normal target fill

            # Priority: Stop-loss takes precedence over target
            # (if both triggered in same bar, we assume stop hit first)
            if stop_triggered:
                # Exit action depends on position direction
                exit_action = TransactionType.SELL if position.is_long else TransactionType.BUY
                position_type = "LONG" if position.is_long else "SHORT"

                exit_order = Order(
                    symbol=symbol,
                    action=exit_action,
                    quantity=abs(position.quantity),  # Always use positive quantity
                    order_type=OrderType.MARKET,
                    timestamp=context.current_time,
                    notes=f"Stop-loss exit {position_type} @ Rs {position.stop_loss_price:.2f} (filled @ Rs {execution_price:.2f})"
                )
                exit_orders.append((exit_order, execution_price))
                logger.info(
                    f"Stop-loss triggered for {position_type} {symbol}: "
                    f"stop={position.stop_loss_price:.2f}, fill={execution_price:.2f}"
                )
            elif target_triggered:
                # Exit action depends on position direction
                exit_action = TransactionType.SELL if position.is_long else TransactionType.BUY
                position_type = "LONG" if position.is_long else "SHORT"

                exit_order = Order(
                    symbol=symbol,
                    action=exit_action,
                    quantity=abs(position.quantity),  # Always use positive quantity
                    order_type=OrderType.MARKET,
                    timestamp=context.current_time,
                    notes=f"Target exit {position_type} @ Rs {position.target_price:.2f} (filled @ Rs {execution_price:.2f})"
                )
                exit_orders.append((exit_order, execution_price))
                logger.info(
                    f"Target reached for {position_type} {symbol}: "
                    f"target={position.target_price:.2f}, fill={execution_price:.2f}"
                )

        # Execute all exit orders at their specific prices
        for exit_order, execution_price in exit_orders:
            try:
                transaction = self.portfolio_manager.process_order(
                    order=exit_order,
                    current_price=execution_price,
                    timestamp=context.current_time
                )
                if transaction is not None:
                    exit_order.status = OrderStatus.FILLED
                    self.all_orders.append(exit_order)
            except Exception as e:
                logger.error(f"Error executing exit order for {exit_order.symbol}: {e}")

    def _check_order_risk(
        self,
        order: Order,
        current_price: float,
        context: StrategyContext
    ) -> List[RiskEvent]:
        """
        Check if proposed order would violate risk limits.

        Args:
            order: Proposed order
            current_price: Current price
            context: Current context

        Returns:
            List of RiskEvent violations (empty if no violations)
        """
        violations = []

        if self.risk_monitor is None:
            return violations

        portfolio_value = context.portfolio_value()
        timestamp = context.current_time

        # Calculate proposed position value after order
        order_value = order.quantity * current_price
        current_position = context.position(order.symbol)
        current_position_value = 0.0

        if current_position is not None:
            current_position_value = abs(current_position.quantity) * current_price

        # New position value after order
        if order.action == TransactionType.BUY:
            new_position_value = current_position_value + order_value
        else:  # SELL
            new_position_value = max(0, current_position_value - order_value)

        # Check position limits
        position_violations = self.risk_monitor.check_position_limits(
            symbol=order.symbol,
            position_value=new_position_value,
            portfolio_value=portfolio_value,
            timestamp=timestamp
        )
        violations.extend(position_violations)

        # Check portfolio leverage (if order increases exposure)
        if order.action == TransactionType.BUY:
            # Calculate new total positions value
            current_positions_value = sum(
                abs(pos.quantity) * context.current_price(pos.symbol)
                for pos in context.positions().values()
                if context.current_price(pos.symbol) is not None
            )
            new_positions_value = current_positions_value + order_value

            leverage_violations = self.risk_monitor.check_portfolio_limits(
                portfolio_value=portfolio_value,
                positions_value=new_positions_value,
                cash=context.cash(),
                timestamp=timestamp
            )
            violations.extend(leverage_violations)

        # Check concentration if this would create/increase position
        if new_position_value > current_position_value:
            # Build positions dict with proposed change
            positions = {}
            for pos in context.positions().values():
                price = context.current_price(pos.symbol)
                if price is not None:
                    positions[pos.symbol] = abs(pos.quantity) * price

            # Update with proposed position
            positions[order.symbol] = new_position_value

            concentration_violations = self.risk_monitor.check_concentration(
                positions=positions,
                portfolio_value=portfolio_value,
                timestamp=timestamp
            )
            violations.extend(concentration_violations)

        return violations

    def _update_portfolio_prices(self, context: StrategyContext):
        """
        Update portfolio with current prices and record equity point.

        Args:
            context: Current context
        """
        # Build price dictionary
        current_prices = {}
        for symbol in self.symbols:
            price = context.current_price(symbol)
            if price is not None:
                current_prices[symbol] = price

        # Update prices in portfolio manager
        if current_prices:
            self.portfolio_manager.update_prices(current_prices)

        # Record equity point
        self.portfolio_manager.record_equity_point(
            timestamp=context.current_time,
            price_dict=current_prices
        )

    def _should_calculate_risk_metrics(self, bar_index: int) -> bool:
        """
        Determine if risk metrics should be calculated for this bar.

        Args:
            bar_index: Current bar index

        Returns:
            True if metrics should be calculated, False otherwise
        """
        if not self.config.enable_risk_checks or self.risk_calculator is None:
            return False

        # Check frequency
        if self.config.risk_calc_frequency > 0:
            if bar_index % self.config.risk_calc_frequency != 0:
                return False

        # Need sufficient history
        if len(self.portfolio_manager.equity_curve) < 20:
            return False

        return True

    def _get_portfolio_returns(self) -> Optional[pd.Series]:
        """
        Extract portfolio returns from equity curve using Polars.

        Returns:
            Pandas Series of returns for compatibility with risk calculator,
            or None if insufficient data
        """
        equity_values = [ep.total_value for ep in self.portfolio_manager.equity_curve]

        # Use Polars for calculation
        pl_series = pl.Series('equity', equity_values)
        returns_pl = pl_series.pct_change()

        # Convert to pandas for compatibility with risk calculator
        returns = returns_pl.to_pandas().dropna()

        if len(returns) < 10:
            return None

        return returns

    def _calculate_volatility_metrics(self, returns: pd.Series) -> float:
        """
        Calculate portfolio volatility.

        Args:
            returns: Portfolio returns series

        Returns:
            Portfolio volatility (annualized)
        """
        return self.risk_calculator.calculate_portfolio_volatility(
            positions={},  # Simplified - would need returns for each position
            returns=returns.to_frame('returns')
        )

    def _calculate_var_cvar(self, returns: pd.Series, portfolio_value: float) -> Tuple[float, float]:
        """
        Calculate Value at Risk and Conditional VaR.

        Args:
            returns: Portfolio returns series
            portfolio_value: Current portfolio value

        Returns:
            Tuple of (VaR_95, CVaR_95) in dollar amounts
        """
        var_95 = self.risk_calculator.calculate_var(
            returns=returns,
            confidence_level=0.95,
            method='historical'
        ) * portfolio_value

        cvar_95 = self.risk_calculator.calculate_cvar(
            returns=returns,
            confidence_level=0.95
        ) * portfolio_value

        return var_95, cvar_95

    def _calculate_drawdown_metrics_dict(self) -> Dict[str, float]:
        """
        Calculate drawdown metrics from equity curve.

        Returns:
            Dictionary with drawdown metrics
        """
        equity_values = [ep.total_value for ep in self.portfolio_manager.equity_curve]
        # Use Polars Series for calculation (risk_calculator accepts both pandas and polars)
        return self.risk_calculator.calculate_drawdown_metrics(
            equity_curve=pl.Series('equity', equity_values)
        )

    def _calculate_performance_ratios(
        self,
        returns: pd.Series,
        portfolio_value: float,
        max_drawdown: float
    ) -> Tuple[float, float, float]:
        """
        Calculate Sharpe, Sortino, and Calmar ratios.

        Args:
            returns: Portfolio returns series
            portfolio_value: Current portfolio value
            max_drawdown: Maximum drawdown

        Returns:
            Tuple of (sharpe_ratio, sortino_ratio, calmar_ratio)
        """
        sharpe = self.risk_calculator.calculate_sharpe_ratio(returns)
        sortino = self.risk_calculator.calculate_sortino_ratio(returns)

        total_return = (portfolio_value - self.config.initial_capital) / self.config.initial_capital
        calmar = total_return / max_drawdown if max_drawdown > 0 else 0.0

        return sharpe, sortino, calmar

    def _calculate_position_risks(
        self,
        context: StrategyContext,
        portfolio_value: float,
        portfolio_volatility: float,
        portfolio_var_95: float,
        portfolio_cvar_95: float
    ) -> Dict[str, PositionRisk]:
        """
        Calculate risk metrics for each position.

        Args:
            context: Current strategy context
            portfolio_value: Current portfolio value
            portfolio_volatility: Portfolio volatility
            portfolio_var_95: Portfolio VaR
            portfolio_cvar_95: Portfolio CVaR

        Returns:
            Dictionary mapping symbol to PositionRisk
        """
        position_risks = {}
        positions = context.positions()

        for symbol, pos in positions.items():
            price = context.current_price(symbol)
            if price is None:
                continue

            market_value = abs(pos.quantity) * price
            weight = market_value / portfolio_value if portfolio_value > 0 else 0.0

            # Simplified position risk (would need historical returns for full calculation)
            position_risks[symbol] = PositionRisk(
                symbol=symbol,
                quantity=pos.quantity,
                market_value=market_value,
                weight=weight,
                volatility=portfolio_volatility,  # Simplified
                var_95=portfolio_var_95 * weight,  # Proportional approximation
                cvar_95=portfolio_cvar_95 * weight,
                beta=1.0,  # Would need market returns to calculate
                marginal_var=0.0,  # Requires covariance matrix
                component_var=0.0,
                risk_contribution_pct=weight * 100,  # Simplified
                avg_correlation=0.0,  # Would need returns correlation
                max_correlation=0.0,
                correlated_symbols=[]
            )

        return position_risks

    def _build_risk_metrics(
        self,
        timestamp,
        portfolio_value: float,
        cash: float,
        positions_value: float,
        leverage: float,
        volatility: float,
        var_95: float,
        cvar_95: float,
        drawdown_metrics: Dict[str, float],
        sharpe: float,
        sortino: float,
        calmar: float,
        position_risks: Dict[str, PositionRisk]
    ) -> RiskMetrics:
        """
        Build the RiskMetrics object from calculated components.

        Returns:
            Complete RiskMetrics snapshot
        """
        return RiskMetrics(
            timestamp=timestamp,
            portfolio_value=portfolio_value,
            cash=cash,
            positions_value=positions_value,
            leverage=leverage,
            portfolio_volatility=volatility,
            portfolio_var_95=var_95,
            portfolio_cvar_95=cvar_95,
            current_drawdown=drawdown_metrics.get('current_drawdown', 0.0),
            max_drawdown=drawdown_metrics.get('max_drawdown', 0.0),
            avg_drawdown=drawdown_metrics.get('average_drawdown', 0.0),
            cdar_95=drawdown_metrics.get('cdar_95', 0.0),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            position_risks=position_risks,
            correlation_matrix=None,  # Would need historical returns
            sector_exposure={}  # Would need sector mapping
        )

    def _calculate_risk_metrics(
        self,
        bar_index: int,
        context: StrategyContext
    ) -> Optional[RiskMetrics]:
        """
        Calculate comprehensive risk metrics for current portfolio state.

        This is called periodically based on risk_calc_frequency configuration.
        Computationally expensive, so should not be called every bar unless necessary.

        REFACTORED: Broken into smaller helper methods for better maintainability.

        Args:
            bar_index: Current bar index
            context: Current strategy context

        Returns:
            RiskMetrics snapshot or None if calculation skipped/failed
        """
        # Check if we should calculate
        if not self._should_calculate_risk_metrics(bar_index):
            return None

        try:
            # Get current portfolio state
            timestamp = context.current_time
            portfolio_value = context.portfolio_value()
            cash = context.cash()
            positions = context.positions()

            # Calculate portfolio returns
            returns = self._get_portfolio_returns()
            if returns is None:
                return None

            # Calculate positions value and leverage
            positions_value = sum(
                abs(pos.quantity) * context.current_price(pos.symbol)
                for pos in positions.values()
                if context.current_price(pos.symbol) is not None
            )
            leverage = positions_value / portfolio_value if portfolio_value > 0 else 0.0

            # Calculate all risk metrics using helper methods
            volatility = self._calculate_volatility_metrics(returns)
            var_95, cvar_95 = self._calculate_var_cvar(returns, portfolio_value)
            drawdown_metrics = self._calculate_drawdown_metrics_dict()
            max_drawdown = drawdown_metrics.get('max_drawdown', 0.0)
            sharpe, sortino, calmar = self._calculate_performance_ratios(
                returns, portfolio_value, max_drawdown
            )
            position_risks = self._calculate_position_risks(
                context, portfolio_value, volatility, var_95, cvar_95
            )

            # Build risk metrics object
            risk_metrics = self._build_risk_metrics(
                timestamp=timestamp,
                portfolio_value=portfolio_value,
                cash=cash,
                positions_value=positions_value,
                leverage=leverage,
                volatility=volatility,
                var_95=var_95,
                cvar_95=cvar_95,
                drawdown_metrics=drawdown_metrics,
                sharpe=sharpe,
                sortino=sortino,
                calmar=calmar,
                position_risks=position_risks
            )

            # Check against risk limits
            if self.risk_monitor is not None:
                violations = self.risk_monitor.monitor_risk(risk_metrics)
                self.risk_events.extend(violations)

                # Update risk metrics with violations
                risk_metrics = RiskMetrics(
                    **{**risk_metrics.__dict__, 'violations': violations}
                )

            # Store in history
            self.risk_metrics_history.append(risk_metrics)

            logger.debug(
                f"Risk metrics calculated: Sharpe={sharpe:.3f}, "
                f"MaxDD={max_drawdown*100:.2f}%, VaR={var_95:,.0f}"
            )

            return risk_metrics

        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
            return None

    def _generate_results(self, start_date: str, end_date: str) -> BacktestResults:
        """
        Generate comprehensive backtest results with enhanced risk analytics.

        Args:
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            BacktestResults object with complete performance and risk metrics
        """
        logger.info("Generating results...")

        # Get final portfolio summary (using primary interval data)
        final_prices = {}
        for symbol, interval_data in self.data_cache.items():
            if self.primary_interval in interval_data:
                df = interval_data[self.primary_interval]
                if df.height > 0:
                    final_prices[symbol] = df['close'][-1]

        summary = self.portfolio_manager.get_summary(price_dict=final_prices)

        # Build equity curve DataFrame (Polars format)
        equity_data = []
        for equity_point in self.portfolio_manager.equity_curve:
            equity_data.append({
                'timestamp': equity_point.timestamp,
                'cash': equity_point.cash,
                'positions_value': equity_point.positions_value,
                'total_value': equity_point.total_value
            })

        # Create Polars DataFrame for better performance
        equity_df = create_equity_curve_polars(equity_data)

        # Calculate performance metrics using Polars
        metrics = self._calculate_metrics(equity_df, summary)

        # Get final risk metrics or calculate if not already done
        final_risk_metrics = None
        if self.risk_metrics_history:
            final_risk_metrics = self.risk_metrics_history[-1]
        elif self.config.enable_risk_checks and len(self.portfolio_manager.equity_curve) >= 20:
            # Calculate final risk metrics
            logger.info("Calculating final risk metrics...")
            # Create a dummy context for final calculation
            final_timestamp = self.aligned_timestamps[-1]
            total_bars = len(self.aligned_timestamps)
            final_context = self._create_context(final_timestamp, total_bars - 1, total_bars)
            final_risk_metrics = self._calculate_risk_metrics(len(self.aligned_timestamps) - 1, final_context)

        # Aggregate position sizing statistics
        position_sizing_stats = self._aggregate_position_sizing_stats()

        # Calculate monthly returns
        monthly_returns = self._calculate_monthly_returns(equity_df)

        # Identify drawdown periods
        drawdown_periods = self._identify_drawdown_periods(equity_df)

        # Enhanced trade analysis
        trade_analysis = self._analyze_trades()

        # Create results object
        strategy_names = ", ".join(s.name for s in self.strategies)

        results = BacktestResults(
            strategy_name=strategy_names,
            start_date=self.aligned_timestamps[0],
            end_date=self.aligned_timestamps[-1],
            initial_capital=self.config.initial_capital,
            final_capital=summary['total_value'],
            total_return=((summary['total_value'] - self.config.initial_capital) /
                         self.config.initial_capital * 100),
            total_pnl=summary['total_value'] - self.config.initial_capital,
            transactions=self.portfolio_manager.transactions.copy(),
            equity_curve=equity_df,  # Now Polars DataFrame
            metrics=metrics,
            signals=self.all_signals,
            config=self.config,
            # New enhanced fields
            risk_metrics_history=self.risk_metrics_history,
            final_risk_metrics=final_risk_metrics,
            risk_events=self.risk_events,
            position_sizing_stats=position_sizing_stats,
            monthly_returns=monthly_returns,
            drawdown_periods=drawdown_periods,
            trade_analysis=trade_analysis
        )

        logger.info("Results generated successfully")
        return results

    def _aggregate_position_sizing_stats(self) -> Dict:
        """
        Aggregate position sizing decision statistics.

        Returns:
            Dictionary with position sizing analytics
        """
        if not self.position_sizing_decisions:
            return {}

        decisions = self.position_sizing_decisions

        return {
            'total_decisions': len(decisions),
            'avg_quantity': np.mean([d['quantity'] for d in decisions]),
            'median_quantity': np.median([d['quantity'] for d in decisions]),
            'avg_signal_strength': np.mean([d['signal_strength'] for d in decisions]),
            'avg_signal_confidence': np.mean([d['signal_confidence'] for d in decisions]),
            'method': self.config.position_sizing_method if self.config.use_position_sizer else 'simple'
        }

    def _calculate_monthly_returns(self, equity_df: pl.DataFrame) -> Dict:
        """
        Calculate monthly return breakdown using Polars.

        Args:
            equity_df: Equity curve Polars DataFrame

        Returns:
            Dictionary with monthly returns
        """
        try:
            if equity_df.height == 0:
                return {}

            # Ensure timestamp is datetime type
            df = equity_df.with_columns(
                pl.col('timestamp').cast(pl.Datetime)
            ).sort('timestamp')

            # Group by month and get last value of each month
            monthly_values = df.group_by_dynamic(
                'timestamp',
                every='1mo',
                closed='right'
            ).agg(
                pl.col('total_value').last().alias('value')
            ).sort('timestamp')

            # Calculate percentage changes
            monthly_with_returns = monthly_values.with_columns(
                pl.col('value').pct_change().alias('return')
            ).filter(
                pl.col('return').is_not_null()
            )

            # Convert to dictionary {month: return}
            return {
                str(row['timestamp'].date()): float(row['return'])
                for row in monthly_with_returns.iter_rows(named=True)
            }

        except Exception as e:
            logger.warning(f"Error calculating monthly returns: {e}")
            return {}

    def _identify_drawdown_periods(self, equity_df: pl.DataFrame) -> List[Dict]:
        """
        Identify significant drawdown periods using Polars and numpy.

        Args:
            equity_df: Equity curve Polars DataFrame

        Returns:
            List of drawdown period dictionaries
        """
        try:
            if equity_df.height == 0:
                return []

            # Extract values and timestamps directly from Polars
            values = equity_df['total_value'].to_numpy()
            timestamps = equity_df['timestamp'].to_numpy()

            # Calculate running max and drawdowns using numpy
            running_max = np.maximum.accumulate(values)
            drawdowns = (values - running_max) / running_max

            # Find drawdown periods (threshold: >5%)
            in_drawdown = drawdowns < -0.05
            drawdown_periods = []

            start_idx = None
            for i, is_dd in enumerate(in_drawdown):
                if is_dd and start_idx is None:
                    start_idx = i
                elif not is_dd and start_idx is not None:
                    # End of drawdown period
                    dd_values = drawdowns[start_idx:i]
                    max_dd = dd_values.min()
                    max_dd_idx = start_idx + dd_values.argmin()

                    # Convert timestamps to dates
                    start_ts = timestamps[start_idx]
                    end_ts = timestamps[i-1]
                    max_dd_ts = timestamps[max_dd_idx]

                    # Handle both datetime and date types
                    if hasattr(start_ts, 'date'):
                        start_date = start_ts.date()
                        end_date = end_ts.date()
                        max_dd_date = max_dd_ts.date()
                        duration_days = (end_ts - start_ts).days
                    else:
                        start_date = start_ts
                        end_date = end_ts
                        max_dd_date = max_dd_ts
                        duration_days = (end_ts - start_ts).days if hasattr(end_ts - start_ts, 'days') else 0

                    drawdown_periods.append({
                        'start_date': str(start_date),
                        'end_date': str(end_date),
                        'max_drawdown': float(max_dd),
                        'max_dd_date': str(max_dd_date),
                        'duration_days': int(duration_days)
                    })

                    start_idx = None

            return drawdown_periods

        except Exception as e:
            logger.warning(f"Error identifying drawdown periods: {e}")
            return []

    def _analyze_trades(self) -> Dict:
        """
        Perform detailed trade analysis.

        Returns:
            Dictionary with trade analytics
        """
        transactions = self.portfolio_manager.transactions

        if not transactions:
            return {}

        # Get trade statistics from portfolio manager (already calculated correctly)
        summary = self.portfolio_manager.get_summary()

        return {
            'total_transactions': len(transactions),
            'profitable_trades': summary.get('winning_trades', 0),
            'losing_trades': summary.get('losing_trades', 0),
            'avg_profit': summary.get('avg_win', 0.0),
            'avg_loss': summary.get('avg_loss', 0.0),
            'max_profit': 0.0,  # Would require additional tracking in portfolio manager
            'max_loss': 0.0,  # Would require additional tracking in portfolio manager
            'profit_factor': summary.get('profit_factor', 0.0),
            # Could add more: avg hold time, win/loss streaks, etc.
        }

    def _calculate_metrics(self, equity_df: pl.DataFrame, summary: Dict) -> Dict:
        """
        Calculate performance metrics using Polars.

        Args:
            equity_df: Equity curve Polars DataFrame
            summary: Portfolio summary

        Returns:
            Dictionary of performance metrics
        """
        metrics = {}

        # Basic metrics from summary
        metrics['total_trades'] = summary['total_trades']
        metrics['winning_trades'] = summary['winning_trades']
        metrics['losing_trades'] = summary['losing_trades']
        metrics['win_rate'] = summary['win_rate']
        metrics['profit_factor'] = summary['profit_factor']

        # Equity curve metrics
        if equity_df.height > 0:
            # Calculate returns using Polars
            returns_series = equity_df.select(
                pl.col('total_value').pct_change().alias('returns')
            ).drop_nulls()

            if returns_series.height > 0:
                returns_values = returns_series['returns'].to_numpy()

                # Sharpe ratio (assuming 252 trading days, 0% risk-free rate)
                if len(returns_values) > 0 and returns_values.std() > 0:
                    metrics['sharpe_ratio'] = np.sqrt(252) * returns_values.mean() / returns_values.std()
                else:
                    metrics['sharpe_ratio'] = 0.0

                # Max drawdown using Polars
                cumulative = equity_df['total_value']
                running_max_values = np.maximum.accumulate(cumulative.to_numpy())
                cumulative_values = cumulative.to_numpy()
                drawdown_values = (cumulative_values - running_max_values) / running_max_values
                metrics['max_drawdown'] = abs(drawdown_values.min()) * 100  # As percentage

                # Total return percentage
                first_value = equity_df['total_value'][0]
                last_value = equity_df['total_value'][-1]
                metrics['total_return_pct'] = (
                    (last_value - first_value) / first_value * 100
                )
            else:
                metrics['sharpe_ratio'] = 0.0
                metrics['max_drawdown'] = 0.0
                metrics['total_return_pct'] = 0.0

        return metrics

    def get_strategy_stats(self) -> List[Dict]:
        """
        Get statistics for all strategies.

        Returns:
            List of strategy statistics dictionaries
        """
        return [strategy.get_stats() for strategy in self.strategies]
