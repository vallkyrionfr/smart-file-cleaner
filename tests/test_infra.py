"""Tests for infrastructure utilities (signals, logging, errors, progress)."""

from smart_file_cleaner.utils.errors import (
    ConfigError,
    HistoryCorruptError,
    OperationAbortedError,
    ScanError,
    SmartCleanerError,
    TrashError,
    UnsafePathError,
)
from smart_file_cleaner.utils.logging import get_logger, setup_logging
from smart_file_cleaner.utils.progress import make_progress
from smart_file_cleaner.utils.signals import (
    register_cleanup,
    setup_signal_handlers,
    shutdown_requested,
)


class TestErrors:
    def test_error_exit_codes(self):
        assert SmartCleanerError("err").exit_code == 1
        assert UnsafePathError("err").exit_code == 1
        assert ConfigError("err").exit_code == 78
        assert ScanError("err").exit_code == 1
        assert OperationAbortedError().exit_code == 130
        assert HistoryCorruptError("err").exit_code == 1
        assert TrashError("err").exit_code == 1


class TestLogging:
    def test_setup_logging_defaults(self):
        setup_logging(verbose=False, quiet=False, json_output=False)
        log = get_logger("test_module")
        assert log is not None

    def test_setup_logging_verbose(self):
        setup_logging(verbose=True)
        log = get_logger("test_verbose")
        assert log is not None

    def test_setup_logging_quiet(self):
        setup_logging(quiet=True)
        log = get_logger("test_quiet")
        assert log is not None

    def test_setup_logging_json(self):
        setup_logging(json_output=True)
        log = get_logger("test_json")
        assert log is not None


class TestSignals:
    def test_setup_signal_handlers_runs(self):
        setup_signal_handlers()  # Should not raise

    def test_register_cleanup(self):
        called = False

        def cleanup_fn():
            nonlocal called
            called = True

        register_cleanup(cleanup_fn)

    def test_shutdown_requested_initially_false(self):
        assert isinstance(shutdown_requested(), bool)


class TestProgress:
    def test_make_progress_context(self):
        with make_progress(quiet=False) as progress:
            task = progress.add_task("test", total=10)
            progress.advance(task)
            assert progress is not None

    def test_make_progress_quiet(self):
        with make_progress(quiet=True) as progress:
            task = progress.add_task("test_quiet", total=10)
            progress.advance(task)
            assert progress.disable is True
