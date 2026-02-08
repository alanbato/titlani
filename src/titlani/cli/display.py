"""Rich display helpers for Titlani CLI commands."""

import sys
from datetime import UTC, datetime
from importlib.metadata import version as get_version
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from ..content.gemmail import GemmailMessage
from ..identity.certificate import MisfinIdentity
from ..protocol.status import interpret_status
from ..server.config import ServerConfig

# -- Formatting helpers --


def format_fingerprint(fp: str) -> str:
    """Format a hex fingerprint into 4-char groups for readability."""
    clean = fp.replace(":", "").replace(" ", "").lower()
    return " ".join(clean[i : i + 4] for i in range(0, len(clean), 4))


def format_relative_time(dt: datetime) -> str:
    """Convert a datetime to a human-readable relative time string."""
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt

    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h}h ago"
    if delta.days < 30:
        return f"{delta.days}d ago"
    if delta.days < 365:
        months = delta.days // 30
        return f"{months}mo ago"
    years = delta.days // 365
    return f"{years}y ago"


def _validity_style(not_after_iso: str) -> tuple[str, str]:
    """Return (color, days_text) for a certificate expiry date."""
    not_after = datetime.fromisoformat(not_after_iso)
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    days = (not_after - datetime.now(UTC)).days

    if days < 0:
        return "red", f"Expired {abs(days)} days ago"
    if days < 30:
        return "yellow", f"{days} days remaining"
    return "green", f"{days} days remaining"


def _status_color(status: int) -> str:
    if 20 <= status < 30:
        return "green"
    if 30 <= status < 40:
        return "yellow"
    if 60 <= status < 70:
        return "magenta"
    return "red"


# -- Display functions --


def format_status_response(status: int, meta: str, console: Console) -> None:
    """Print a formatted status code response."""
    color = _status_color(status)
    desc = interpret_status(status)
    console.print(f"[{color}][{status}] {desc}[/]")
    if meta:
        console.print(f"  {meta}")


def display_identity_info(
    identity: MisfinIdentity,
    cert_info: dict[str, str],
    fingerprint: str,
    console: Console,
    *,
    cert_file: Path | None = None,
    key_file: Path | None = None,
    title: str = "Identity Certificate",
) -> None:
    """Display identity certificate information in a panel."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", width=14)
    table.add_column("Value")

    table.add_row("Address", identity.address)
    if identity.blurb:
        table.add_row("Blurb", identity.blurb)
    table.add_row("Hostname", identity.hostname)
    table.add_row("Fingerprint", format_fingerprint(fingerprint))

    if cert_file:
        table.add_row("Certificate", str(cert_file))
    if key_file:
        table.add_row("Private Key", str(key_file))

    # Validity dates with color coding
    not_before = cert_info.get("not_before", "")
    not_after = cert_info.get("not_after", "")
    if not_before:
        table.add_row("Not Before", not_before)
    if not_after:
        color, days_text = _validity_style(not_after)
        table.add_row("Not After", f"[{color}]{not_after}[/]")
        table.add_row("Validity", f"[{color}]{days_text}[/]")

    console.print(Panel(table, title=f"[bold]{title}[/]", expand=False))


def display_server_config(config: ServerConfig, console: Console) -> None:
    """Display a server configuration summary panel."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", width=22)
    table.add_column("Value")

    # Network
    table.add_row("Listen", f"{config.host}:{config.port}")
    table.add_row("Hostname", config.hostname)
    table.add_row("Mailbox Directory", str(config.mailbox_dir))

    # TLS
    if config.certfile:
        table.add_row("TLS Certificate", str(config.certfile))
    else:
        table.add_row("TLS Certificate", "[dim]auto-generated[/]")

    # Identity
    if config.identity_certfile:
        table.add_row("Identity Cert", str(config.identity_certfile))
    else:
        table.add_row("Identity Cert", "[dim]auto-generated[/]")

    # Rate limiting
    if config.rate_limit_enable:
        rl = (
            f"[green]Enabled[/] "
            f"(capacity={config.rate_limit_capacity}, "
            f"refill={config.rate_limit_refill_rate}/s)"
        )
        table.add_row("Rate Limiting", rl)
    else:
        table.add_row("Rate Limiting", "[dim]Disabled[/]")

    # Access control
    if config.access_control_enable:
        default = "allow" if config.access_control_default_allow else "deny"
        table.add_row("Access Control", f"[green]Enabled[/] (default: {default})")
    else:
        table.add_row("Access Control", "[dim]Disabled[/]")

    # Verification
    mode_styles = {
        "off": "[dim]Disabled[/]",
        "optional": "[yellow]Optional[/]",
        "required": "[green]Required[/]",
    }
    table.add_row(
        "Sender Verification",
        mode_styles.get(config.verification_mode, config.verification_mode),
    )

    console.print(
        Panel(
            table,
            title="[bold]Server Configuration[/]",
            expand=False,
        )
    )


def display_tofu_list(hosts: list[dict[str, Any]], console: Console) -> None:
    """Display TOFU known hosts table."""
    if not hosts:
        console.print("[yellow]No known hosts in TOFU database.[/]")
        return

    table = Table(title="Known Hosts (TOFU)")
    table.add_column("Hostname", style="cyan")
    table.add_column("Port", justify="right")
    table.add_column("Fingerprint")
    table.add_column("First Seen", justify="right")
    table.add_column("Last Seen", justify="right")

    for h in hosts:
        fp = h["fingerprint"]
        # Normalize fingerprint from tlacacoca's sha256:hex format
        if ":" in fp:
            fp = fp.split(":", 1)[1]
        first = datetime.fromisoformat(h["first_seen"])
        last = datetime.fromisoformat(h["last_seen"])
        table.add_row(
            h["hostname"],
            str(h["port"]),
            format_fingerprint(fp),
            format_relative_time(first),
            format_relative_time(last),
        )

    console.print(table)


def display_verification_list(
    entries: list[tuple[str, str, datetime]],
    console: Console,
) -> None:
    """Display verified senders table."""
    if not entries:
        console.print("[yellow]No verified senders in cache.[/]")
        return

    table = Table(title="Verified Senders")
    table.add_column("Address", style="cyan")
    table.add_column("Fingerprint")
    table.add_column("Verified", justify="right")

    for address, fingerprint, verified_at in entries:
        table.add_row(
            address,
            format_fingerprint(fingerprint),
            format_relative_time(verified_at),
        )

    console.print(table)


def display_gemmail_message(msg: GemmailMessage, console: Console) -> None:
    """Display a single gemmail message with metadata and body."""
    lines: list[str] = []

    if msg.senders:
        senders = ", ".join(s.long_form for s in msg.senders)
        lines.append(f"[bold cyan]From:[/]  {senders}")
    if msg.recipients:
        recips = ", ".join(r.long_form for r in msg.recipients)
        lines.append(f"[bold cyan]To:[/]    {recips}")
    if msg.timestamps:
        latest = max(msg.timestamps)
        ts = latest.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"[bold cyan]Date:[/]  {ts} ({format_relative_time(latest)})")

    lines.append("")
    lines.append(msg.body.rstrip("\n"))

    title = msg.subject or "Message"
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold]{title}[/]",
            border_style="cyan",
            expand=False,
        )
    )


def display_gemmail_list(
    messages: list[tuple[Path, GemmailMessage]],
    console: Console,
) -> None:
    """Display a table of gemmail messages."""
    if not messages:
        console.print("[yellow]No messages found.[/]")
        return

    table = Table(title=f"Messages ({len(messages)})")
    table.add_column("Received", style="dim", width=18)
    table.add_column("From", style="cyan", width=30)
    table.add_column("Subject")

    for filepath, msg in messages:
        # Parse timestamp from filename (e.g. 20260208T194757Z)
        stem = filepath.stem
        try:
            dt = datetime.strptime(stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            time_display = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            time_display = stem

        sender = msg.senders[0].long_form if msg.senders else "[dim]anonymous[/]"
        subject = msg.subject or "[dim]no subject[/]"
        table.add_row(time_display, sender, subject)

    console.print(table)


def display_version_info(console: Console) -> None:
    """Display version information in a panel."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold", width=14)
    table.add_column("Value")

    table.add_row("Version", get_version("titlani"))
    table.add_row("Protocol", "Misfin(C)")
    table.add_row("Python", sys.version.split()[0])

    for dep in ("rich", "typer", "tlacacoca", "cryptography"):
        try:
            table.add_row(f"  {dep}", get_version(dep))
        except Exception:
            pass

    console.print(
        Panel(
            table,
            title="[bold cyan]Titlani[/] Misfin(C) Client & Server",
            border_style="cyan",
            expand=False,
        )
    )


def confirm_action(prompt: str, console: Console) -> bool:
    """Ask for user confirmation via Rich prompt."""
    return Confirm.ask(prompt, console=console)
