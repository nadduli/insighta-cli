"""`insighta profiles ...` command group."""

import re
from datetime import datetime, timezone
from pathlib import Path

import typer

from ..client import APIClient, APIError, NotAuthenticated, require_session
from ..output import (
    console,
    print_error,
    print_success,
    render_pagination_footer,
    render_profile_detail,
    render_profiles_table,
    spinner,
)

app = typer.Typer(help="Profile commands.", no_args_is_help=True)


def _build_filter_params(
    *,
    gender: str | None,
    country: str | None,
    age_group: str | None,
    min_age: int | None,
    max_age: int | None,
    sort_by: str | None,
    order: str | None,
    page: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict = {}
    if gender:
        params["gender"] = gender
    if country:
        params["country_id"] = country
    if age_group:
        params["age_group"] = age_group
    if min_age is not None:
        params["min_age"] = min_age
    if max_age is not None:
        params["max_age"] = max_age
    if sort_by:
        params["sort_by"] = sort_by
    if order:
        params["order"] = order
    if page is not None:
        params["page"] = page
    if limit is not None:
        params["limit"] = limit
    return params


def _run(client_call):
    """Wrap a callable that uses the API client; map errors to typer.Exit."""
    try:
        return client_call()
    except NotAuthenticated as e:
        print_error(str(e))
        raise typer.Exit(1)
    except APIError as e:
        print_error(e.message)
        raise typer.Exit(1)


@app.command("list")
def list_profiles(
    gender: str | None = typer.Option(None, "--gender", help="male / female"),
    country: str | None = typer.Option(None, "--country", help="ISO-3166 alpha-2"),
    age_group: str | None = typer.Option(
        None, "--age-group", help="child / teenager / adult / senior"
    ),
    min_age: int | None = typer.Option(None, "--min-age"),
    max_age: int | None = typer.Option(None, "--max-age"),
    sort_by: str | None = typer.Option(
        None, "--sort-by", help="age / created_at / gender_probability"
    ),
    order: str | None = typer.Option(None, "--order", help="asc / desc"),
    page: int = typer.Option(1, "--page"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """List profiles with optional filters and pagination."""
    creds = require_session()
    params = _build_filter_params(
        gender=gender,
        country=country,
        age_group=age_group,
        min_age=min_age,
        max_age=max_age,
        sort_by=sort_by,
        order=order,
        page=page,
        limit=limit,
    )

    def call():
        with APIClient(creds) as client, spinner("Loading profiles"):
            return client.get_json("/api/profiles", params=params)

    body = _run(call)
    render_profiles_table(body.get("data", []))
    render_pagination_footer(body)


@app.command()
def get(profile_id: str = typer.Argument(..., help="Profile UUID")) -> None:
    """Fetch a single profile by ID."""
    creds = require_session()

    def call():
        with APIClient(creds) as client, spinner("Loading profile"):
            return client.get_json(f"/api/profiles/{profile_id}")

    body = _run(call)
    render_profile_detail(body.get("data", {}))


@app.command()
def search(
    query: str = typer.Argument(..., help='e.g. "young males from nigeria"'),
    page: int = typer.Option(1, "--page"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """Natural-language profile search."""
    creds = require_session()

    def call():
        with APIClient(creds) as client, spinner("Searching"):
            return client.get_json(
                "/api/profiles/search",
                params={"q": query, "page": page, "limit": limit},
            )

    body = _run(call)
    if body.get("status") == "error":
        print_error(body.get("message", "Unable to interpret query"))
        raise typer.Exit(1)

    render_profiles_table(body.get("data", []))
    render_pagination_footer(body)


@app.command()
def create(
    name: str = typer.Option(..., "--name", help="Person's name to enrich and store"),
) -> None:
    """Create a new profile by enriching the given name (admin only)."""
    creds = require_session()

    def call():
        with APIClient(creds) as client, spinner(f"Enriching '{name}'"):
            return client.post_json("/api/profiles", json_body={"name": name})

    body = _run(call)
    profile = body.get("data") or {}
    if body.get("message") == "Profile already exists":
        console.print(f"[yellow]Profile already exists for {profile.get('name')}.[/]")
    else:
        print_success(f"Created profile {profile.get('id')} for {profile.get('name')}.")
    render_profile_detail(profile)


@app.command()
def export(
    format: str = typer.Option("csv", "--format", help="Only csv is supported"),
    gender: str | None = typer.Option(None, "--gender"),
    country: str | None = typer.Option(None, "--country"),
    age_group: str | None = typer.Option(None, "--age-group"),
    min_age: int | None = typer.Option(None, "--min-age"),
    max_age: int | None = typer.Option(None, "--max-age"),
    sort_by: str | None = typer.Option(None, "--sort-by"),
    order: str | None = typer.Option(None, "--order"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Override destination path. Default: profiles_<timestamp>.csv in cwd.",
    ),
) -> None:
    """Stream the matching profiles as CSV into the current directory."""
    if format != "csv":
        print_error("Only --format csv is supported.")
        raise typer.Exit(2)

    creds = require_session()
    params = _build_filter_params(
        gender=gender,
        country=country,
        age_group=age_group,
        min_age=min_age,
        max_age=max_age,
        sort_by=sort_by,
        order=order,
    )
    params["format"] = "csv"

    def call():
        with APIClient(creds) as client, spinner("Exporting"):
            response = client.stream("GET", "/api/profiles/export", params=params)
            try:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace")
                    raise APIError(response.status_code, body)

                target = output or Path.cwd() / _filename_from_headers(response.headers)
                try:
                    with target.open("wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
                except OSError as e:
                    raise APIError(0, f"Could not write {target}: {e}")
                return target
            finally:
                response.close()

    target = _run(call)
    print_success(f"Wrote {target}")


def _filename_from_headers(headers) -> str:
    """Pull filename from Content-Disposition; fall back to a timestamped name."""
    cd = headers.get("content-disposition", "")
    match = re.search(r'filename="([^"]+)"', cd)
    if match:
        return match.group(1)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"profiles_{ts}.csv"
