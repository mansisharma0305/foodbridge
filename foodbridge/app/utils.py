"""Small helpers: time, formatting, validation, redirects."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from flask import current_app, request, url_for

from . import constants as C


def _tz():
    name = "Asia/Kolkata"
    try:
        name = current_app.config.get("APP_TIMEZONE", name)
    except RuntimeError:  # no app context
        pass
    try:
        return ZoneInfo(name)
    except Exception:  # tzdata missing (typical on Windows without `tzdata`)
        return timezone(timedelta(hours=5, minutes=30)) if name == "Asia/Kolkata" else timezone.utc


def now_local():
    """Naive datetime in the configured timezone. ALL stored datetimes use this convention."""
    return datetime.now(_tz()).replace(tzinfo=None, microsecond=0)


def password_error(password):
    """Return a message if the password is too weak, else None."""
    if password is None or len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password must be at most 128 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def is_safe_url(target):
    """Only allow same-host redirects (prevents open-redirect via ?next=)."""
    if not target or "\\" in target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def dashboard_url(user):
    return url_for(
        {C.DONOR: "donor.dashboard", C.RECIPIENT: "recipient.dashboard", C.ADMIN: "admin.dashboard"}[user.role]
    )


def register_template_helpers(app):
    @app.template_filter("dt")
    def dt_filter(value, fmt="%d %b %Y, %I:%M %p"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("qty")
    def qty_filter(value):
        if value is None:
            return "—"
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    @app.template_filter("timeleft")
    def timeleft_filter(deadline):
        secs = int((deadline - now_local()).total_seconds())
        if secs <= 0:
            return "Deadline passed"
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if days:
            return f"{days}d {hours}h left"
        if hours:
            return f"{hours}h {minutes}m left"
        return f"{minutes}m left"

    @app.template_filter("status_label")
    def status_label_filter(value):
        return C.STATUS_LABELS.get(value, value)

    @app.template_filter("hours_left")
    def hours_left_filter(deadline):
        return (deadline - now_local()).total_seconds() / 3600

    @app.context_processor
    def inject_globals():
        return {"constants": C, "now": now_local()}
