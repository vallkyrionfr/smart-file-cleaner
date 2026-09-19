"""Graceful signal handling for smart-file-cleaner.

Registers handlers for SIGINT (Ctrl+C) and SIGTERM so that long-running
scans and batch operations can shut down cleanly, flushing any in-flight
history manifests and closing progress bars before exiting.

Usage::

    from smart_file_cleaner.utils.signals import setup_signal_handlers, shutdown_requested

    setup_signal_handlers()

    for path in large_directory_walk():
        if shutdown_requested():
            break
        process(path)
"""

from __future__ import annotations

import signal
import threading
from typing import Callable, List

_shutdown_event = threading.Event()
_cleanup_callbacks: List[Callable[[], None]] = []


def setup_signal_handlers() -> None:
    """Register SIGINT and SIGTERM handlers for graceful shutdown.

    Must be called from the main thread. Safe to call multiple times.
    """
    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except (OSError, ValueError):
        # On Windows, SIGTERM may not be available in all contexts.
        # In non-main threads, signal registration silently fails.
        pass


def register_cleanup(callback: Callable[[], None]) -> None:
    """Register a callback to be invoked on graceful shutdown.

    Args:
        callback: Zero-argument callable (e.g. flush history, close progress bar).
    """
    _cleanup_callbacks.append(callback)


def shutdown_requested() -> bool:
    """Check whether a shutdown signal has been received.

    Returns:
        True if SIGINT or SIGTERM was received, False otherwise.
    """
    return _shutdown_event.is_set()


def _handle_signal(signum: int, frame: object) -> None:
    """Internal signal handler: sets the shutdown event and runs cleanup."""
    _shutdown_event.set()
    for callback in _cleanup_callbacks:
        try:
            callback()
        except Exception:
            pass
    # Re-raise as KeyboardInterrupt so Typer exits cleanly with code 130
    raise KeyboardInterrupt
