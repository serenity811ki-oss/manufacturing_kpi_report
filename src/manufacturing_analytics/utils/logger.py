"""
logger.py
=========
Centralized logging configuration for the Manufacturing Analytics Platform.

Using Loguru instead of the standard ``logging`` module because it provides:
    * Zero-boilerplate setup (no handler/formatter classes to wire up)
    * Automatic log rotation & retention
    * Built-in colorized console output
    * Structured, readable timestamps and log levels out of the box

Every other module in the project should import ``get_logger`` from here
rather than instantiating its own logger, so that all logs share the same
sinks (console + rotating file) and formatting.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Guard against re-configuring the logger multiple times when this module
# is imported from several places (e.g. notebooks re-running cells).
_CONFIGURED = False


def configure_logging(log_dir: str | Path = "logs", level: str = "INFO") -> None:
    """Configure Loguru sinks for console + rotating file output.

    Parameters
    ----------
    log_dir:
        Directory where log files will be written. Created if missing.
    level:
        Minimum log level to emit (e.g. "DEBUG", "INFO", "WARNING").
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove Loguru's default handler so we control formatting explicitly.
    logger.remove()

    # Console sink — concise, colorized, good for interactive use.
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    # File sink — rotates at 10 MB, keeps 10 days of history, compressed.
    logger.add(
        log_path / "manufacturing_analytics_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,  # thread/process-safe writes
        backtrace=True,
        diagnose=False,  # avoid leaking variable values in prod logs
    )

    _CONFIGURED = True
    logger.debug("Logging configured. Writing logs to: {}", log_path.resolve())


def get_logger(name: str | None = None):
    """Return a Loguru logger instance, configuring sinks on first use.

    Parameters
    ----------
    name:
        Optional context name (typically ``__name__``) bound to log records.
    """
    if not _CONFIGURED:
        configure_logging()
    return logger.bind(module_name=name) if name else logger
