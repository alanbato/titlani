"""CLI command modules assembled into the main Typer app."""

import typer

from .admin import admin_app
from .identity import identity_app
from .init import init
from .list import list_app
from .mail import mail_app
from .send import send
from .serve import serve
from .tofu import tofu_app
from .verification import verification_app
from .version import version

app = typer.Typer(
    name="titlani",
    help="Titlani - Misfin(C) mail protocol client and server",
    add_completion=True,
    no_args_is_help=True,
)

app.command(rich_help_panel="Getting Started")(init)
app.command(rich_help_panel="Messaging")(send)
app.command(rich_help_panel="Server")(serve)
app.command(rich_help_panel="Getting Started")(version)
app.add_typer(admin_app, name="admin", rich_help_panel="Server")
app.add_typer(identity_app, name="identity", rich_help_panel="Security")
app.add_typer(tofu_app, name="tofu", rich_help_panel="Security")
app.add_typer(list_app, name="list", rich_help_panel="Server")
app.add_typer(mail_app, name="mail", rich_help_panel="Messaging")
app.add_typer(verification_app, name="verification", rich_help_panel="Security")
