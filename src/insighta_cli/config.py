"""Runtime configuration. Read from environment with sensible local defaults."""

import os
from dataclasses import dataclass


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
    return Config(
        backend_url=os.environ.get("INSIGHTA_BACKEND_URL", "http://localhost:8000").rstrip("/"),
        github_client_id=os.environ.get("INSIGHTA_GITHUB_CLIENT_ID"),
        callback_port=int(os.environ.get("INSIGHTA_CALLBACK_PORT", "51420")),
    )
