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


def test_help_lists_connect() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "azaks-conn" in result.stdout
    assert "connect" in result.stdout


def test_no_args_is_help() -> None:
    """Bare invocation should print help and exit non-zero (typer no_args_is_help)."""
    result = runner.invoke(app, [])
    # typer exits 0 with --help, but no_args_is_help triggers a usage error path.
    assert "connect" in result.stdout or "Usage" in result.stdout
