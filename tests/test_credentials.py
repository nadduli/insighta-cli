import stat

from insighta_cli.credentials import (
    Credentials,
    delete_credentials,
    load_credentials,
    save_credentials,
    update_tokens,
)


def _sample(**overrides) -> Credentials:
    base = dict(
        backend_url="http://test.local",
        access_token="a.b.c",
        refresh_token="d.e.f",
        user_id="u-1",
        username="alice",
        role="analyst",
    )
    base.update(overrides)
    return Credentials.new(**base)


def test_save_then_load_roundtrips():
    creds = _sample()
    path = save_credentials(creds)
    assert path.exists()

    loaded = load_credentials()
    assert loaded is not None
    assert loaded.access_token == "a.b.c"
    assert loaded.refresh_token == "d.e.f"
    assert loaded.username == "alice"
    assert loaded.role == "analyst"


def test_credentials_file_is_user_only():
    save_credentials(_sample())
    loaded = load_credentials()
    from pathlib import Path
    path = Path.home() / ".insighta" / "credentials.json"
    mode = path.stat().st_mode

    # Owner read/write, no group/other access.
    assert bool(mode & stat.S_IRUSR)
    assert bool(mode & stat.S_IWUSR)
    assert not bool(mode & stat.S_IRGRP)
    assert not bool(mode & stat.S_IROTH)
    assert loaded is not None


def test_load_returns_none_when_missing():
    assert load_credentials() is None


def test_delete_removes_file():
    save_credentials(_sample())
    assert delete_credentials() is True
    assert load_credentials() is None
    assert delete_credentials() is False  # idempotent


def test_update_tokens_preserves_user_info():
    save_credentials(_sample())
    updated = update_tokens("new-access", "new-refresh")
    assert updated is not None
    assert updated.access_token == "new-access"
    assert updated.refresh_token == "new-refresh"
    assert updated.username == "alice"
    assert updated.user_id == "u-1"


def test_update_tokens_no_op_without_session():
    assert update_tokens("a", "b") is None
