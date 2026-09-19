"""Structured logging setup for smart-file-cleaner using structlog.

Usage:
    from smart_file_cleaner.utils.logging import get_logger, setup_logging

    setup_logging(verbose=False, quiet=False, json_output=False)
    log = get_logger(__name__)
    log.info("scan.started", path=str(target_dir), recursive=True)

- All logging goes to stderr (never stdout) so it doesn't pollute piped output.
- verbose=True  → DEBUG level, human-readable colors
- quiet=True    → WARNING level only
- json_output   → structured JSON lines (for CI / log aggregators)
- Default       → INFO level, human-readable
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    import structlog

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    json_output: bool = False,
) -> None:
    """Configure logging for the current process.

    Args:
        verbose: Enable DEBUG-level output with detailed context.
        quiet: Suppress all output below WARNING level.
        json_output: Emit structured JSON log lines instead of human-readable.
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    if not _HAS_STRUCTLOG:
        # Graceful degradation: use stdlib logging
        logging.basicConfig(
            level=level,
            stream=sys.stderr,
            format="%(levelname)s %(name)s %(message)s",
        )
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Return a structlog (or stdlib) logger for the given module name.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A bound logger instance.
    """
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)
