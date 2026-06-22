"""Smoke tests for the CLI surface."""

from __future__ import annotations

from typer.testing import CliRunner

from azaks_conn import __version__
from azaks_conn.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "azaks-conn" in result.stdout
    # Replace `hello` once the placeholder command is removed.
    assert "hello" in result.stdout


def test_hello_default() -> None:
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "world" in result.stdout


def test_hello_named() -> None:
    result = runner.invoke(app, ["hello", "--name", "naeem"])
    assert result.exit_code == 0
    assert "naeem" in result.stdout
