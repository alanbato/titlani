"""CLI command modules assembled into the main Typer app."""

import typer

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

app.command()(init)
app.command()(send)
app.command()(serve)
app.command()(version)
app.add_typer(identity_app, name="identity")
app.add_typer(tofu_app, name="tofu")
app.add_typer(list_app, name="list")
app.add_typer(mail_app, name="mail")
app.add_typer(verification_app, name="verification")
