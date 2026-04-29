"""HTTP client for the backend with auto-refresh on 401.

Always sends `X-API-Version: 1` and a Bearer token. On a 401, attempts a
single token refresh (POST /auth/refresh) and retries the original request
once. If the refresh itself fails, raises NotAuthenticated so the caller
can prompt for re-login.
"""

from typing import Any

import httpx

from .credentials import (
    Credentials,
    delete_credentials,
    load_credentials,
    update_tokens,
)

API_VERSION = "1"


class APIError(Exception):
    """Backend returned a non-2xx response. Carries the parsed message."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code
        self.message = message


class NotAuthenticated(Exception):
    """No usable session — caller should prompt for re-login."""


def _extract_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return body.get("message") or response.text or "Unknown error"
    except ValueError:
        pass
    return response.text or "Unknown error"


class APIClient:
    """Thin wrapper around httpx.Client with the cross-cutting concerns baked in."""

    def __init__(self, creds: Credentials):
        self._creds = creds
        self._client = httpx.Client(
            base_url=creds.backend_url,
            timeout=20.0,
            headers={"X-API-Version": API_VERSION},
        )

    def __enter__(self) -> "APIClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    @property
    def credentials(self) -> Credentials:
        return self._creds

    # ---- token refresh ----------------------------------------------------

    def _refresh_tokens(self) -> bool:
        """Attempt to rotate. Returns True if refreshed, False otherwise."""
        try:
            response = self._client.post(
                "/auth/refresh",
                json={"refresh_token": self._creds.refresh_token},
            )
        except httpx.HTTPError:
            return False

        if response.status_code != 200:
            return False

        try:
            body = response.json()
        except ValueError:
            return False

        access = body.get("access_token")
        refresh = body.get("refresh_token")
        if not access or not refresh:
            return False

        updated = update_tokens(access, refresh)
        if updated is None:
            return False
        self._creds = updated
        return True

    # ---- request -----------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
    ) -> httpx.Response:
        """Make a request. Retries once after refresh on 401."""
        response = self._client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {self._creds.access_token}"},
        )
        if response.status_code != 401:
            return response

        # Try one refresh + retry
        if not self._refresh_tokens():
            delete_credentials()
            raise NotAuthenticated("Session expired. Run `insighta login` again.")

        return self._client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {self._creds.access_token}"},
        )

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        response = self.request("GET", url, params=params)
        if response.status_code >= 400:
            raise APIError(response.status_code, _extract_error_message(response))
        return response.json()

    def post_json(self, url: str, *, json_body: Any = None) -> dict:
        response = self.request("POST", url, json_body=json_body)
        if response.status_code >= 400:
            raise APIError(response.status_code, _extract_error_message(response))
        return response.json()

    def stream(self, method: str, url: str, *, params: dict | None = None):
        """Open a streaming request for downloads (e.g. CSV export).

        The caller is responsible for the context manager. Falls back to
        non-streamed on 401 + refresh + retry to keep the logic simple.
        """
        # First try with streaming
        request = self._client.build_request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {self._creds.access_token}"},
        )
        response = self._client.send(request, stream=True)
        if response.status_code != 401:
            return response

        # 401: close it, refresh, retry once.
        response.close()
        if not self._refresh_tokens():
            delete_credentials()
            raise NotAuthenticated("Session expired. Run `insighta login` again.")

        retry = self._client.build_request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {self._creds.access_token}"},
        )
        return self._client.send(retry, stream=True)


def require_session() -> Credentials:
    """Load credentials or raise NotAuthenticated."""
    creds = load_credentials()
    if creds is None:
        raise NotAuthenticated("Not logged in. Run `insighta login` first.")
    return creds
