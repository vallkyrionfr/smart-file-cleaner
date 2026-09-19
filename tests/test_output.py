"""Tests for output formatters (utils/output.py)."""

import json

from rich.table import Table

from smart_file_cleaner.utils.output import (
    OutputFormat,
    OutputFormatter,
    make_formatter,
)


def test_make_formatter():
    fmt_text = make_formatter("text")
    assert fmt_text.format == OutputFormat.TEXT

    fmt_json = make_formatter("json")
    assert fmt_json.format == OutputFormat.JSON

    fmt_fallback = make_formatter("unknown_mode")
    assert fmt_fallback.format == OutputFormat.TEXT


def test_output_json(capsys):
    fmt = OutputFormatter(format=OutputFormat.JSON)
    data = {"status": "ok", "count": 42}
    fmt.print_json(data)

    captured = capsys.readouterr()
    assert json.loads(captured.out) == data


def test_output_text_mode_prints(capsys):
    fmt = OutputFormatter(format=OutputFormat.TEXT, no_color=True)
    fmt.print("Hello world")
    captured = capsys.readouterr()
    assert "Hello world" in captured.out


def test_output_json_mode_suppresses_text_print(capsys):
    fmt = OutputFormatter(format=OutputFormat.JSON)
    fmt.print("This should not print")
    captured = capsys.readouterr()
    assert "This should not print" not in captured.out


def test_output_error_stderr(capsys):
    fmt = OutputFormatter()
    fmt.print_error("Critical failure")
    captured = capsys.readouterr()
    assert "Critical failure" in captured.err


def test_output_warning_stderr(capsys):
    fmt = OutputFormatter()
    fmt.print_warning("Check this out")
    captured = capsys.readouterr()
    assert "Check this out" in captured.err


def test_output_success_text_only(capsys):
    fmt_text = OutputFormatter(format=OutputFormat.TEXT, no_color=True)
    fmt_text.print_success("Done successfully")
    captured = capsys.readouterr()
    assert "Done successfully" in captured.out

    fmt_json = OutputFormatter(format=OutputFormat.JSON)
    fmt_json.print_success("Done successfully")
    captured_json = capsys.readouterr()
    assert "Done successfully" not in captured_json.out


def test_output_panel_and_table(capsys):
    fmt = OutputFormatter(format=OutputFormat.TEXT, no_color=True)
    fmt.print_panel("Panel content", title="Title")
    table = Table(title="Test Table")
    table.add_column("Col1")
    table.add_row("Val1")
    fmt.print_table(table)

    captured = capsys.readouterr()
    assert "Panel content" in captured.out
    assert "Col1" in captured.out
    assert "Val1" in captured.out
