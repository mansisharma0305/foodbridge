from datetime import timedelta

import pytest

from app import services
from app.extensions import db
from app.models import Donation, DonationRequest, User
from app.utils import now_local
from sqlalchemy.exc import IntegrityError
from tests.helpers import (count, get_field, logged_in_client, make_donation, make_request, make_user)


@pytest.fixture
def world(app):
    donor, other_donor = make_user(app, "donor"), make_user(app, "donor")
    ngo, ngo2 = make_user(app, "recipient"), make_user(app, "recipient")
    admin = make_user(app, "admin")
    did = make_donation(app, donor.id)
    return {
        "app": app, "donor": donor, "other_donor": other_donor, "ngo": ngo, "ngo2": ngo2, "admin": admin, "did": did,
        "dc": logged_in_client(app, donor), "odc": logged_in_client(app, other_donor),
        "nc": logged_in_client(app, ngo), "nc2": logged_in_client(app, ngo2), "ac": logged_in_client(app, admin),
    }


def dstatus(w, did=None):
    return get_field(w["app"], Donation, did or w["did"], "status")


def rstatus(w, rid=1):
    return get_field(w["app"], DonationRequest, rid, "status")


def request_food(w, client="nc", **kw):
    return w[client].post(f"/recipient/listings/{w['did']}/request", data={"note": "We can collect"}, **kw)


# ---------------------------------------------------------------- requesting
def test_recipient_requests_available_listing(world):
    resp = request_food(world)
    assert resp.status_code == 302 and "/recipient/requests/1" in resp.headers["Location"]
    assert rstatus(world) == "pending" and dstatus(world) == "requested"


def test_duplicate_request_by_same_recipient_blocked(world):
    request_food(world)
    resp = request_food(world, follow_redirects=True)
    assert b"no longer available" in resp.data or b"already requested" in resp.data
    assert count(world["app"], DonationRequest) == 1


def test_second_recipient_cannot_request_requested_listing(world):
    request_food(world)
    resp = request_food(world, "nc2", follow_redirects=True)
    assert b"no longer available" in resp.data
    assert count(world["app"], DonationRequest) == 1


def test_rejected_recipient_cannot_rerequest_but_cancelled_can(world):
    request_food(world)
    world["dc"].post("/donor/requests/1/reject")
    assert rstatus(world) == "rejected" and dstatus(world) == "available"
    resp = request_food(world, follow_redirects=True)
    assert b"already requested" in resp.data
    request_food(world, "nc2")  # a different recipient may request
    world["nc2"].post("/recipient/requests/2/cancel")
    assert rstatus(world, 2) == "cancelled" and dstatus(world) == "available"
    request_food(world, "nc2")  # cancelling frees the recipient to request again
    assert count(world["app"], DonationRequest) == 3


def test_donor_and_admin_cannot_request_food(world):
    assert world["dc"].post(f"/recipient/listings/{world['did']}/request").status_code == 403
    assert world["ac"].post(f"/recipient/listings/{world['did']}/request").status_code == 403


@pytest.mark.parametrize("status", ["cancelled", "completed", "collected", "approved"])
def test_unavailable_listings_cannot_be_requested(world, status):
    did = make_donation(world["app"], world["donor"].id, status=status)
    resp = world["nc"].post(f"/recipient/listings/{did}/request", follow_redirects=True)
    assert b"no longer available" in resp.data
    assert count(world["app"], DonationRequest) == 0


def test_expired_listing_cannot_be_requested(world):
    did = make_donation(world["app"], world["donor"].id, pickup_deadline=now_local() - timedelta(minutes=30))
    resp = world["nc"].post(f"/recipient/listings/{did}/request", follow_redirects=True)
    assert b"has expired" in resp.data
    assert count(world["app"], DonationRequest) == 0
    assert dstatus(world, did) == "expired"


# ---------------------------------------------------------------- approve / reject
def test_approve_request(world):
    request_food(world)
    assert world["dc"].post("/donor/requests/1/approve").status_code == 302
    assert rstatus(world) == "approved" and dstatus(world) == "approved"
    assert get_field(world["app"], DonationRequest, 1, "approved_at") is not None


def test_reject_request_reopens_listing(world):
    request_food(world)
    world["dc"].post("/donor/requests/1/reject", data={"note": "Not suitable"})
    assert rstatus(world) == "rejected" and dstatus(world) == "available"
    assert get_field(world["app"], DonationRequest, 1, "response_note") == "Not suitable"


# ---------------------------------------------------------------- unauthorised changes
def test_unauthorised_status_changes_are_forbidden(world):
    request_food(world)
    # wrong donor, recipient on donor route, admin, anonymous
    assert world["odc"].post("/donor/requests/1/approve").status_code == 403
    assert world["nc"].post("/donor/requests/1/approve").status_code == 403
    assert world["ac"].post("/donor/requests/1/approve").status_code == 403
    anon = world["app"].test_client().post("/donor/requests/1/approve")
    assert anon.status_code == 302 and "/auth/login" in anon.headers["Location"]
    # another recipient cannot cancel or complete someone else's request
    assert world["nc2"].post("/recipient/requests/1/cancel").status_code == 403
    assert world["nc2"].post("/recipient/requests/1/complete").status_code == 403
    assert world["nc2"].get("/recipient/requests/1").status_code == 403
    assert world["odc"].get(f"/donor/donations/{world['did']}").status_code == 403
    assert rstatus(world) == "pending" and dstatus(world) == "requested"


def test_recipient_cannot_use_donor_only_actions(world):
    request_food(world)
    world["dc"].post("/donor/requests/1/approve")
    assert world["nc"].post("/donor/requests/1/collect").status_code == 403
    assert world["nc"].post("/recipient/requests/1/collect").status_code == 404
    assert world["nc"].post("/recipient/requests/1/approve").status_code == 404
    assert rstatus(world) == "approved"


def test_invalid_state_transitions_rejected(world):
    request_food(world)
    r = world["dc"].post("/donor/requests/1/collect", follow_redirects=True)  # pending -> collect
    assert b"cannot collect it" in r.data and rstatus(world) == "pending"
    r = world["dc"].post("/donor/requests/1/complete", follow_redirects=True)
    assert rstatus(world) == "pending"
    world["dc"].post("/donor/requests/1/approve")
    r = world["dc"].post("/donor/requests/1/approve", follow_redirects=True)
    assert b"cannot approve it" in r.data
    r = world["dc"].post("/donor/requests/1/reject", follow_redirects=True)  # approved -> reject not allowed
    assert rstatus(world) == "approved"
    world["dc"].post("/donor/requests/1/collect")
    world["nc"].post("/recipient/requests/1/cancel")  # collected -> cancel not allowed
    assert rstatus(world) == "collected"


def test_state_changes_require_post(world):
    request_food(world)
    assert world["dc"].get("/donor/requests/1/approve").status_code == 405
    assert world["nc"].get("/recipient/requests/1/cancel").status_code == 405
    assert world["dc"].get(f"/donor/donations/{world['did']}/cancel").status_code == 405


# ---------------------------------------------------------------- collection & completion
def test_full_lifecycle_recipient_completes(world):
    request_food(world)
    world["dc"].post("/donor/requests/1/approve")
    world["dc"].post("/donor/requests/1/collect")
    assert rstatus(world) == "collected" and dstatus(world) == "collected"
    world["nc"].post("/recipient/requests/1/complete")
    assert rstatus(world) == "completed" and dstatus(world) == "completed"
    req = get_field(world["app"], DonationRequest, 1, "timeline")
    assert [label for label, _ in req] == ["Requested", "Approved", "Marked collected", "Completed"]
    assert b"Completed" in world["nc"].get("/recipient/requests/1").data


def test_donor_can_also_complete(world):
    request_food(world)
    for action in ("approve", "collect", "complete"):
        world["dc"].post(f"/donor/requests/1/{action}")
    assert dstatus(world) == "completed"


def test_recipient_cancels_approved_request(world):
    request_food(world)
    world["dc"].post("/donor/requests/1/approve")
    world["nc"].post("/recipient/requests/1/cancel")
    assert rstatus(world) == "cancelled" and dstatus(world) == "available"


# ---------------------------------------------------------------- expiry
def test_overdue_listings_and_requests_expire(world):
    app = world["app"]
    request_food(world)
    world["dc"].post("/donor/requests/1/approve")
    with app.app_context():
        db.session.get(Donation, world["did"]).pickup_deadline = now_local() - timedelta(minutes=1)
        db.session.commit()
        assert services.expire_overdue() == 1
    assert dstatus(world) == "expired" and rstatus(world) == "expired"
    assert world["dc"].post("/donor/requests/1/collect").status_code == 302
    assert rstatus(world) == "expired"  # cannot be collected after expiry


def test_approve_after_deadline_is_blocked_by_service(world):
    app = world["app"]
    request_food(world)
    with app.app_context():
        donation = db.session.get(Donation, world["did"])
        donation.pickup_deadline = now_local() - timedelta(minutes=1)
        req = db.session.get(DonationRequest, 1)
        donor = db.session.get(User, world["donor"].id)
        with pytest.raises(services.WorkflowError):
            services.apply_action(req, "approve", donor)
        db.session.rollback()


# ---------------------------------------------------------------- database-level guarantees
def test_database_allows_only_one_active_request_per_listing(world):
    app = world["app"]
    make_request(app, world["did"], world["ngo"].id, "pending")
    make_request(app, world["did"], world["ngo2"].id, "cancelled")  # inactive rows are fine
    with pytest.raises(IntegrityError):
        make_request(app, world["did"], world["ngo2"].id, "approved")


# ---------------------------------------------------------------- dashboards & impact
def test_dashboards_show_requests_and_statuses(world):
    request_food(world)
    html = world["dc"].get("/donor/dashboard").data.decode()
    assert "Requests waiting for your decision" in html and "Approve" in html
    html = world["nc"].get("/recipient/dashboard").data.decode()
    assert "Pending review" in html
    assert b"No " in world["nc"].get("/recipient/dashboard?status=rejected").data


def test_impact_never_mixes_units(world):
    app = world["app"]
    for qty, unit in ((10, "kg"), (5, "kg"), (20, "servings"), (4, "packets")):
        did = make_donation(app, world["donor"].id, quantity=qty, unit=unit, status="completed")
        make_request(app, did, world["ngo"].id, "completed", completed_at=now_local())
    with app.app_context():
        by_unit = {u["unit"]: (u["total"], u["count"]) for u in services.impact_summary()["by_unit"]}
        assert by_unit == {"kg": (15.0, 2), "servings": (20.0, 1), "packets": (4.0, 1)}
        assert services.impact_summary()["completed_count"] == 4
    html = world["app"].test_client().get("/impact").data.decode()
    assert "15" in html and "servings" in html and "packets" in html
