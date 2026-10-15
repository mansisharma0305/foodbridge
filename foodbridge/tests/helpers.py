"""Test helpers. Data is created inside short-lived app contexts and returned as plain values."""
import itertools
from collections import namedtuple
from datetime import timedelta

from app.extensions import db
from app.models import Donation, DonationRequest, User
from app.utils import now_local

PASSWORD = "Passw0rd!"
DT_FMT = "%Y-%m-%dT%H:%M"
Account = namedtuple("Account", "id email")
_counter = itertools.count(1)


def make_user(app, role="donor", email=None, **overrides):
    email = email or f"{role}{next(_counter)}@example.com"
    fields = dict(
        name=f"{role.title()} Person", organization=f"{role.title()} Org {email.split('@')[0]}",
        org_type="NGO", phone="+91 90000 12345", city="Lucknow", address="1 Test Road",
    )
    fields.update(overrides)
    with app.app_context():
        user = User(email=email, role=role, **fields)
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return Account(user.id, email)


def make_donation(app, donor_id, **overrides):
    now = now_local()
    fields = dict(
        food_name="Test Rice", category="Cooked meals", quantity=10.0, unit="kg",
        description="Fresh", prepared_at=now - timedelta(hours=1),
        pickup_deadline=now + timedelta(hours=4), pickup_location="12 Private Lane",
        city="Lucknow", contact_phone="+91 90000 55555", handling_notes="Keep covered",
        status="available",
    )
    fields.update(overrides)
    with app.app_context():
        donation = Donation(donor_id=donor_id, **fields)
        db.session.add(donation)
        db.session.commit()
        return donation.id


def make_request(app, donation_id, recipient_id, status="pending", **overrides):
    with app.app_context():
        req = DonationRequest(donation_id=donation_id, recipient_id=recipient_id, status=status, **overrides)
        db.session.add(req)
        db.session.commit()
        return req.id


def login(client, account, password=PASSWORD, **kwargs):
    return client.post("/auth/login", data={"email": account.email, "password": password}, **kwargs)


def logged_in_client(app, account):
    client = app.test_client()
    resp = login(client, account)
    assert resp.status_code == 302, "test setup: login failed"
    return client


def get_field(app, model, pk, field):
    with app.app_context():
        return getattr(db.session.get(model, pk), field)


def count(app, model):
    with app.app_context():
        return db.session.query(model).count()


def donation_form_data(**overrides):
    now = now_local()
    data = {
        "food_name": "Vegetable pulao", "category": "Cooked meals", "quantity": "12.5", "unit": "servings",
        "description": "Freshly cooked", "prepared_at": (now - timedelta(hours=1)).strftime(DT_FMT),
        "pickup_deadline": (now + timedelta(hours=5)).strftime(DT_FMT),
        "pickup_location": "12 Market Road", "city": "Lucknow", "contact_phone": "+91 90000 11111",
        "handling_notes": "Keep covered", "safety_confirmed": "y",
    }
    data.update(overrides)
    return data


def registration_data(**overrides):
    data = {
        "role": "donor", "name": "Test Donor", "email": "new.user@example.com",
        "organization": "Test Kitchen", "org_type": "Restaurant", "phone": "+91 90000 22222",
        "city": "Lucknow", "address": "", "password": PASSWORD, "confirm": PASSWORD,
        "accept_guidance": "y",
    }
    data.update(overrides)
    return data
