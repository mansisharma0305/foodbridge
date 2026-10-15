import pytest

from app.models import Report, User
from tests.helpers import count, get_field, login, logged_in_client, make_user


@pytest.mark.parametrize("path", ["/donor/dashboard", "/donor/donations/new", "/recipient/dashboard",
                                  "/recipient/browse", "/admin/", "/admin/users", "/profile", "/report"])
def test_anonymous_users_are_redirected_to_login(client, path):
    resp = client.get(path)
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


@pytest.mark.parametrize("path", ["/", "/impact", "/food-safety", "/auth/login", "/auth/register"])
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_unknown_page_returns_friendly_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404 and b"Page not found" in resp.data


@pytest.mark.parametrize("role,forbidden", [
    ("donor", ["/recipient/dashboard", "/recipient/browse", "/admin/", "/admin/users", "/admin/reports"]),
    ("recipient", ["/donor/dashboard", "/donor/donations/new", "/admin/", "/admin/listings"]),
    ("admin", ["/donor/dashboard", "/donor/donations/new", "/recipient/dashboard", "/recipient/browse", "/report"]),
])
def test_wrong_role_gets_403(app, role, forbidden):
    client = logged_in_client(app, make_user(app, role))
    for path in forbidden:
        assert client.get(path).status_code == 403, path


def test_own_dashboards_load(app):
    for role, path in (("donor", "/donor/dashboard"), ("recipient", "/recipient/dashboard")):
        client = logged_in_client(app, make_user(app, role))
        resp = client.get(path)
        assert resp.status_code == 200 and b"No " in resp.data  # friendly empty state


# ---------------------------------------------------------------- admin dashboard
def test_admin_dashboard_and_pages_accessible_to_admin(app):
    client = logged_in_client(app, make_user(app, "admin"))
    for path in ("/admin/", "/admin/users", "/admin/listings", "/admin/requests", "/admin/reports"):
        assert client.get(path).status_code == 200, path
    assert b"Admin dashboard" in client.get("/admin/").data


def test_admin_dashboard_statistics(app):
    from tests.helpers import make_donation, make_request
    admin = make_user(app, "admin")
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    d1 = make_donation(app, donor.id, status="requested")
    make_request(app, d1, ngo.id, "pending")
    make_donation(app, donor.id, status="completed", unit="packets", quantity=7)
    html = logged_in_client(app, admin).get("/admin/").data.decode()
    assert "Total users" in html and "Pending requests" in html
    assert "7 packets" in html


def test_non_admin_cannot_use_admin_actions(app):
    donor = make_user(app, "donor")
    other = make_user(app, "recipient")
    client = logged_in_client(app, donor)
    assert client.post(f"/admin/users/{other.id}/toggle").status_code == 403
    assert client.post("/admin/reports/1/resolve", data={"decision": "resolved"}).status_code == 403


def test_admin_can_deactivate_user_but_not_admin(app):
    admin = make_user(app, "admin")
    donor = make_user(app, "donor")
    other_admin = make_user(app, "admin")
    client = logged_in_client(app, admin)
    assert client.post(f"/admin/users/{donor.id}/toggle").status_code == 302
    assert get_field(app, User, donor.id, "active") is False
    assert login(app.test_client(), donor).status_code == 200  # cannot log in any more
    client.post(f"/admin/users/{other_admin.id}/toggle")
    assert get_field(app, User, other_admin.id, "active") is True
    client.post(f"/admin/users/{donor.id}/toggle")
    assert get_field(app, User, donor.id, "active") is True


def test_report_submission_and_admin_resolution(app):
    admin, donor = make_user(app, "admin"), make_user(app, "donor")
    dclient = logged_in_client(app, donor)
    resp = dclient.post("/report", data={"category": "technical", "description": "The page was slow to load."})
    assert resp.status_code == 302 and count(app, Report) == 1
    assert dclient.post("/report", data={"category": "", "description": "short"}).status_code == 200

    aclient = logged_in_client(app, admin)
    assert b"The page was slow" in aclient.get("/admin/reports").data
    resp = aclient.post("/admin/reports/1/resolve", data={"decision": "resolved", "admin_note": "Looked into it"})
    assert resp.status_code == 302
    assert get_field(app, Report, 1, "status") == "resolved"
    assert aclient.post("/admin/reports/1/resolve", data={"decision": "bogus"}).status_code == 400
