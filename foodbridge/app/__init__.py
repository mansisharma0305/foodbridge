"""FoodBridge application factory."""
import os
import secrets

from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from config import config_by_name

from .extensions import csrf, db, login_manager
from .utils import register_template_helpers

CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def create_app(config_name=None, overrides=None):
    name = config_name or os.environ.get("APP_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(name, config_by_name["development"]))
    if overrides:
        app.config.update(overrides)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("APP_ENV") == "production":
            raise RuntimeError("SECRET_KEY must be set in the environment when APP_ENV=production.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY not set: using a temporary random key (sessions reset on restart).")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"
    csrf.init_app(app)
    register_template_helpers(app)

    from . import models  # noqa: F401  (register models)
    from . import services
    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .cli import register_cli
    from .donor import bp as donor_bp
    from .main import bp as main_bp
    from .recipient import bp as recipient_bp

    for blueprint in (main_bp, auth_bp, donor_bp, recipient_bp, admin_bp):
        app.register_blueprint(blueprint)
    register_cli(app)

    with app.app_context():
        db.create_all()  # simple initialisation; `flask --app run init-db` does the same

    @app.before_request
    def _expire_overdue_listings():
        if request.endpoint in (None, "static"):
            return
        try:
            services.expire_overdue()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Could not refresh listing expiry")

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.endpoint != "static":
            resp.headers.setdefault("Cache-Control", "no-store")
        if app.config.get("SESSION_COOKIE_SECURE"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    def _error(code, title, message):
        return render_template("errors/error.html", code=code, title=title, message=message), code

    @app.errorhandler(403)
    def forbidden(_e):
        return _error(403, "Access denied", "You do not have permission to do that.")

    @app.errorhandler(404)
    def not_found(_e):
        return _error(404, "Page not found", "We could not find what you were looking for.")

    @app.errorhandler(429)
    def too_many(_e):
        return _error(429, "Too many attempts", "Please wait a few minutes before trying again.")

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return _error(400, "Session expired", "Your form expired or was invalid. Go back, refresh the page and try again.")

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return _error(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    return app
