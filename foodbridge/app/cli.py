"""Flask CLI: init-db, reset-db, create-admin, seed-demo."""
import click
from sqlalchemy import select

from . import constants as C
from .extensions import db
from .models import User
from .utils import password_error


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables (safe to run repeatedly)."""
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="This DELETES ALL DATA. Continue?")
    def reset_db():
        """Drop and recreate every table."""
        db.drop_all()
        db.create_all()
        click.echo("Database reset.")

    @app.cli.command("create-admin")
    @click.option("--email", envvar="ADMIN_EMAIL", prompt=True, help="Admin email (or ADMIN_EMAIL).")
    @click.option("--name", envvar="ADMIN_NAME", default="FoodBridge Admin", show_default=True)
    @click.option("--password", envvar="ADMIN_PASSWORD", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(email, name, password):
        """Provision (or reset the password of) an admin. There is no public admin signup."""
        email = email.strip().lower()
        problem = password_error(password)
        if problem:
            raise click.ClickException(problem)
        user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user and user.role != C.ADMIN:
            raise click.ClickException("That email belongs to a non-admin account. Use a different email.")
        if user:
            user.set_password(password)
            user.active = True
            click.echo(f"Password updated for existing admin {email}.")
        else:
            user = User(name=name, email=email, role=C.ADMIN, organization="FoodBridge Admin")
            user.set_password(password)
            db.session.add(user)
            click.echo(f"Admin {email} created.")
        db.session.commit()

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Remove previous sample data first.")
    @click.option("--force", is_flag=True, help="Allow seeding when APP_ENV=production (not recommended).")
    def seed_demo_cmd(reset, force):
        """Create clearly labelled SAMPLE users and donations for demonstration."""
        from .seed import DEMO_PASSWORD, seed_demo

        if app.config.get("APP_ENV") == "production" and not force:
            raise click.ClickException("Refusing to seed demo data in production (use --force to override).")
        try:
            summary = seed_demo(reset=reset)
        except RuntimeError as exc:
            raise click.ClickException(str(exc))
        click.echo(f"Seeded {summary['users']} sample users and {summary['donations']} sample donations.")
        click.echo("Sample logins (all use the demo password):")
        for email in summary["emails"]:
            click.echo(f"  {email}")
        click.echo(f"Demo password: {DEMO_PASSWORD}")
