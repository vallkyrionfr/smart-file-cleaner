"""Exception hierarchy for smart-file-cleaner.

All domain-specific errors inherit from SmartCleanerError.
The CLI layer catches SmartCleanerError at the top level, renders it
with Rich, and exits with the corresponding exit_code.

Unexpected errors (TypeError, OSError, etc.) bubble up as full
Rich tracebacks for debugging.
"""


class SmartCleanerError(Exception):
    """Base exception for all smart-file-cleaner domain errors.

    Attributes:
        message: Human-readable error description.
        exit_code: Process exit code to use when this error terminates the CLI.
    """

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class UnsafePathError(SmartCleanerError):
    """Raised when an operation targets a protected system directory or root home."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)


class ConfigError(SmartCleanerError):
    """Raised for invalid or unreadable configuration files."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=78)  # EX_CONFIG


class ScanError(SmartCleanerError):
    """Raised when a directory scan encounters an unrecoverable error (e.g. permission denied)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)


class OperationAbortedError(SmartCleanerError):
    """Raised when the user explicitly cancels an operation (Ctrl+C or interactive 'q')."""

    def __init__(self, message: str = "Operation cancelled by user.") -> None:
        super().__init__(message, exit_code=130)  # Standard SIGINT exit code


class HistoryCorruptError(SmartCleanerError):
    """Raised when an undo manifest is missing, unreadable, or structurally invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)


class TrashError(SmartCleanerError):
    """Raised when moving a file to the OS Trash/Recycle Bin fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)
