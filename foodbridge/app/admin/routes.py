from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from .. import constants as C
from .. import services
from ..decorators import roles_required
from ..extensions import db
from ..models import Donation, DonationRequest, Report, User
from ..utils import now_local
from . import bp


def _page(stmt):
    return db.paginate(
        stmt, page=request.args.get("page", 1, type=int),
        per_page=current_app.config["ITEMS_PER_PAGE"] + 5, error_out=False,
    )


def _args(*keys):
    return {k: request.args[k] for k in keys if request.args.get(k)}


@bp.route("/")
@roles_required(C.ADMIN)
def dashboard():
    overview = services.admin_overview()
    status_chart = {
        "labels": [C.STATUS_LABELS[s] for s in C.DONATION_STATUSES],
        "datasets": [{"label": "Listings", "data": [overview["listings"].get(s, 0) for s in C.DONATION_STATUSES]}],
    }
    recent_reports = db.session.execute(
        select(Report).where(Report.status == C.REPORT_OPEN).order_by(Report.created_at.desc()).limit(5)
    ).scalars().all()
    return render_template("admin/dashboard.html", o=overview, status_chart=status_chart, recent_reports=recent_reports)


@bp.route("/users")
@roles_required(C.ADMIN)
def users():
    role, q = request.args.get("role", ""), request.args.get("q", "").strip()
    stmt = select(User)
    if role in C.ROLES:
        stmt = stmt.where(User.role == role)
    if q:
        like = q.lower()
        stmt = stmt.where(or_(
            func.lower(User.email).contains(like, autoescape=True),
            func.lower(User.name).contains(like, autoescape=True),
            func.lower(func.coalesce(User.organization, "")).contains(like, autoescape=True),
        ))
    pagination = _page(stmt.order_by(User.created_at.desc()))
    return render_template("admin/users.html", pagination=pagination, role=role, q=q,
                           query_args=_args("role", "q"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@roles_required(C.ADMIN)
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.role == C.ADMIN:
        flash("Administrator accounts cannot be deactivated from the dashboard.", "warning")
    else:
        user.active = not user.active
        try:
            db.session.commit()
            flash(f"{user.display_name} is now {'active' if user.active else 'deactivated'}.", "success")
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not update the account.", "danger")
    return redirect(url_for("admin.users", **_args("role", "q")))


@bp.route("/listings")
@roles_required(C.ADMIN)
def listings():
    status, q = request.args.get("status", ""), request.args.get("q", "").strip()
    stmt = select(Donation)
    if status in C.DONATION_STATUSES:
        stmt = stmt.where(Donation.status == status)
    if q:
        stmt = stmt.where(func.lower(Donation.food_name).contains(q.lower(), autoescape=True))
    pagination = _page(stmt.order_by(Donation.created_at.desc()))
    return render_template("admin/listings.html", pagination=pagination, status=status, q=q,
                           query_args=_args("status", "q"))


@bp.route("/listings/<int:donation_id>/cancel", methods=["POST"])
@roles_required(C.ADMIN)
def cancel_listing(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    try:
        services.cancel_donation(donation, current_user)
        flash("Listing removed.", "info")
    except services.WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.listings"))


@bp.route("/requests")
@roles_required(C.ADMIN)
def requests_list():
    status = request.args.get("status", "")
    stmt = select(DonationRequest)
    if status in C.REQUEST_STATUSES:
        stmt = stmt.where(DonationRequest.status == status)
    pagination = _page(stmt.order_by(DonationRequest.created_at.desc()))
    return render_template("admin/requests.html", pagination=pagination, status=status, query_args=_args("status"))


@bp.route("/reports")
@roles_required(C.ADMIN)
def reports():
    status = request.args.get("status", C.REPORT_OPEN)
    stmt = select(Report)
    if status in C.REPORT_STATUSES:
        stmt = stmt.where(Report.status == status)
    pagination = _page(stmt.order_by(Report.created_at.desc()))
    return render_template("admin/reports.html", pagination=pagination, status=status, query_args={"status": status})


@bp.route("/reports/<int:report_id>/resolve", methods=["POST"])
@roles_required(C.ADMIN)
def resolve_report(report_id):
    report = db.get_or_404(Report, report_id)
    decision = request.form.get("decision")
    if decision not in (C.REPORT_RESOLVED, C.REPORT_DISMISSED):
        abort(400)
    report.status = decision
    report.admin_note = (request.form.get("admin_note") or "").strip()[:500] or None
    report.resolved_at = now_local()
    report.resolved_by_id = current_user.id
    try:
        db.session.commit()
        flash(f"Report marked as {decision}.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Could not update the report.", "danger")
    return redirect(url_for("admin.reports"))
