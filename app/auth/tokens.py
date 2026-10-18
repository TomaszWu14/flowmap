"""Signed, expiring password-reset tokens. A token dies as soon as the password changes."""

from datetime import UTC, datetime

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

from ..extensions import db
from ..models import User

SALT = "password-reset"
MAX_HOURS = 72


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def make_reset_token(user: User, hours: int) -> str:
    # validity lives inside the signed payload, so it cannot be extended from the URL
    return _serializer().dumps({"uid": user.id, "ph": user.password_hash[-12:], "h": min(hours, MAX_HOURS)})


def user_from_token(token: str) -> User | None:
    try:
        data, issued = _serializer().loads(token, max_age=MAX_HOURS * 3600, return_timestamp=True)
    except BadSignature:  # includes SignatureExpired
        return None
    if (datetime.now(UTC) - issued).total_seconds() > int(data.get("h", 1)) * 3600:
        return None
    user = db.session.get(User, data.get("uid"))
    if user is None or user.is_blocked or user.password_hash[-12:] != data.get("ph"):
        return None
    return user
