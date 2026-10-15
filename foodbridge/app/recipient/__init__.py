from flask import Blueprint

bp = Blueprint("recipient", __name__, url_prefix="/recipient")

from . import routes  # noqa: E402,F401
