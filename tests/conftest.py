import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch):
    """Force HOME to a temp dir so credentials writes never touch the real home dir."""
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("HOME", td)
        # Path.home() reads $HOME on POSIX
        yield Path(td)


@pytest.fixture
def cli_env(monkeypatch):
    monkeypatch.setenv("INSIGHTA_BACKEND_URL", "http://test.local")
    monkeypatch.setenv("INSIGHTA_GITHUB_CLIENT_ID", "test-client")
    monkeypatch.setenv("INSIGHTA_CALLBACK_PORT", "51420")
    yield
