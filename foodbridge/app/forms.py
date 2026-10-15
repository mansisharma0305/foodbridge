"""Flask-WTF forms. Every rule here is enforced server-side."""
from datetime import timedelta

from flask import current_app
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import (
    BooleanField, DateTimeLocalField, FloatField, HiddenField, PasswordField,
    SelectField, StringField, SubmitField, TextAreaField,
)
from wtforms.validators import (
    DataRequired, EqualTo, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError,
)

from . import constants as C
from .extensions import db
from .models import User
from .utils import now_local, password_error

DT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
PHONE = Regexp(r"^\+?[0-9][0-9\s\-]{6,18}[0-9]$", message="Enter a valid phone number (digits, spaces or dashes).")
EMAIL = Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address.")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _email(value):
    return value.strip().lower() if isinstance(value, str) else value


def _choices(values, blank=None):
    items = [(v, v) for v in values]
    return ([("", blank)] + items) if blank else items


class RegistrationForm(FlaskForm):
    role = SelectField("I want to", choices=C.SELF_REGISTER_ROLES, default=C.DONOR,
                       validators=[DataRequired(message="Choose how you will use FoodBridge.")])
    name = StringField("Your full name", [DataRequired(), Length(2, 100)], filters=[_strip])
    email = StringField("Email", [DataRequired(), Length(max=255), EMAIL], filters=[_email])
    organization = StringField("Organization / business name", [DataRequired(), Length(2, 150)], filters=[_strip])
    org_type = SelectField("Organization type", choices=_choices(C.ORG_TYPES, "Select type"), default="",
                           validators=[DataRequired(message="Please choose an organization type.")])
    phone = StringField("Phone number", [DataRequired(), PHONE], filters=[_strip])
    city = StringField("City / area", [DataRequired(), Length(2, 80)], filters=[_strip])
    address = StringField("Address (optional)", [Optional(), Length(max=255)], filters=[_strip])
    password = PasswordField("Password", [DataRequired(), Length(8, 128, message="Use 8 to 128 characters.")])
    confirm = PasswordField("Confirm password", [DataRequired(), EqualTo("password", message="Passwords do not match.")])
    accept_guidance = BooleanField(
        "I have read the food-safety guidance and understand FoodBridge is a coordination platform, "
        "not a food-safety certifier.",
        validators=[DataRequired(message="Please confirm to continue.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        if db.session.execute(select(User.id).where(User.email == field.data)).first():
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        problem = password_error(field.data)
        if problem:
            raise ValidationError(problem)


class LoginForm(FlaskForm):
    email = StringField("Email", [DataRequired(), Length(max=255)], filters=[_email])
    password = PasswordField("Password", [DataRequired()])
    remember = BooleanField("Keep me signed in on this device")
    submit = SubmitField("Log in")


class ProfileForm(FlaskForm):
    name = StringField("Your full name", [DataRequired(), Length(2, 100)], filters=[_strip])
    organization = StringField("Organization / business name", [DataRequired(), Length(2, 150)], filters=[_strip])
    org_type = SelectField("Organization type", choices=_choices(C.ORG_TYPES, "Select type"), default="",
                           validators=[DataRequired(message="Please choose an organization type.")])
    phone = StringField("Phone number", [DataRequired(), PHONE], filters=[_strip])
    city = StringField("City / area", [DataRequired(), Length(2, 80)], filters=[_strip])
    address = StringField("Address (optional)", [Optional(), Length(max=255)], filters=[_strip])
    submit = SubmitField("Save changes")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", [DataRequired()])
    new_password = PasswordField("New password", [DataRequired(), Length(8, 128, message="Use 8 to 128 characters.")])
    confirm = PasswordField("Confirm new password", [DataRequired(), EqualTo("new_password", message="Passwords do not match.")])
    submit = SubmitField("Change password")

    def validate_new_password(self, field):
        problem = password_error(field.data)
        if problem:
            raise ValidationError(problem)


class DonationForm(FlaskForm):
    food_name = StringField("Food item", [DataRequired(), Length(2, 120)], filters=[_strip])
    category = SelectField("Category", choices=_choices(C.CATEGORIES, "Select category"), default="",
                           validators=[DataRequired(message="Please choose a category.")])
    quantity = FloatField("Quantity", [
        InputRequired(message="Enter the quantity."),
        NumberRange(min=0.01, max=C.MAX_QUANTITY, message=f"Quantity must be between 0.01 and {C.MAX_QUANTITY:,}."),
    ])
    unit = SelectField("Unit", choices=_choices(C.UNITS, "Unit"), default="",
                       validators=[DataRequired(message="Please choose a unit.")])
    description = TextAreaField("Description (ingredients, packaging, allergens…)", [Optional(), Length(max=1000)], filters=[_strip])
    prepared_at = DateTimeLocalField("Prepared / acquired at", format=DT_FORMATS,
                                     validators=[DataRequired(message="Enter a valid date and time.")])
    pickup_deadline = DateTimeLocalField("Pickup deadline", format=DT_FORMATS,
                                         validators=[DataRequired(message="Enter a valid date and time.")])
    pickup_location = StringField("Exact pickup address", [DataRequired(), Length(5, 255)], filters=[_strip])
    city = StringField("Area / city (shown to all recipients)", [DataRequired(), Length(2, 80)], filters=[_strip])
    contact_phone = StringField("Contact phone for pickup", [DataRequired(), PHONE], filters=[_strip])
    handling_notes = TextAreaField("Handling / storage notes (e.g. keep refrigerated, consume within 4 hours)",
                                   [Optional(), Length(max=500)], filters=[_strip])
    safety_confirmed = BooleanField(
        "I confirm this food was prepared, stored and handled according to applicable local food-safety rules "
        "and is intended for safe consumption.",
        validators=[DataRequired(message="You must confirm this before posting food.")],
    )
    submit = SubmitField("Save listing")

    def validate_prepared_at(self, field):
        now = now_local()
        if field.data > now + timedelta(minutes=5):
            raise ValidationError("Preparation time cannot be in the future.")
        if field.data < now - timedelta(days=30):
            raise ValidationError("Preparation time cannot be more than 30 days ago.")

    def validate_pickup_deadline(self, field):
        now = now_local()
        if field.data <= now:
            raise ValidationError("The pickup deadline must be in the future.")
        prepared = self.prepared_at.data
        if prepared and field.data <= prepared:
            raise ValidationError("The pickup deadline must be after the preparation time.")
        max_hours = current_app.config["MAX_PICKUP_WINDOW_HOURS"]
        if field.data > now + timedelta(hours=max_hours):
            raise ValidationError(f"The pickup deadline cannot be more than {max_hours} hours from now.")

    def apply_to(self, donation):
        donation.food_name = self.food_name.data
        donation.category = self.category.data
        donation.quantity = self.quantity.data
        donation.unit = self.unit.data
        donation.description = self.description.data or None
        donation.prepared_at = self.prepared_at.data
        donation.pickup_deadline = self.pickup_deadline.data
        donation.pickup_location = self.pickup_location.data
        donation.city = self.city.data
        donation.contact_phone = self.contact_phone.data
        donation.handling_notes = self.handling_notes.data or None


class RequestForm(FlaskForm):
    note = TextAreaField("Message to the donor (optional)", [Optional(), Length(max=300)], filters=[_strip])
    submit = SubmitField("Request this food")


class SearchForm(FlaskForm):
    class Meta:
        csrf = False  # read-only GET filters

    q = StringField("Food name", [Optional(), Length(max=100)], filters=[_strip])
    category = SelectField("Category", choices=_choices(C.CATEGORIES, "All categories"), default="")
    city = StringField("Location", [Optional(), Length(max=80)], filters=[_strip])
    unit = SelectField("Unit", choices=_choices(C.UNITS, "Any unit"), default="")
    min_quantity = FloatField("Min. quantity", [Optional(), NumberRange(min=0, max=C.MAX_QUANTITY)])
    availability = SelectField("Availability", default="available", choices=[
        ("available", "Available now"), ("expiring", "Expiring within 6 hours"),
        ("all", "Available + already requested"),
    ])
    sort = SelectField("Sort by", default="deadline", choices=[("deadline", "Pickup deadline (soonest)"), ("newest", "Newest first")])

    def validate_min_quantity(self, field):
        if field.data not in (None, 0) and not self.unit.data:
            raise ValidationError("Choose a unit to filter by quantity (units are never mixed).")


class ReportForm(FlaskForm):
    category = SelectField("What is this about?", choices=[("", "Select a reason")] + C.REPORT_CATEGORIES, default="",
                           validators=[DataRequired(message="Please choose a reason.")])
    description = TextAreaField("Describe the issue", [DataRequired(), Length(10, 1000)], filters=[_strip])
    donation_id = HiddenField(validators=[Optional()])
    submit = SubmitField("Submit report")
