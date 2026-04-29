"""Rich-based formatting helpers: tables, status spinners, error printing."""

from contextlib import contextmanager

from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


@contextmanager
def spinner(message: str):
    """Show a transient spinner during a network call."""
    with console.status(f"[cyan]{message}[/]", spinner="dots"):
        yield


def print_error(message: str) -> None:
    err_console.print(f"[bold red]Error:[/] {message}")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/] {message}")


def render_profiles_table(profiles: list[dict]) -> None:
    """Render a list of profile dicts as a Rich table."""
    if not profiles:
        console.print("[dim]No profiles match.[/]")
        return

    table = Table(show_lines=False, header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Gender")
    table.add_column("Age", justify="right")
    table.add_column("Group")
    table.add_column("Country")
    table.add_column("Conf.", justify="right")
    table.add_column("ID", style="dim")

    for p in profiles:
        table.add_row(
            p.get("name", ""),
            p.get("gender", ""),
            str(p.get("age", "")),
            p.get("age_group", ""),
            f"{p.get('country_id', '')} {p.get('country_name', '')}".strip(),
            f"{p.get('country_probability', 0):.2f}",
            p.get("id", ""),
        )
    console.print(table)


def render_profile_detail(profile: dict) -> None:
    """Render a single profile as a vertical key/value table."""
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    for key in (
        "id",
        "name",
        "gender",
        "gender_probability",
        "age",
        "age_group",
        "country_id",
        "country_name",
        "country_probability",
        "created_at",
    ):
        table.add_row(key, str(profile.get(key, "")))
    console.print(table)


def render_pagination_footer(meta: dict) -> None:
    """Print the page/total footer from a paginated response envelope."""
    page = meta.get("page", 1)
    total_pages = meta.get("total_pages", 1)
    total = meta.get("total", 0)
    console.print(
        f"[dim]Page {page}/{total_pages} — {total} matching profile"
        f"{'s' if total != 1 else ''}.[/]"
    )
