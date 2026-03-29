"""Strategy base class. Implement init() and on_bar() to define a strategy."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

from backtester.strategy.strategy_context import StrategyContext
from backtester.strategy.signal import Signal

from backtester.data_loader import Interval

logger = logging.getLogger(__name__)


class Strategy(ABC):
    """Base for trading strategies. Implement init() and on_bar()."""

    def __init__(self, name: str = None, timeframes: Optional[List['Interval']] = None, **params):
        """name: strategy id (defaults to class name). timeframes: extra intervals (e.g. [Interval.DAY]). **params: stored in self.params."""
        self.name = name if name is not None else self.__class__.__name__
        self.timeframes = timeframes or []  # Additional timeframes beyond primary
        self.params = params
        self.description = ""

        # Logger for strategy use
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

        # Internal state (not accessible to strategy logic)
        self._initialized = False
        self._bar_count = 0
        self._signal_count = 0

        tf_info = f", timeframes={self.timeframes}" if self.timeframes else ""
        logger.info(f"Created strategy: {self.name} with params: {self.params}{tf_info}")

    @abstractmethod
    def init(self, context: StrategyContext):
        """Called once before first bar. Use for validation, pre-calc, setup."""
        pass

    @abstractmethod
    def on_bar(self, context: StrategyContext) -> List[Signal]:
        """Called each bar. Return list of Signal objects. Read-only context; no direct portfolio changes."""
        pass

    def _on_bar_wrapper(self, context: StrategyContext) -> List[Signal]:
        """Orchestrator calls this. Runs init on first bar, then on_bar. Do not override."""
        # Initialize on first call
        if not self._initialized:
            self.init(context)
            self._initialized = True
            logger.info(f"Strategy {self.name} initialized successfully")

        # Increment bar counter
        self._bar_count += 1

        signals = self.on_bar(context)

        if not isinstance(signals, list):
            raise TypeError(f"Strategy {self.name} returned {type(signals).__name__}, expected list")

        self._signal_count += len(signals)

        if self._bar_count % 1000 == 0:
            logger.info(
                f"Strategy {self.name}: processed {self._bar_count} bars, "
                f"generated {self._signal_count} signals"
            )

        return signals

    def get_stats(self) -> Dict[str, Any]:
        """Returns name, bars_processed, signals_generated, params, timeframes."""
        return {
            'name': self.name,
            'description': self.description,
            'bars_processed': self._bar_count,
            'signals_generated': self._signal_count,
            'params': self.params.copy(),
            'timeframes': [tf.value if hasattr(tf, 'value') else str(tf) for tf in self.timeframes]
        }

    def __repr__(self) -> str:
        """Debug repr."""
        tf_str = f", timeframes={len(self.timeframes)}" if self.timeframes else ""
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"params={self.params}, "
            f"bars={self._bar_count}, "
            f"signals={self._signal_count}{tf_str})"
        )

    def __str__(self) -> str:
        """Human-readable str."""
        param_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({param_str})"
