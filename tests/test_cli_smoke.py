"""Smoke tests for the Typer app — make sure command wiring is intact."""

from typer.testing import CliRunner

from insighta_cli import __version__
from insighta_cli.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_root_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("login", "logout", "whoami", "profiles"):
        assert cmd in result.stdout


def test_profiles_help_lists_subcommands():
    result = runner.invoke(app, ["profiles", "--help"])
    assert result.exit_code == 0
    for cmd in ("list", "get", "search", "create", "export", "upload"):
        assert cmd in result.stdout


def test_whoami_without_session_exits_one():
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output or "Not logged in" in result.stderr
