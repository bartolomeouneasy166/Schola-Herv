"""
Rich-based logger for Schola-herv.
Provides a consistent logging interface across all modules.
"""

import logging
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler


def setup_logger(
    name: str = "schola_herv",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """
    Create and configure a logger with Rich formatting.

    Args:
        name:     Logger name (default: ``"schola_herv"``).
        level:    Logging level (default: ``INFO``).
        log_file: Optional path to a log file.  When provided, a
                  :class:`logging.FileHandler` is added alongside the
                  Rich console handler so all messages are persisted.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding multiple handlers if already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Rich handler – nicely formatted console output
    rich_handler = RichHandler(
        rich_tracebacks=True,
        show_time=False,
        show_path=False,
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    # Optional file handler
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    return logger
