"""
Logging setup for the backtesting framework.

Creates dedicated, numbered log files for each backtest run.
Log files are stored in backtester/logs/ with the format:
    log{N}_{YYYY-MM-DD_HH-MM-SS}.log

Example:
    log1_2026-03-10_14-30-00.log
    log2_2026-03-10_15-45-22.log
"""

import logging
from datetime import datetime
from pathlib import Path

# Directory where all backtest logs are saved
LOGS_DIR = Path(__file__).parent.parent / "logs"

_LOG_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"


def _get_next_log_number() -> int:
    """Scan the logs directory and return the next available log number."""
    numbers = (
        int(f.stem.split("_")[0][3:])        # strip leading "log"
        for f in LOGS_DIR.glob("log*.log")
        if f.stem.split("_")[0][3:].isdigit()
    )
    return max(numbers, default=0) + 1


def setup_backtest_logging(level: int = logging.DEBUG) -> str:
    """
    Configure file + console logging for a backtest run.

    Creates a new numbered log file in backtester/logs/ with the
    current timestamp. Also keeps console output at INFO level.

    Args:
        level: Log level written to file (default DEBUG for full detail).

    Returns:
        Absolute path of the created log file.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_number = _get_next_log_number()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = LOGS_DIR / f"log{log_number}_{timestamp}.log"

    root_logger = logging.getLogger()

    # Replace any existing file handler so re-runs get a fresh log file
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(filename, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt=_LOG_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    root_logger.addHandler(file_handler)

    # Add a console handler only if one doesn't already exist
    has_console = any(
        type(h) is logging.StreamHandler          # exact type, not FileHandler subclass
        for h in root_logger.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(fmt=_LOG_FMT, datefmt="%H:%M:%S"))
        root_logger.addHandler(console_handler)

    # Root logger must be at least as permissive as the file handler
    if root_logger.level == logging.NOTSET or root_logger.level > level:
        root_logger.setLevel(level)

    return str(filename)
