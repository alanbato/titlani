"""Init command — interactive wizard for generating config files."""

from pathlib import Path

import typer
from platformdirs import user_config_path
from rich.console import Console

from ...protocol.constants import DEFAULT_GMAP_PORT, DEFAULT_PORT
from ...server.config import default_mailbox_dir

console = Console()
error_console = Console(stderr=True, style="bold red")

DEFAULT_CONFIG_DIR = user_config_path("titlani")


def _build_server_toml(
    *,
    hostname: str,
    port: int,
    mailbox_dir: str,
    gmap_enable: bool,
    gmap_port: int,
    verification_enable: bool,
    verification_mode: str,
    encryption_enable: bool,
    auto_reply_enable: bool,
    auto_reply_interval: int,
    rate_limit_enable: bool,
    rate_limit_capacity: int,
    rate_limit_refill_rate: float,
    access_control_enable: bool,
    access_control_default_allow: bool,
) -> str:
    lines = [
        "[server]",
        f'hostname = "{hostname}"',
        f"port = {port}",
        f'mailbox_dir = "{mailbox_dir}"',
        '# certfile = "server.pem"',
        '# keyfile = "server.key"',
        '# identity_certfile = "identity.pem"',
        '# identity_keyfile = "identity.key"',
        "",
        "[verification]",
    ]
    if verification_enable:
        lines.append(f'mode = "{verification_mode}"')
    else:
        lines.append('# mode = "optional"')
    lines += [
        "# cache_ttl = 604800",
        "# probe_timeout = 10.0",
        "",
        "[encryption]",
        f"enable = {str(encryption_enable).lower()}",
        '# key_dir = "keys"',
        "",
        "[gmap]",
        f"enable = {str(gmap_enable).lower()}",
        f"port = {gmap_port}",
        "",
        "[auto_reply]",
        f"enable = {str(auto_reply_enable).lower()}",
    ]
    if auto_reply_enable:
        lines.append(f"interval = {auto_reply_interval}")
    else:
        lines.append("# interval = 86400")
    lines += [
        "",
        "[rate_limit]",
        f"enable = {str(rate_limit_enable).lower()}",
    ]
    if rate_limit_enable:
        lines.append(f"capacity = {rate_limit_capacity}")
        lines.append(f"refill_rate = {rate_limit_refill_rate}")
    else:
        lines.append("# capacity = 10")
        lines.append("# refill_rate = 1.0")
    lines += [
        "# retry_after = 30",
        "",
        "[access_control]",
        f"enable = {str(access_control_enable).lower()}",
    ]
    if access_control_enable:
        lines.append(f"default_allow = {str(access_control_default_allow).lower()}")
    else:
        lines.append("# default_allow = true")
    lines += [
        "# allow_list = []",
        "# deny_list = []",
        "",
    ]
    return "\n".join(lines)


def _build_client_toml(server_config_path: Path) -> str:
    return f'[mail]\nserver_config = "{server_config_path}"\n'


def init(
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory to write config files to",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing config files",
    ),
) -> None:
    """Interactive wizard to generate server and client config files."""
    config_dir = output_dir or DEFAULT_CONFIG_DIR

    server_path = config_dir / "server.toml"
    client_path = config_dir / "config.toml"

    if not force:
        existing = [p for p in (server_path, client_path) if p.exists()]
        if existing:
            names = ", ".join(p.name for p in existing)
            error_console.print(
                f"Config files already exist: {names}\nUse --force to overwrite."
            )
            raise typer.Exit(code=1)

    # Step 1: Essentials
    console.print("\n[bold]Step 1: Essentials[/]\n")
    hostname = typer.prompt("Hostname for mail routing", default="localhost")
    port = typer.prompt("Port", default=DEFAULT_PORT, type=int)
    mailbox_dir = typer.prompt("Mailbox directory", default=str(default_mailbox_dir()))

    # Step 2: Feature toggles
    console.print("\n[bold]Step 2: Feature toggles[/]\n")
    gmap_enable = typer.confirm("Enable GMAP (remote mailbox access)?", default=False)
    verification_enable = typer.confirm(
        "Enable sender verification (probe-based)?", default=False
    )
    encryption_enable = typer.confirm("Enable at-rest encryption?", default=False)
    auto_reply_enable = typer.confirm("Enable auto-reply?", default=False)
    rate_limit_enable = typer.confirm("Enable rate limiting?", default=False)
    access_control_enable = typer.confirm(
        "Enable access control (IP allow/deny)?", default=False
    )

    # Step 3: Detail prompts for enabled features
    verification_mode = "off"
    auto_reply_interval = 86400
    rate_limit_capacity = 10
    rate_limit_refill_rate = 1.0
    access_control_default_allow = True

    gmap_port = DEFAULT_GMAP_PORT

    has_details = any(
        [
            gmap_enable,
            verification_enable,
            auto_reply_enable,
            rate_limit_enable,
            access_control_enable,
        ]
    )
    if has_details:
        console.print("\n[bold]Step 3: Feature details[/]\n")

    if gmap_enable:
        gmap_port = typer.prompt("GMAP port", default=DEFAULT_GMAP_PORT, type=int)

    if verification_enable:
        verification_mode = typer.prompt(
            "Verification mode (optional/required)",
            default="optional",
        )
        if verification_mode not in ("optional", "required"):
            error_console.print(f"Invalid verification mode: {verification_mode!r}")
            raise typer.Exit(code=1)

    if auto_reply_enable:
        auto_reply_interval = typer.prompt(
            "Auto-reply interval in seconds", default=86400, type=int
        )

    if rate_limit_enable:
        rate_limit_capacity = typer.prompt("Rate limit capacity", default=10, type=int)
        rate_limit_refill_rate = typer.prompt("Refill rate", default=1.0, type=float)

    if access_control_enable:
        access_control_default_allow = typer.confirm(
            "Allow connections by default?", default=True
        )

    # Step 4: Write files
    server_toml = _build_server_toml(
        hostname=hostname,
        port=port,
        mailbox_dir=mailbox_dir,
        gmap_enable=gmap_enable,
        gmap_port=gmap_port,
        verification_enable=verification_enable,
        verification_mode=verification_mode,
        encryption_enable=encryption_enable,
        auto_reply_enable=auto_reply_enable,
        auto_reply_interval=auto_reply_interval,
        rate_limit_enable=rate_limit_enable,
        rate_limit_capacity=rate_limit_capacity,
        rate_limit_refill_rate=rate_limit_refill_rate,
        access_control_enable=access_control_enable,
        access_control_default_allow=access_control_default_allow,
    )
    client_toml = _build_client_toml(server_path)

    config_dir.mkdir(parents=True, exist_ok=True)
    server_path.write_text(server_toml)
    client_path.write_text(client_toml)

    console.print(f"\n[green]Wrote:[/] {server_path}")
    console.print(f"[green]Wrote:[/] {client_path}")
    console.print("\nStart your server with: [bold]titlani serve[/]")
