from datetime import timedelta

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .. import constants as C
from .. import services
from ..decorators import roles_required
from ..extensions import db
from ..forms import DonationForm
from ..models import Donation, DonationRequest
from ..utils import now_local
from . import bp


def _owned_donation_or_403(donation_id):
    donation = db.get_or_404(Donation, donation_id)
    if donation.donor_id != current_user.id:
        abort(403)
    return donation


@bp.route("/dashboard")
@roles_required(C.DONOR)
def dashboard():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    stmt = select(Donation).where(Donation.donor_id == current_user.id)
    if status in C.DONATION_STATUSES:
        stmt = stmt.where(Donation.status == status)
    pagination = db.paginate(
        stmt.order_by(Donation.created_at.desc()), page=page,
        per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False,
    )
    return render_template(
        "donor/dashboard.html",
        pagination=pagination, status=status,
        query_args={"status": status} if status else {},
        counts=services.donor_counts(current_user.id),
        pending=services.donor_requests(current_user.id, [C.R_PENDING]),
        approved=services.donor_requests(current_user.id, [C.R_APPROVED]),
        collected=services.donor_requests(current_user.id, [C.R_COLLECTED]),
        units=services.completed_by_unit(donor_id=current_user.id),
    )


@bp.route("/donations/new", methods=["GET", "POST"])
@roles_required(C.DONOR)
def new_donation():
    now = now_local().replace(second=0)
    form = DonationForm(data={
        "prepared_at": now, "pickup_deadline": now + timedelta(hours=4),
        "contact_phone": current_user.phone, "city": current_user.city,
        "pickup_location": current_user.address,
    })
    if form.validate_on_submit():
        donation = Donation(donor_id=current_user.id, status=C.D_AVAILABLE)
        form.apply_to(donation)
        db.session.add(donation)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Could not save donation")
            flash("We could not save your listing. Please try again.", "danger")
        else:
            flash("Your listing is now live for recipients.", "success")
            return redirect(url_for("donor.donation_detail", donation_id=donation.id))
    return render_template("donor/donation_form.html", form=form, editing=False)


@bp.route("/donations/<int:donation_id>")
@roles_required(C.DONOR)
def donation_detail(donation_id):
    donation = _owned_donation_or_403(donation_id)
    return render_template("donor/donation_detail.html", donation=donation)


@bp.route("/donations/<int:donation_id>/edit", methods=["GET", "POST"])
@roles_required(C.DONOR)
def edit_donation(donation_id):
    donation = _owned_donation_or_403(donation_id)
    if not donation.can_edit:
        flash("Only listings that are still available can be edited.", "warning")
        return redirect(url_for("donor.donation_detail", donation_id=donation.id))
    form = DonationForm(obj=donation)
    if request.method == "GET":
        form.safety_confirmed.data = False  # must be re-confirmed after changes
    if form.validate_on_submit():
        try:
            services.update_donation(donation, current_user, form.apply_to)
        except services.PermissionDenied:
            abort(403)
        except services.WorkflowError as exc:
            flash(str(exc), "danger")
        else:
            flash("Listing updated.", "success")
            return redirect(url_for("donor.donation_detail", donation_id=donation.id))
    return render_template("donor/donation_form.html", form=form, editing=True, donation=donation)


@bp.route("/donations/<int:donation_id>/cancel", methods=["POST"])
@roles_required(C.DONOR)
def cancel_donation(donation_id):
    donation = _owned_donation_or_403(donation_id)
    try:
        services.cancel_donation(donation, current_user)
        flash("Listing cancelled.", "info")
    except services.PermissionDenied:
        abort(403)
    except services.WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("donor.donation_detail", donation_id=donation.id))


@bp.route("/requests/<int:request_id>/<action>", methods=["POST"])
@roles_required(C.DONOR)
def request_action(request_id, action):
    if action not in ("approve", "reject", "collect", "complete"):
        abort(404)
    req = db.get_or_404(DonationRequest, request_id)
    try:
        services.apply_action(req, action, current_user, note=request.form.get("note"))
        flash(services.ACTION_MESSAGES[action], "success")
    except services.PermissionDenied:
        abort(403)
    except services.WorkflowError as exc:
        flash(str(exc), "danger")
    if request.form.get("return") == "detail":
        return redirect(url_for("donor.donation_detail", donation_id=req.donation_id))
    return redirect(url_for("donor.dashboard"))
