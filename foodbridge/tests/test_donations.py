from datetime import timedelta

import pytest

from app.models import Donation, DonationRequest
from app.utils import now_local
from tests.helpers import (count, donation_form_data, get_field, logged_in_client, make_donation,
                           make_request, make_user, DT_FMT)


# ---------------------------------------------------------------- create + validate
def test_donor_creates_valid_donation(app):
    donor = make_user(app, "donor")
    client = logged_in_client(app, donor)
    resp = client.post("/donor/donations/new", data=donation_form_data())
    assert resp.status_code == 302
    assert count(app, Donation) == 1
    assert get_field(app, Donation, 1, "status") == "available"
    assert get_field(app, Donation, 1, "donor_id") == donor.id
    assert get_field(app, Donation, 1, "quantity") == 12.5
    assert get_field(app, Donation, 1, "unit") == "servings"


def _times(prepared_delta, deadline_delta):
    now = now_local()
    return {"prepared_at": (now + prepared_delta).strftime(DT_FMT),
            "pickup_deadline": (now + deadline_delta).strftime(DT_FMT)}


@pytest.mark.parametrize("overrides,message", [
    ({"quantity": "0"}, b"Quantity must be between"),
    ({"quantity": "-5"}, b"Quantity must be between"),
    ({"quantity": ""}, b"Enter the quantity"),
    ({"unit": ""}, b"Please choose a unit"),
    ({"category": ""}, b"Please choose a category"),
    ({"category": "Weird"}, b"Not a valid choice"),
    ({"food_name": ""}, b"This field is required"),
    ({"contact_phone": "abc"}, b"valid phone number"),
    ({"safety_confirmed": ""}, b"You must confirm"),
    (_times(timedelta(hours=-3), timedelta(hours=-1)), b"must be in the future"),
    (_times(timedelta(minutes=3), timedelta(minutes=2)), b"after the preparation time"),
    (_times(timedelta(hours=2), timedelta(hours=5)), b"cannot be in the future"),
    (_times(timedelta(hours=-1), timedelta(hours=200)), b"cannot be more than 168 hours"),
])
def test_invalid_donations_are_rejected(app, overrides, message):
    client = logged_in_client(app, make_user(app, "donor"))
    resp = client.post("/donor/donations/new", data=donation_form_data(**overrides))
    assert resp.status_code == 200
    assert message in resp.data
    assert count(app, Donation) == 0


# ---------------------------------------------------------------- edit / cancel
def test_donor_can_edit_available_listing(app):
    donor = make_user(app, "donor")
    did = make_donation(app, donor.id)
    client = logged_in_client(app, donor)
    assert client.get(f"/donor/donations/{did}/edit").status_code == 200
    resp = client.post(f"/donor/donations/{did}/edit", data=donation_form_data(food_name="Updated pulao", quantity="30"))
    assert resp.status_code == 302
    assert get_field(app, Donation, did, "food_name") == "Updated pulao"
    assert get_field(app, Donation, did, "quantity") == 30


def test_edit_blocked_for_other_donor_and_after_request(app):
    donor, other = make_user(app, "donor"), make_user(app, "donor")
    did = make_donation(app, donor.id)
    assert logged_in_client(app, other).get(f"/donor/donations/{did}/edit").status_code == 403
    assert logged_in_client(app, other).post(f"/donor/donations/{did}/edit", data=donation_form_data()).status_code == 403
    locked = make_donation(app, donor.id, status="requested", food_name="Locked item")
    client = logged_in_client(app, donor)
    resp = client.post(f"/donor/donations/{locked}/edit", data=donation_form_data(food_name="Hacked"))
    assert resp.status_code == 302
    assert get_field(app, Donation, locked, "food_name") == "Locked item"


def test_cancel_listing_cancels_open_request(app):
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    did = make_donation(app, donor.id, status="requested")
    rid = make_request(app, did, ngo.id, "pending")
    client = logged_in_client(app, donor)
    assert client.post(f"/donor/donations/{did}/cancel").status_code == 302
    assert get_field(app, Donation, did, "status") == "cancelled"
    assert get_field(app, DonationRequest, rid, "status") == "cancelled"


def test_cancel_by_other_donor_forbidden_and_completed_not_cancellable(app):
    donor, other = make_user(app, "donor"), make_user(app, "donor")
    did = make_donation(app, donor.id)
    assert logged_in_client(app, other).post(f"/donor/donations/{did}/cancel").status_code == 403
    assert get_field(app, Donation, did, "status") == "available"
    done = make_donation(app, donor.id, status="completed")
    logged_in_client(app, donor).post(f"/donor/donations/{done}/cancel")
    assert get_field(app, Donation, done, "status") == "completed"


# ---------------------------------------------------------------- browse / search
@pytest.fixture
def browse_data(app):
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    now = now_local()
    make_donation(app, donor.id, food_name="Zebra Biryani", category="Cooked meals", city="Lucknow", unit="servings", quantity=50,
                  pickup_deadline=now + timedelta(hours=10))
    make_donation(app, donor.id, food_name="Quokka Bread", category="Bakery items", city="Varanasi", unit="pieces", quantity=10,
                  pickup_deadline=now + timedelta(hours=2))
    make_donation(app, donor.id, food_name="Expired Yak Stew", pickup_deadline=now - timedelta(hours=1))
    make_donation(app, donor.id, food_name="Cancelled Llama Soup", status="cancelled")
    make_donation(app, donor.id, food_name="Requested Emu Curry", status="requested")
    return logged_in_client(app, ngo)


def test_browse_shows_only_open_listings(browse_data):
    html = browse_data.get("/recipient/browse").data.decode()
    assert "Zebra Biryani" in html and "Quokka Bread" in html
    for hidden in ("Expired Yak Stew", "Cancelled Llama Soup", "Requested Emu Curry"):
        assert hidden not in html


def test_browse_search_and_filters(browse_data):
    def names(**params):
        html = browse_data.get("/recipient/browse", query_string=params).data.decode()
        return {n for n in ("Zebra Biryani", "Quokka Bread", "Requested Emu Curry") if n in html}
    assert names(q="BIRY") == {"Zebra Biryani"}
    assert names(category="Bakery items") == {"Quokka Bread"}
    assert names(city="varan") == {"Quokka Bread"}
    assert names(unit="servings", min_quantity="40") == {"Zebra Biryani"}
    assert names(unit="servings", min_quantity="60") == set()
    assert names(availability="expiring") == {"Quokka Bread"}
    assert names(availability="all") == {"Zebra Biryani", "Quokka Bread", "Requested Emu Curry"}
    assert names(q="%") == set()  # LIKE wildcards are escaped


def test_min_quantity_requires_unit(browse_data):
    html = browse_data.get("/recipient/browse", query_string={"min_quantity": "5"}).data.decode()
    assert "Choose a unit" in html and "Zebra Biryani" in html


def test_browse_pagination(app):
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    for i in range(11):
        make_donation(app, donor.id, food_name=f"Item {i:02d}")
    client = logged_in_client(app, ngo)
    assert client.get("/recipient/browse").data.count(b"View details") == 9
    assert client.get("/recipient/browse?page=2").data.count(b"View details") == 2


def test_contact_details_hidden_until_approved(app):
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    did = make_donation(app, donor.id, pickup_location="SECRET-ADDRESS-77", contact_phone="+91 99999 77777")
    client = logged_in_client(app, ngo)
    for path in ("/recipient/browse", f"/recipient/listings/{did}"):
        data = client.get(path).data
        assert b"SECRET-ADDRESS-77" not in data and b"99999 77777" not in data
    client.post(f"/recipient/listings/{did}/request", data={"note": "please"})
    rid = 1
    assert b"SECRET-ADDRESS-77" not in client.get(f"/recipient/requests/{rid}").data
    logged_in_client(app, donor).post(f"/donor/requests/{rid}/approve")
    data = client.get(f"/recipient/requests/{rid}").data
    assert b"SECRET-ADDRESS-77" in data and b"99999 77777" in data


def test_expired_listing_shows_notice(app):
    donor, ngo = make_user(app, "donor"), make_user(app, "recipient")
    did = make_donation(app, donor.id, pickup_deadline=now_local() - timedelta(hours=1))
    resp = logged_in_client(app, ngo).get(f"/recipient/listings/{did}")
    assert resp.status_code == 200 and b"This listing has expired" in resp.data
    assert get_field(app, Donation, did, "status") == "expired"
