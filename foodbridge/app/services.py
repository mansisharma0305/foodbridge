"""Business rules: the ONLY place where listing/request status transitions happen.

Views call these functions; they raise WorkflowError (user-facing message) or
PermissionDenied (-> HTTP 403). Every state change is validated on the server.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import constants as C
from .extensions import db
from .models import Donation, DonationRequest, Report, User
from .utils import now_local


class WorkflowError(Exception):
    """A rule was violated; the message is safe to show to the user."""


class PermissionDenied(WorkflowError):
    """The acting user is not allowed to perform the action."""


def _commit():
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise WorkflowError("That change conflicts with another update. Please refresh and try again.")
    except SQLAlchemyError:
        db.session.rollback()
        raise WorkflowError("A database error occurred. Nothing was changed; please try again.")


# --------------------------------------------------------------------------- expiry
def expire_overdue(now=None):
    """Mark listings past their pickup deadline as expired (available/requested/approved)."""
    now = now or now_local()
    overdue = db.session.execute(
        select(Donation).where(
            Donation.status.in_([C.D_AVAILABLE, C.D_REQUESTED, C.D_APPROVED]),
            Donation.pickup_deadline < now,
        )
    ).scalars().all()
    if not overdue:
        return 0
    for donation in overdue:
        donation.status = C.D_EXPIRED
        for req in donation.requests:
            if req.status in (C.R_PENDING, C.R_APPROVED):
                req.status = C.R_EXPIRED
                req.expired_at = now
                req.response_note = "Pickup deadline passed."
    _commit()
    return len(overdue)


# --------------------------------------------------------------------------- donations
def update_donation(donation, actor, apply_fn):
    if actor.role != C.DONOR or donation.donor_id != actor.id:
        raise PermissionDenied("You can only edit your own listings.")
    if donation.status != C.D_AVAILABLE:
        raise WorkflowError("Only listings that are still available (no request yet) can be edited.")
    apply_fn(donation)
    _commit()


def cancel_donation(donation, actor):
    is_owner = actor.role == C.DONOR and donation.donor_id == actor.id
    if not (is_owner or actor.role == C.ADMIN):
        raise PermissionDenied("You cannot cancel this listing.")
    if donation.status not in C.DONATION_CANCELLABLE:
        raise WorkflowError(
            f"A listing that is {C.STATUS_LABELS.get(donation.status, donation.status).lower()} cannot be cancelled."
        )
    now = now_local()
    for req in donation.requests:
        if req.status in (C.R_PENDING, C.R_APPROVED):
            req.status = C.R_CANCELLED
            req.cancelled_at = now
            req.response_note = "Listing was cancelled by the donor." if is_owner else "Listing was removed by an administrator."
    donation.status = C.D_CANCELLED
    _commit()


# --------------------------------------------------------------------------- requests
def create_request(donation, recipient, note=""):
    if recipient.role != C.RECIPIENT:
        raise PermissionDenied("Only recipient accounts can request food.")
    now = now_local()
    if donation.status == C.D_EXPIRED or donation.pickup_deadline <= now:
        raise WorkflowError("This listing has expired and can no longer be requested.")
    if donation.status != C.D_AVAILABLE:
        raise WorkflowError("This listing is no longer available.")
    duplicate = db.session.execute(
        select(DonationRequest.id).where(
            DonationRequest.donation_id == donation.id,
            DonationRequest.recipient_id == recipient.id,
            DonationRequest.status != C.R_CANCELLED,
        )
    ).first()
    if duplicate:
        raise WorkflowError("You have already requested this listing.")
    req = DonationRequest(
        donation_id=donation.id, recipient_id=recipient.id,
        status=C.R_PENDING, note=(note or "").strip()[:300] or None,
    )
    donation.status = C.D_REQUESTED
    db.session.add(req)
    try:
        db.session.commit()
    except IntegrityError:  # unique index: someone else requested at the same moment
        db.session.rollback()
        raise WorkflowError("Another recipient just requested this listing.")
    except SQLAlchemyError:
        db.session.rollback()
        raise WorkflowError("A database error occurred. Please try again.")
    return req


# action -> (allowed current request statuses, new request status,
#            new donation status, who may do it, timestamp column)
ACTIONS = {
    "approve": ({C.R_PENDING}, C.R_APPROVED, C.D_APPROVED, "donor", "approved_at"),
    "reject": ({C.R_PENDING}, C.R_REJECTED, C.D_AVAILABLE, "donor", "rejected_at"),
    "cancel": ({C.R_PENDING, C.R_APPROVED}, C.R_CANCELLED, C.D_AVAILABLE, "recipient", "cancelled_at"),
    "collect": ({C.R_APPROVED}, C.R_COLLECTED, C.D_COLLECTED, "donor", "collected_at"),
    "complete": ({C.R_COLLECTED}, C.R_COMPLETED, C.D_COMPLETED, "either", "completed_at"),
}
ACTION_MESSAGES = {
    "approve": "Request approved. The recipient can now see the pickup details.",
    "reject": "Request rejected. The listing is available again.",
    "cancel": "Request cancelled.",
    "collect": "Marked as collected.",
    "complete": "Donation completed. Thank you for reducing food waste!",
}


def apply_action(req, action, actor, note=None):
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    allowed_from, new_req, new_don, who, ts_column = ACTIONS[action]
    donation = req.donation

    # 1) authorisation (server-side, before anything else)
    is_donor = actor.role == C.DONOR and donation.donor_id == actor.id
    is_recipient = actor.role == C.RECIPIENT and req.recipient_id == actor.id
    permitted = {"donor": is_donor, "recipient": is_recipient, "either": is_donor or is_recipient}[who]
    if not permitted:
        raise PermissionDenied("You are not allowed to perform this action.")

    # 2) valid state transition
    if req.status not in allowed_from:
        raise WorkflowError(
            f"This request is {C.STATUS_LABELS.get(req.status, req.status).lower()}; "
            f"you cannot {action} it at this stage."
        )

    now = now_local()
    if action in ("approve", "collect") and donation.pickup_deadline < now:
        expire_overdue(now)
        raise WorkflowError("The pickup deadline for this listing has passed, so it has expired.")

    req.status = new_req
    setattr(req, ts_column, now)
    if note:
        req.response_note = note.strip()[:300] or None
    # rejecting / cancelling re-opens the listing unless its deadline has already passed
    if new_don == C.D_AVAILABLE and donation.pickup_deadline < now:
        donation.status = C.D_EXPIRED
    else:
        donation.status = new_don
    _commit()
    return req


# --------------------------------------------------------------------------- queries
def donor_requests(donor_id, statuses):
    return db.session.execute(
        select(DonationRequest).join(Donation, DonationRequest.donation_id == Donation.id)
        .where(Donation.donor_id == donor_id, DonationRequest.status.in_(statuses))
        .order_by(DonationRequest.created_at.desc())
    ).scalars().all()


def donor_counts(donor_id):
    rows = dict(db.session.execute(
        select(Donation.status, func.count()).where(Donation.donor_id == donor_id).group_by(Donation.status)
    ).all())
    return {
        "total": sum(rows.values()),
        "active": sum(rows.get(s, 0) for s in (C.D_AVAILABLE, C.D_REQUESTED, C.D_APPROVED, C.D_COLLECTED)),
        "completed": rows.get(C.D_COMPLETED, 0),
        "expired_or_cancelled": rows.get(C.D_EXPIRED, 0) + rows.get(C.D_CANCELLED, 0),
    }


def recipient_counts(recipient_id):
    rows = dict(db.session.execute(
        select(DonationRequest.status, func.count())
        .where(DonationRequest.recipient_id == recipient_id).group_by(DonationRequest.status)
    ).all())
    return {
        "total": sum(rows.values()),
        "pending": rows.get(C.R_PENDING, 0),
        "approved": rows.get(C.R_APPROVED, 0) + rows.get(C.R_COLLECTED, 0),
        "completed": rows.get(C.R_COMPLETED, 0),
    }


def completed_by_unit(donor_id=None, recipient_id=None):
    """Completed donations grouped by unit. Units are NEVER summed together."""
    stmt = (
        select(Donation.unit, func.count(DonationRequest.id), func.coalesce(func.sum(Donation.quantity), 0.0))
        .select_from(Donation).join(DonationRequest, DonationRequest.donation_id == Donation.id)
        .where(DonationRequest.status == C.R_COMPLETED)
        .group_by(Donation.unit).order_by(Donation.unit)
    )
    if donor_id is not None:
        stmt = stmt.where(Donation.donor_id == donor_id)
    if recipient_id is not None:
        stmt = stmt.where(DonationRequest.recipient_id == recipient_id)
    return [{"unit": u, "count": c, "total": float(t)} for u, c, t in db.session.execute(stmt).all()]


def _last_months(n=6):
    today = now_local()
    year, month = today.year, today.month
    out = []
    for i in range(n - 1, -1, -1):
        m, y = month - i, year
        while m <= 0:
            m += 12
            y -= 1
        out.append((y, m))
    return out


def impact_summary():
    done = DonationRequest.status == C.R_COMPLETED
    by_unit = completed_by_unit()
    by_category = [
        {"category": cat, "count": cnt}
        for cat, cnt in db.session.execute(
            select(Donation.category, func.count(DonationRequest.id))
            .select_from(Donation).join(DonationRequest, DonationRequest.donation_id == Donation.id)
            .where(done).group_by(Donation.category).order_by(func.count(DonationRequest.id).desc())
        ).all()
    ]
    donors = db.session.execute(
        select(func.count(func.distinct(Donation.donor_id)))
        .select_from(Donation).join(DonationRequest, DonationRequest.donation_id == Donation.id).where(done)
    ).scalar() or 0
    recipients = db.session.execute(
        select(func.count(func.distinct(DonationRequest.recipient_id))).where(done)
    ).scalar() or 0
    completed_dates = db.session.execute(
        select(DonationRequest.completed_at).where(done, DonationRequest.completed_at.is_not(None))
    ).scalars().all()
    months = _last_months(6)
    monthly = {m: 0 for m in months}
    for d in completed_dates:
        if (d.year, d.month) in monthly:
            monthly[(d.year, d.month)] += 1
    active = db.session.execute(
        select(func.count()).select_from(Donation)
        .where(Donation.status == C.D_AVAILABLE, Donation.pickup_deadline > now_local())
    ).scalar() or 0
    has_sample = (db.session.execute(
        select(func.count()).select_from(Donation).where(Donation.is_sample.is_(True))
    ).scalar() or 0) > 0
    return {
        "completed_count": sum(u["count"] for u in by_unit),
        "by_unit": by_unit,
        "by_category": by_category,
        "donors": donors,
        "recipients": recipients,
        "active_listings": active,
        "monthly_labels": [datetime(y, m, 1).strftime("%b %Y") for y, m in months],
        "monthly_counts": [monthly[m] for m in months],
        "has_sample": has_sample,
    }


def admin_overview():
    users = dict(db.session.execute(select(User.role, func.count()).group_by(User.role)).all())
    inactive = db.session.execute(select(func.count()).select_from(User).where(User.active.is_(False))).scalar()
    listings = dict(db.session.execute(select(Donation.status, func.count()).group_by(Donation.status)).all())
    requests = dict(db.session.execute(
        select(DonationRequest.status, func.count()).group_by(DonationRequest.status)).all())
    listed_by_unit = [
        {"unit": u, "count": c, "total": float(t)}
        for u, c, t in db.session.execute(
            select(Donation.unit, func.count(), func.coalesce(func.sum(Donation.quantity), 0.0))
            .where(Donation.status != C.D_CANCELLED).group_by(Donation.unit).order_by(Donation.unit)
        ).all()
    ]
    open_reports = db.session.execute(
        select(func.count()).select_from(Report).where(Report.status == C.REPORT_OPEN)).scalar()
    return {
        "users": users, "inactive_users": inactive, "total_users": sum(users.values()),
        "listings": listings, "total_listings": sum(listings.values()),
        "requests": requests, "pending_requests": requests.get(C.R_PENDING, 0),
        "completed": listings.get(C.D_COMPLETED, 0),
        "listed_by_unit": listed_by_unit, "redistributed_by_unit": completed_by_unit(),
        "open_reports": open_reports,
    }
