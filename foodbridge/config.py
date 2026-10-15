"""Configuration. Secrets and environment-specific values come from environment variables."""
import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY")  # validated in create_app()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///foodbridge.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
    MAX_PICKUP_WINDOW_HOURS = _int("MAX_PICKUP_WINDOW_HOURS", 168)
    ITEMS_PER_PAGE = 9
    MAX_CONTENT_LENGTH = 1024 * 1024

    # Session / cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = APP_ENV == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    WTF_CSRF_ENABLED = True
    RATELIMIT_ENABLED = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


config_by_name = {
    "development": Config,
    "production": Config,
    "testing": TestingConfig,
}
