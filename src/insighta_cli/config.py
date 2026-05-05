"""Runtime configuration. Read from environment with sensible local defaults."""

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """Apply KEY=VALUE pairs from `path` into os.environ.

    Real environment variables always win — we only `setdefault`. Lines
    starting with `#` and blank lines are skipped. Surrounding quotes
    on the value are stripped.
    """
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _autoload_envs() -> None:
    """Load INSIGHTA_* config from .env files near the user.

    Order (most specific first — already-set vars are never overwritten):
      1. ./.env in the current working directory
      2. ~/.insighta/config.env for a globally-installed CLI

    Skipped during pytest runs so test fixtures stay deterministic.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    _load_env_file(Path.cwd() / ".env")
    _load_env_file(Path.home() / ".insighta" / "config.env")


@dataclass(frozen=True)
class Config:
    backend_url: str
    github_client_id: str | None
    callback_port: int

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.callback_port}/callback"


def load_config() -> Config:
    """Load env-driven config. github_client_id may be None for non-login commands."""
    _autoload_envs()
    return Config(
        backend_url=os.environ.get(
            "INSIGHTA_BACKEND_URL", "https://insighta-labs-production-c161.up.railway.app"
        ).rstrip("/"),
        github_client_id=os.environ.get("INSIGHTA_GITHUB_CLIENT_ID"),
        callback_port=int(os.environ.get("INSIGHTA_CALLBACK_PORT", "51420")),
    )
