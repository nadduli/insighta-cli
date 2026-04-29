"""Credential persistence at ~/.insighta/credentials.json (mode 0600)."""

import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def _credentials_dir() -> Path:
    return Path.home() / ".insighta"


def _credentials_path() -> Path:
    return _credentials_dir() / "credentials.json"


@dataclass
class Credentials:
    backend_url: str
    access_token: str
    refresh_token: str
    user_id: str
    username: str
    role: str
    saved_at: str

    @classmethod
    def new(
        cls,
        *,
        backend_url: str,
        access_token: str,
        refresh_token: str,
        user_id: str,
        username: str,
        role: str,
    ) -> "Credentials":
        return cls(
            backend_url=backend_url,
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            username=username,
            role=role,
            saved_at=datetime.now(timezone.utc).isoformat(),
        )


def save_credentials(creds: Credentials) -> Path:
    """Persist credentials to disk with 0600 perms. Returns the path."""
    dir_path = _credentials_dir()
    dir_path.mkdir(mode=0o700, exist_ok=True)
    # mkdir(exist_ok=True) doesn't fix perms on an existing dir; force them.
    os.chmod(dir_path, 0o700)

    path = _credentials_path()
    # Write to a temp file first, then atomic-rename. Avoids a half-written file
    # if we get interrupted mid-write.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(creds), indent=2))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    return path


def load_credentials() -> Credentials | None:
    """Read credentials from disk, or None if no session is stored."""
    path = _credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return Credentials(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def delete_credentials() -> bool:
    """Remove the credentials file. Returns True if a file was removed."""
    path = _credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def update_tokens(access_token: str, refresh_token: str) -> Credentials | None:
    """Persist a refreshed (access, refresh) pair, keeping user info intact."""
    creds = load_credentials()
    if creds is None:
        return None
    creds.access_token = access_token
    creds.refresh_token = refresh_token
    creds.saved_at = datetime.now(timezone.utc).isoformat()
    save_credentials(creds)
    return creds
