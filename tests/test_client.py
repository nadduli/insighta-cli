from pathlib import Path

import httpx
import pytest
import respx

from insighta_cli.client import APIClient, NotAuthenticated
from insighta_cli.credentials import Credentials, save_credentials


def _make_creds(access="access-1", refresh="refresh-1") -> Credentials:
    creds = Credentials.new(
        backend_url="http://test.local",
        access_token=access,
        refresh_token=refresh,
        user_id="u-1",
        username="alice",
        role="analyst",
    )
    save_credentials(creds)
    return creds


@respx.mock
def test_request_sends_bearer_and_api_version_header():
    creds = _make_creds()
    route = respx.get("http://test.local/api/profiles").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": []})
    )

    with APIClient(creds) as client:
        client.get_json("/api/profiles", params={"page": 1})

    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer access-1"
    assert sent.headers["x-api-version"] == "1"


@respx.mock
def test_401_triggers_refresh_and_retry():
    creds = _make_creds()

    api_call = respx.get("http://test.local/api/profiles")
    api_call.side_effect = [
        httpx.Response(401, json={"status": "error", "message": "Token expired"}),
        httpx.Response(200, json={"status": "success", "data": []}),
    ]

    refresh_call = respx.post("http://test.local/auth/refresh").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "access_token": "access-2",
                "refresh_token": "refresh-2",
            },
        )
    )

    with APIClient(creds) as client:
        client.get_json("/api/profiles")

    assert refresh_call.called
    assert api_call.call_count == 2

    # The retry must use the rotated bearer token.
    second_call = api_call.calls[1].request
    assert second_call.headers["authorization"] == "Bearer access-2"


@respx.mock
def test_refresh_failure_raises_not_authenticated_and_clears_creds():
    _make_creds()

    respx.get("http://test.local/api/profiles").mock(
        return_value=httpx.Response(401, json={"status": "error", "message": "expired"})
    )
    respx.post("http://test.local/auth/refresh").mock(
        return_value=httpx.Response(
            401, json={"status": "error", "message": "bad refresh"}
        )
    )

    creds = _make_creds()
    with APIClient(creds) as client:
        with pytest.raises(NotAuthenticated):
            client.get_json("/api/profiles")

    from insighta_cli.credentials import load_credentials

    assert load_credentials() is None  # cleared


@respx.mock
def test_upload_file_posts_multipart(tmp_path: Path):
    creds = _make_creds()

    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text(
        "name,gender,age,country_id\nA,male,30,NG\n", encoding="utf-8"
    )

    route = respx.post("http://test.local/api/profiles/upload").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "total_rows": 1,
                "inserted": 1,
                "skipped": 0,
                "reasons": {},
            },
        )
    )

    with APIClient(creds) as client:
        result = client.upload_file("/api/profiles/upload", csv_path)

    assert result["inserted"] == 1
    assert route.called

    sent = route.calls[0].request
    # multipart with the right boundary header
    assert sent.headers["content-type"].startswith("multipart/form-data;")
    # Bearer + API version preserved
    assert sent.headers["authorization"] == "Bearer access-1"
    assert sent.headers["x-api-version"] == "1"


@respx.mock
def test_upload_file_refreshes_token_on_401(tmp_path: Path):
    creds = _make_creds()
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text(
        "name,gender,age,country_id\nA,male,30,NG\n", encoding="utf-8"
    )

    upload_route = respx.post("http://test.local/api/profiles/upload")
    upload_route.side_effect = [
        httpx.Response(401, json={"status": "error", "message": "expired"}),
        httpx.Response(
            200,
            json={
                "status": "success",
                "total_rows": 1,
                "inserted": 1,
                "skipped": 0,
                "reasons": {},
            },
        ),
    ]

    refresh_route = respx.post("http://test.local/auth/refresh").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "success",
                "access_token": "access-2",
                "refresh_token": "refresh-2",
            },
        )
    )

    with APIClient(creds) as client:
        result = client.upload_file("/api/profiles/upload", csv_path)

    assert result["inserted"] == 1
    assert refresh_route.called
    assert upload_route.call_count == 2

    # Retry must use the rotated token
    second = upload_route.calls[1].request
    assert second.headers["authorization"] == "Bearer access-2"
