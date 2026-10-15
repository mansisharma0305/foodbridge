from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .. import constants as C
from .. import services
from ..decorators import roles_required
from ..extensions import db
from ..forms import ChangePasswordForm, ProfileForm, ReportForm
from ..models import Donation, Report
from ..ratelimit import rate_limit
from ..utils import dashboard_url, now_local
from . import bp


@bp.route("/")
def index():
    latest = db.session.execute(
        select(Donation).where(Donation.status == C.D_AVAILABLE, Donation.pickup_deadline > now_local())
        .order_by(Donation.created_at.desc()).limit(3)
    ).scalars().all()
    return render_template("index.html", stats=services.impact_summary(), latest=latest)


@bp.route("/impact")
def impact():
    return render_template("impact.html", stats=services.impact_summary())


@bp.route("/food-safety")
def food_safety():
    return render_template("food_safety.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(dashboard_url(current_user))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        for field in ("name", "organization", "org_type", "phone", "city", "address"):
            setattr(current_user, field, getattr(form, field).data or None)
        try:
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("main.profile"))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not save your profile. Please try again.", "danger")
    return render_template("profile.html", form=form)


@bp.route("/profile/password", methods=["GET", "POST"])
@login_required
@rate_limit(10, 600)
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(form.new_password.data)
            try:
                db.session.commit()
                flash("Password changed.", "success")
                return redirect(url_for("main.profile"))
            except SQLAlchemyError:
                db.session.rollback()
                flash("Could not change your password. Please try again.", "danger")
    return render_template("change_password.html", form=form)


@bp.route("/report", methods=["GET", "POST"])
@roles_required(C.DONOR, C.RECIPIENT)
@rate_limit(10, 3600)
def report():
    form = ReportForm()
    donation = None
    raw_id = request.args.get("donation_id") or form.donation_id.data
    if raw_id and str(raw_id).isdigit():
        donation = db.session.get(Donation, int(raw_id))
    if request.method == "GET" and donation:
        form.donation_id.data = str(donation.id)
    if form.validate_on_submit():
        db.session.add(Report(
            reporter_id=current_user.id, donation_id=donation.id if donation else None,
            category=form.category.data, description=form.description.data,
        ))
        try:
            db.session.commit()
            flash("Thank you. Your report was sent to the administrators.", "success")
            return redirect(url_for("main.dashboard"))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not submit your report. Please try again.", "danger")
    return render_template("report.html", form=form, donation=donation)
