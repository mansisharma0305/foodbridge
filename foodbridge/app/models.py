"""SQLAlchemy models: User, Donation, DonationRequest, Report."""
import sqlite3

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, event, text
from sqlalchemy.engine import Engine
from werkzeug.security import check_password_hash, generate_password_hash

from . import constants as C
from .extensions import db, login_manager
from .utils import now_local


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _in(column, values):
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


_ACTIVE_SQL = text(_in("status", C.ACTIVE_REQUEST_STATUSES))
_DUMMY_HASH = None


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", C.ROLES), name="ck_users_role"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    organization = db.Column(db.String(150))
    org_type = db.Column(db.String(50))
    phone = db.Column(db.String(25))
    city = db.Column(db.String(80))
    address = db.Column(db.String(255))
    active = db.Column(db.Boolean, nullable=False, default=True)
    is_sample = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)

    donations = db.relationship("Donation", back_populates="donor")
    requests = db.relationship("DonationRequest", back_populates="recipient")

    @property
    def is_active(self):  # Flask-Login: inactive accounts cannot log in
        return bool(self.active)

    @property
    def display_name(self):
        return self.organization or self.name

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def burn_password_check(password):
        """Spend comparable time when the email is unknown (reduces user-enumeration timing)."""
        global _DUMMY_HASH
        if _DUMMY_HASH is None:
            _DUMMY_HASH = generate_password_hash("not-a-real-password-1")
        check_password_hash(_DUMMY_HASH, password or "")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Donation(db.Model):
    __tablename__ = "donations"
    __table_args__ = (
        CheckConstraint(_in("status", C.DONATION_STATUSES), name="ck_donations_status"),
        CheckConstraint("quantity > 0", name="ck_donations_quantity_positive"),
        Index("ix_donations_status_deadline", "status", "pickup_deadline"),
    )

    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    food_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    prepared_at = db.Column(db.DateTime, nullable=False)
    pickup_deadline = db.Column(db.DateTime, nullable=False)
    pickup_location = db.Column(db.String(255), nullable=False)  # private until approved
    city = db.Column(db.String(80), nullable=False, index=True)  # public area
    contact_phone = db.Column(db.String(25), nullable=False)  # private until approved
    handling_notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=C.D_AVAILABLE)
    is_sample = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_local, onupdate=now_local)

    donor = db.relationship("User", back_populates="donations")
    requests = db.relationship(
        "DonationRequest", back_populates="donation",
        cascade="all, delete-orphan", order_by="DonationRequest.created_at",
    )

    @property
    def active_request(self):
        for req in self.requests:
            if req.status in C.ACTIVE_REQUEST_STATUSES:
                return req
        return None

    @property
    def is_past_deadline(self):
        return self.pickup_deadline < now_local()

    @property
    def can_edit(self):
        return self.status == C.D_AVAILABLE

    @property
    def can_cancel(self):
        return self.status in C.DONATION_CANCELLABLE

    def __repr__(self):
        return f"<Donation {self.id} {self.food_name} [{self.status}]>"


class DonationRequest(db.Model):
    __tablename__ = "donation_requests"
    __table_args__ = (
        CheckConstraint(_in("status", C.REQUEST_STATUSES), name="ck_requests_status"),
        # At most ONE active request per listing, enforced by the database itself.
        Index(
            "uq_one_active_request_per_donation", "donation_id", unique=True,
            sqlite_where=_ACTIVE_SQL, postgresql_where=_ACTIVE_SQL,
        ),
        Index("ix_requests_recipient_status", "recipient_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("donations.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=C.R_PENDING)
    note = db.Column(db.String(300))  # message from recipient
    response_note = db.Column(db.String(300))  # reason from donor / system
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    approved_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    expired_at = db.Column(db.DateTime)
    collected_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    donation = db.relationship("Donation", back_populates="requests")
    recipient = db.relationship("User", back_populates="requests")

    @property
    def timeline(self):
        events = [
            ("Requested", self.created_at), ("Approved", self.approved_at),
            ("Rejected", self.rejected_at), ("Marked collected", self.collected_at),
            ("Completed", self.completed_at), ("Cancelled", self.cancelled_at),
            ("Expired", self.expired_at),
        ]
        return sorted(((l, t) for l, t in events if t), key=lambda e: e[1])

    @property
    def contact_visible(self):
        return self.status in C.CONTACT_VISIBLE_STATUSES

    def __repr__(self):
        return f"<DonationRequest {self.id} donation={self.donation_id} [{self.status}]>"


class Report(db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(_in("status", C.REPORT_STATUSES), name="ck_reports_status"),
        Index("ix_reports_status", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    donation_id = db.Column(db.Integer, db.ForeignKey("donations.id", ondelete="SET NULL"))
    category = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=C.REPORT_OPEN)
    admin_note = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])
    donation = db.relationship("Donation")

    @property
    def category_label(self):
        return dict(C.REPORT_CATEGORIES).get(self.category, self.category)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
