"""`headroom overlay` CLI — registered via headroom.cli_extension."""

from __future__ import annotations

import click

from .control import grace_seconds, list_clients, set_grace_seconds, status, stop


def register(main: click.Group) -> None:
    @main.group("overlay")
    def overlay() -> None:
        """macOS overlay: stop / status / idle grace (local, not upstream)."""

    @overlay.command("stop")
    def overlay_stop() -> None:
        """Stop the three overlay jobs if no named clients are running."""
        code, message, clients = stop()
        if clients:
            click.echo(message, err=True)
            for row in clients:
                click.echo(f"  {row}", err=True)
            raise SystemExit(1)
        click.echo(message)
        if code:
            raise SystemExit(1)

    @overlay.command("status")
    def overlay_status() -> None:
        data = status()
        click.echo(f"grace_seconds={data['grace_seconds']}")
        click.echo(f"running={data['running']} listening={data['listening']}")
        clients = data["clients"] or list_clients()
        if clients:
            click.echo("clients:")
            for row in clients:
                click.echo(f"  {row}")
        else:
            click.echo("clients: none")

    @overlay.command("grace")
    @click.argument("seconds", type=int, required=False)
    def overlay_grace(seconds: int | None) -> None:
        """Get or set idle stop grace (seconds after last client exits)."""
        if seconds is None:
            click.echo(str(grace_seconds()))
            return
        click.echo(str(set_grace_seconds(seconds)))
