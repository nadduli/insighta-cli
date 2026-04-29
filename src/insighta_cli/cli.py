"""Top-level Typer app. Wires command groups to the `insighta` entrypoint."""

import typer

from . import __version__
from .commands import auth as auth_cmd
from .commands import profiles as profiles_cmd

app = typer.Typer(
    name="insighta",
    help="Insighta Labs+ CLI — query the profile intelligence platform.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(profiles_cmd.app, name="profiles")

# login / logout / whoami live at the top level for ergonomics.
app.command("login")(auth_cmd.login)
app.command("logout")(auth_cmd.logout)
app.command("whoami")(auth_cmd.whoami)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"insighta {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Insighta Labs+ command-line client."""


def main() -> None:
    app()
