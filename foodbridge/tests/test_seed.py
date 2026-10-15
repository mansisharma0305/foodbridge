import pytest

from app.extensions import db
from app.models import Donation, DonationRequest, User
from app.seed import DEMO_PASSWORD, seed_demo
from tests.helpers import login, make_user, Account


def test_seed_creates_labelled_sample_data(app):
    with app.app_context():
        summary = seed_demo()
        assert summary["users"] == 6 and summary["donations"] > 10
        assert db.session.query(User).filter_by(role="admin").count() == 0  # admin is never seeded
        assert db.session.query(User).filter_by(is_sample=False).count() == 0
        assert db.session.query(Donation).filter_by(is_sample=False).count() == 0
        statuses = {d.status for d in db.session.query(Donation)}
        assert {"available", "requested", "approved", "collected", "completed", "expired", "cancelled"} <= statuses
        with pytest.raises(RuntimeError):
            seed_demo()
        seed_demo(reset=True)
        assert db.session.query(User).count() == 6
    assert login(app.test_client(), Account(0, "donor1@demo.foodbridge.test"), DEMO_PASSWORD).status_code == 302


def test_seed_reset_keeps_real_users(app):
    real = make_user(app, "donor", email="real@example.com")
    with app.app_context():
        seed_demo()
        seed_demo(reset=True)
        assert db.session.query(User).filter_by(email="real@example.com").count() == 1
        assert db.session.query(DonationRequest).count() > 0


def test_landing_page_flags_sample_data(app, client):
    with app.app_context():
        seed_demo()
    html = client.get("/").data.decode()
    assert "Sample" in html and "Live impact" in html
    assert b"Sample" in client.get("/impact").data
