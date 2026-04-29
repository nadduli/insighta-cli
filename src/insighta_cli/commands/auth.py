"""`insighta login`, `logout`, `whoami` commands."""

import typer

from ..auth import AuthError, run_login_flow
from ..client import APIClient, APIError, NotAuthenticated, require_session
from ..config import load_config
from ..credentials import (
    Credentials,
    delete_credentials,
    load_credentials,
    save_credentials,
)
from ..output import console, print_error, print_success, spinner

app = typer.Typer(help="Authentication commands.", no_args_is_help=True)


@app.command()
def login() -> None:
    """Authenticate with GitHub via PKCE and store the session locally."""
    config = load_config()

    try:
        with spinner("Opening browser for GitHub authorization"):
            response = run_login_flow(config)
    except AuthError as e:
        print_error(str(e))
        raise typer.Exit(1)

    user = response.get("user") or {}
    creds = Credentials.new(
        backend_url=config.backend_url,
        access_token=response["access_token"],
        refresh_token=response["refresh_token"],
        user_id=user.get("id", ""),
        username=user.get("username", "unknown"),
        role=user.get("role", "analyst"),
    )
    save_credentials(creds)
    print_success(f"Logged in as @{creds.username} ({creds.role}).")


@app.command()
def logout() -> None:
    """Revoke the current session and clear local credentials."""
    creds = load_credentials()
    if creds is None:
        console.print("[dim]No active session.[/]")
        return

    # Best-effort server-side revoke. If the network's down or the token is
    # already invalid, still clear locally — logout must always succeed.
    with APIClient(creds) as client:
        try:
            client.post_json(
                "/auth/logout",
                json_body={"refresh_token": creds.refresh_token},
            )
        except Exception:
            pass

    delete_credentials()
    print_success("Logged out.")


@app.command()
def whoami() -> None:
    """Show the currently authenticated user."""
    try:
        creds = require_session()
    except NotAuthenticated as e:
        print_error(str(e))
        raise typer.Exit(1)

    with APIClient(creds) as client:
        try:
            with spinner("Fetching account"):
                me = client.get_json("/auth/me")
        except NotAuthenticated as e:
            print_error(str(e))
            raise typer.Exit(1)
        except APIError as e:
            print_error(e.message)
            raise typer.Exit(1)

    console.print(
        f"[bold]@{me.get('username')}[/] · role: [cyan]{me.get('role')}[/] · "
        f"id: [dim]{me.get('id')}[/]"
    )
    if me.get("email"):
        console.print(f"email: {me['email']}")
