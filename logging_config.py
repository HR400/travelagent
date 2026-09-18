"""Production logging infrastructure with structured logging support."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName"
            }:
                log_data[key] = value

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for development environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"{timestamp} [{record.levelname}] {record.name}: {record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: Path | None = None,
    console_output: bool = True,
) -> logging.Logger:
    """
    Configure production logging with optional file output.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json' or 'text')
        log_file: Optional path to log file
        console_output: Whether to output logs to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("travel_agent")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Choose formatter based on format type
    if log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "travel_agent") -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding contextual information to logs."""

    def __init__(self, **kwargs: Any):
        self.context = kwargs
        self.old_context: dict[str, Any] = {}

    def __enter__(self) -> "LogContext":
        self.old_context = getattr(logging.getLogger(), "_log_context", {})
        logging.getLogger().setdefault("_log_context", {}).update(self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        logging.getLogger()._log_context = self.old_context


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_context: Any,
) -> None:
    """Log a message with additional context information."""
    extra = {"context": extra_context}
    logger.log(level, message, extra=extra)
