import base64
import hashlib
import socket
from urllib.request import urlopen

import pytest

from insighta_cli.auth import (
    AuthError,
    _build_authorize_url,
    _generate_pkce,
    _start_callback_server,
)


def _free_port() -> int:
    """Grab an OS-assigned free port to avoid clashing with the user's :51420."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = _generate_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected


def test_pkce_verifier_is_high_entropy():
    seen = {_generate_pkce()[0] for _ in range(50)}
    assert len(seen) == 50  # collision would mean broken randomness


def test_authorize_url_carries_pkce_and_state():
    url = _build_authorize_url(
        client_id="abc",
        redirect_uri="http://127.0.0.1:51420/callback",
        state="s-1",
        challenge="ch-1",
    )
    assert "client_id=abc" in url
    assert "state=s-1" in url
    assert "code_challenge=ch-1" in url
    assert "code_challenge_method=S256" in url
    assert "scope=read%3Auser+user%3Aemail" in url


def test_callback_server_captures_code_and_state():
    port = _free_port()
    server, captured, done = _start_callback_server(port)
    try:
        urlopen(f"http://127.0.0.1:{port}/callback?code=abc&state=xyz").read()
        assert done.wait(timeout=2.0)
        assert captured == {"code": "abc", "state": "xyz", "error": None}
    finally:
        server.shutdown()
        server.server_close()


def test_callback_server_clean_error_on_port_in_use():
    port = _free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        with pytest.raises(AuthError, match="Could not bind"):
            _start_callback_server(port)
    finally:
        blocker.close()
