import base64
import hashlib

from insighta_cli.auth import _build_authorize_url, _generate_pkce


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
