"""PKCE OAuth flow against GitHub via the backend's /auth/cli/exchange.

Flow:
1. Generate PKCE verifier + S256 challenge and a random state.
2. Start a temporary loopback HTTP server on the configured port.
3. Open the GitHub authorize URL in the user's browser.
4. Capture the redirect (code, state) from GitHub.
5. POST {code, code_verifier} to the backend, which holds the client secret.
6. Persist the returned tokens to ~/.insighta/credentials.json.
"""

import base64
import hashlib
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import Config

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
SCOPE = "read:user user:email"


class AuthError(Exception):
    """User-facing auth failure."""


def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) where challenge = S256(verifier)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_authorize_url(
    *, client_id: str, redirect_uri: str, state: str, challenge: str
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


_DONE_HTML = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Insighta</title><style>body{font-family:system-ui;display:grid;
place-items:center;min-height:100vh;margin:0;background:#0d1117;color:#c9d1d9}
h1{font-weight:500}</style></head><body>
<div><h1>Logged in to Insighta.</h1><p>You can close this tab.</p></div>
</body></html>"""


def _capture_callback(port: int, timeout: float = 300.0) -> dict:
    """Run a one-shot HTTP server on 127.0.0.1:port until /callback fires."""
    captured: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_error(404)
                return
            params = parse_qs(parsed.query)
            captured["code"] = (params.get("code") or [None])[0]
            captured["state"] = (params.get("state") or [None])[0]
            captured["error"] = (params.get("error") or [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_DONE_HTML)))
            self.end_headers()
            self.wfile.write(_DONE_HTML)
            done.set()

        def log_message(self, *args, **kwargs):
            return  # silence default access logging

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not done.wait(timeout=timeout):
            raise AuthError("Timed out waiting for GitHub callback.")
    finally:
        server.shutdown()
        server.server_close()
    return captured


def _exchange_with_backend(
    *, backend_url: str, code: str, code_verifier: str
) -> dict:
    """POST /auth/cli/exchange. Returns the parsed response body on success."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{backend_url}/auth/cli/exchange",
                json={"code": code, "code_verifier": code_verifier},
            )
    except httpx.HTTPError as e:
        raise AuthError(f"Could not reach backend: {e}")

    if response.status_code != 200:
        try:
            body = response.json()
            message = body.get("message", response.text)
        except ValueError:
            message = response.text
        raise AuthError(
            f"Backend rejected exchange ({response.status_code}): {message}"
        )

    return response.json()


def run_login_flow(config: Config) -> dict:
    """Execute the full PKCE flow. Returns the backend's exchange response.

    Caller is responsible for persisting the returned tokens.
    """
    if not config.github_client_id:
        raise AuthError(
            "INSIGHTA_GITHUB_CLIENT_ID is not set. "
            "Configure the CLI's GitHub OAuth client ID in your environment."
        )

    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    authorize_url = _build_authorize_url(
        client_id=config.github_client_id,
        redirect_uri=config.redirect_uri,
        state=state,
        challenge=challenge,
    )

    # Open the browser BEFORE starting the server only to surface failures
    # earlier; we still need the server running to catch the redirect, so
    # in practice we open after the server is ready below.
    captured: dict = {}

    def _open_browser():
        webbrowser.open(authorize_url, new=2)

    # Bring up the server, then nudge the browser, then block on capture.
    _open_browser()
    captured = _capture_callback(config.callback_port)

    if captured.get("error"):
        raise AuthError(f"GitHub denied authorization: {captured['error']}")
    if not captured.get("code") or not captured.get("state"):
        raise AuthError("GitHub callback was missing code or state.")
    if captured["state"] != state:
        raise AuthError("OAuth state mismatch — possible CSRF attempt. Aborting.")

    return _exchange_with_backend(
        backend_url=config.backend_url,
        code=captured["code"],
        code_verifier=verifier,
    )
