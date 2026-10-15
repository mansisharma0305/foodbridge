from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..forms import LoginForm, RegistrationForm
from ..models import User
from ..ratelimit import rate_limit
from ..utils import dashboard_url, is_safe_url
from . import bp


@bp.route("/register", methods=["GET", "POST"])
@rate_limit(10, 3600)
def register():
    if current_user.is_authenticated:
        return redirect(dashboard_url(current_user))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data, email=form.email.data,
            role=form.role.data,  # form only allows donor / recipient; admins are never self-registered
            organization=form.organization.data, org_type=form.org_type.data,
            phone=form.phone.data, city=form.city.data, address=form.address.data or None,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.email.errors.append("An account with this email already exists.")
        except SQLAlchemyError:
            db.session.rollback()
            flash("We could not create your account. Please try again.", "danger")
        else:
            flash("Account created. Please log in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@rate_limit(10, 300)
def login():
    if current_user.is_authenticated:
        return redirect(dashboard_url(current_user))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(select(User).where(User.email == form.email.data)).scalar_one_or_none()
        if user is None:
            User.burn_password_check(form.password.data)
        if user is not None and user.check_password(form.password.data):
            if not user.active:
                flash("This account has been deactivated. Please contact an administrator.", "warning")
            else:
                login_user(user, remember=form.remember.data)
                target = request.args.get("next")
                if target and is_safe_url(target):
                    return redirect(target)
                return redirect(dashboard_url(user))
        else:
            flash("Invalid email or password.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
