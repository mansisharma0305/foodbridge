import pytest

from app import create_app
from app.extensions import db
from app.ratelimit import reset_rate_limits


@pytest.fixture
def app():
    """Fresh app + in-memory database per test. No app context is kept open, so each
    request gets its own context (like production); tests open short contexts via helpers."""
    reset_rate_limits()
    application = create_app("testing")
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
    reset_rate_limits()


@pytest.fixture
def client(app):
    return app.test_client()
