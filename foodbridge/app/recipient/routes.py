from datetime import timedelta

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from .. import constants as C
from .. import services
from ..decorators import roles_required
from ..extensions import db
from ..forms import RequestForm, SearchForm
from ..models import Donation, DonationRequest
from ..utils import now_local
from . import bp


@bp.route("/dashboard")
@roles_required(C.RECIPIENT)
def dashboard():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    stmt = select(DonationRequest).where(DonationRequest.recipient_id == current_user.id)
    if status in C.REQUEST_STATUSES:
        stmt = stmt.where(DonationRequest.status == status)
    pagination = db.paginate(
        stmt.order_by(DonationRequest.created_at.desc()), page=page,
        per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False,
    )
    return render_template(
        "recipient/dashboard.html", pagination=pagination, status=status,
        query_args={"status": status} if status else {},
        counts=services.recipient_counts(current_user.id),
        units=services.completed_by_unit(recipient_id=current_user.id),
    )


@bp.route("/browse")
@roles_required(C.RECIPIENT)
def browse():
    form = SearchForm(formdata=request.args)
    now = now_local()
    valid = form.validate()
    availability = form.availability.data if valid else "available"
    stmt = select(Donation).where(Donation.pickup_deadline > now)
    if availability == "all":
        stmt = stmt.where(Donation.status.in_([C.D_AVAILABLE, C.D_REQUESTED]))
    elif availability == "expiring":
        stmt = stmt.where(Donation.status == C.D_AVAILABLE, Donation.pickup_deadline <= now + timedelta(hours=6))
    else:
        stmt = stmt.where(Donation.status == C.D_AVAILABLE)
    if valid:
        if form.q.data:
            stmt = stmt.where(func.lower(Donation.food_name).contains(form.q.data.lower(), autoescape=True))
        if form.category.data:
            stmt = stmt.where(Donation.category == form.category.data)
        if form.city.data:
            stmt = stmt.where(func.lower(Donation.city).contains(form.city.data.lower(), autoescape=True))
        if form.unit.data:
            stmt = stmt.where(Donation.unit == form.unit.data)
            if form.min_quantity.data:
                stmt = stmt.where(Donation.quantity >= form.min_quantity.data)
    newest = valid and form.sort.data == "newest"
    order = Donation.created_at.desc() if newest else Donation.pickup_deadline.asc()
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(
        stmt.order_by(order), page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False,
    )
    query_args = {k: v for k, v in request.args.items() if k != "page" and v != ""}
    return render_template("recipient/browse.html", form=form, pagination=pagination, query_args=query_args)


@bp.route("/listings/<int:donation_id>")
@roles_required(C.RECIPIENT)
def listing_detail(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    mine = db.session.execute(
        select(DonationRequest).where(
            DonationRequest.donation_id == donation.id, DonationRequest.recipient_id == current_user.id,
        ).order_by(DonationRequest.created_at.desc())
    ).scalars().first()
    if donation.status not in (C.D_AVAILABLE, C.D_REQUESTED, C.D_EXPIRED) and mine is None:
        abort(404)
    return render_template("recipient/listing_detail.html", donation=donation, form=RequestForm(), mine=mine)


@bp.route("/listings/<int:donation_id>/request", methods=["POST"])
@roles_required(C.RECIPIENT)
def request_food(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    form = RequestForm()
    if not form.validate_on_submit():
        flash("Your message is too long (maximum 300 characters).", "danger")
        return redirect(url_for("recipient.listing_detail", donation_id=donation.id))
    try:
        req = services.create_request(donation, current_user, form.note.data)
    except services.PermissionDenied:
        abort(403)
    except services.WorkflowError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("recipient.listing_detail", donation_id=donation.id))
    flash("Request sent. The donor will review it shortly.", "success")
    return redirect(url_for("recipient.request_detail", request_id=req.id))


@bp.route("/requests/<int:request_id>")
@roles_required(C.RECIPIENT)
def request_detail(request_id):
    req = db.get_or_404(DonationRequest, request_id)
    if req.recipient_id != current_user.id:
        abort(403)
    return render_template("recipient/request_detail.html", req=req, donation=req.donation)


@bp.route("/requests/<int:request_id>/<action>", methods=["POST"])
@roles_required(C.RECIPIENT)
def request_action(request_id, action):
    if action not in ("cancel", "complete"):
        abort(404)
    req = db.get_or_404(DonationRequest, request_id)
    try:
        services.apply_action(req, action, current_user)
        flash(services.ACTION_MESSAGES[action], "success")
    except services.PermissionDenied:
        abort(403)
    except services.WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("recipient.request_detail", request_id=req.id))
