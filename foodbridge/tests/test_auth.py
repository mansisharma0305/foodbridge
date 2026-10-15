import pytest

from app import create_app
from app.extensions import db
from app.models import User
from tests.helpers import (PASSWORD, count, get_field, login, logged_in_client, make_user,
                           registration_data)


# ---------------------------------------------------------------- registration
def test_register_donor_success_and_password_is_hashed(app, client):
    resp = client.post("/auth/register", data=registration_data())
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/auth/login")
    with app.app_context():
        user = db.session.query(User).filter_by(email="new.user@example.com").one()
        assert user.role == "donor"
        assert user.password_hash != PASSWORD and PASSWORD not in user.password_hash
        assert user.check_password(PASSWORD) and not user.check_password("wrong-pass-1")


def test_register_recipient_success(app, client):
    resp = client.post("/auth/register", data=registration_data(role="recipient", email="ngo@example.com"))
    assert resp.status_code == 302
    assert get_field(app, User, 1, "role") == "recipient"


def test_register_email_is_normalised(app, client):
    client.post("/auth/register", data=registration_data(email="  MiXed@Example.COM "))
    with app.app_context():
        assert db.session.query(User).filter_by(email="mixed@example.com").count() == 1


def test_register_duplicate_email_rejected(app, client):
    make_user(app, "donor", email="dup@example.com")
    resp = client.post("/auth/register", data=registration_data(email="dup@example.com"))
    assert resp.status_code == 200
    assert b"already exists" in resp.data
    assert count(app, User) == 1


@pytest.mark.parametrize("overrides,message", [
    ({"password": "short1", "confirm": "short1"}, b"Use 8 to 128 characters"),
    ({"password": "onlyletters", "confirm": "onlyletters"}, b"at least one letter and one number"),
    ({"password": "12345678", "confirm": "12345678"}, b"at least one letter and one number"),
    ({"confirm": "Different1"}, b"Passwords do not match"),
    ({"email": "not-an-email"}, b"valid email"),
    ({"phone": "abc"}, b"valid phone number"),
    ({"org_type": ""}, b"choose an organization type"),
    ({"accept_guidance": ""}, b"Please confirm"),
])
def test_register_validation_errors(app, client, overrides, message):
    resp = client.post("/auth/register", data=registration_data(**overrides))
    assert resp.status_code == 200
    assert message in resp.data
    assert count(app, User) == 0


def test_cannot_register_as_admin(app, client):
    resp = client.post("/auth/register", data=registration_data(role="admin"))
    assert resp.status_code == 200
    assert count(app, User) == 0


# ---------------------------------------------------------------- login / logout
@pytest.mark.parametrize("role,target", [
    ("donor", "/donor/dashboard"), ("recipient", "/recipient/dashboard"), ("admin", "/admin/"),
])
def test_login_redirects_to_role_dashboard(app, client, role, target):
    account = make_user(app, role)
    resp = login(client, account)
    assert resp.status_code == 302 and resp.headers["Location"].endswith(target)


def test_invalid_password_is_rejected(app, client):
    account = make_user(app, "donor")
    resp = login(client, account, password="WrongPass1")
    assert resp.status_code == 200 and b"Invalid email or password" in resp.data
    assert client.get("/donor/dashboard").status_code == 302  # still anonymous


def test_unknown_email_gets_same_message(app, client):
    resp = client.post("/auth/login", data={"email": "ghost@example.com", "password": PASSWORD})
    assert resp.status_code == 200 and b"Invalid email or password" in resp.data


def test_deactivated_account_cannot_log_in(app, client):
    account = make_user(app, "donor", active=False)
    resp = login(client, account)
    assert resp.status_code == 200 and b"deactivated" in resp.data


def test_logout_requires_post_and_ends_session(app):
    account = make_user(app, "donor")
    client = logged_in_client(app, account)
    assert client.get("/auth/logout").status_code == 405
    assert client.get("/donor/dashboard").status_code == 200
    assert client.post("/auth/logout").status_code == 302
    assert client.get("/donor/dashboard").status_code == 302


def test_login_next_parameter_only_allows_local_redirects(app):
    account = make_user(app, "donor")
    ok = app.test_client().post("/auth/login?next=/impact", data={"email": account.email, "password": PASSWORD})
    assert ok.headers["Location"].endswith("/impact")
    for evil in ("https://evil.example/", "//evil.example/", "/\\evil.example"):
        resp = app.test_client().post("/auth/login", query_string={"next": evil},
                                      data={"email": account.email, "password": PASSWORD})
        assert "evil.example" not in resp.headers["Location"]


# ---------------------------------------------------------------- security controls
def test_csrf_is_enforced_when_enabled():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    client = app.test_client()
    resp = client.post("/auth/login", data={"email": "a@b.com", "password": "x"})
    assert resp.status_code == 400
    with app.app_context():
        db.drop_all()


def test_login_rate_limit():
    app = create_app("testing", {"RATELIMIT_ENABLED": True})
    client = app.test_client()
    for _ in range(10):
        assert client.post("/auth/login", data={"email": "a@b.com", "password": "x"}).status_code == 200
    assert client.post("/auth/login", data={"email": "a@b.com", "password": "x"}).status_code == 429
    from app.ratelimit import reset_rate_limits
    reset_rate_limits()
    with app.app_context():
        db.drop_all()


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


def test_session_cookie_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_production_requires_secret_key(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "SECRET_KEY", None)
    monkeypatch.setattr(Config, "APP_ENV", "production")
    with pytest.raises(RuntimeError):
        create_app("production", {"SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": None, "APP_ENV": "production"})


# ---------------------------------------------------------------- profile
def test_profile_update_and_password_change(app):
    account = make_user(app, "donor")
    client = logged_in_client(app, account)
    resp = client.post("/profile", data={
        "name": "New Name", "organization": "New Org", "org_type": "Hotel",
        "phone": "+91 91111 22222", "city": "Kanpur", "address": ""})
    assert resp.status_code == 302
    assert get_field(app, User, account.id, "city") == "Kanpur"

    bad = client.post("/profile/password", data={"current_password": "nope", "new_password": "NewPass123", "confirm": "NewPass123"})
    assert bad.status_code == 200 and b"Current password is incorrect" in bad.data
    good = client.post("/profile/password", data={"current_password": PASSWORD, "new_password": "NewPass123", "confirm": "NewPass123"})
    assert good.status_code == 302
    fresh = app.test_client()
    assert login(fresh, account, password="NewPass123").status_code == 302
    assert login(app.test_client(), account).status_code == 200  # old password fails


# ---------------------------------------------------------------- admin provisioning (CLI only)
def test_create_admin_cli(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--email", "boss@example.com", "--password", "Adm1nPass99"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        admin = db.session.query(User).filter_by(email="boss@example.com").one()
        assert admin.role == "admin" and admin.check_password("Adm1nPass99")
    weak = runner.invoke(args=["create-admin", "--email", "x@example.com", "--password", "weak"])
    assert weak.exit_code != 0
