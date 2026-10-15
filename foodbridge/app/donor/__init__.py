from flask import Blueprint

bp = Blueprint("donor", __name__, url_prefix="/donor")

from . import routes  # noqa: E402,F401
