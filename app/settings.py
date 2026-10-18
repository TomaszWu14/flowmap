"""Runtime settings editable in the admin panel. Env vars give the defaults; a DB row overrides them."""

from flask import current_app

from .extensions import db
from .models import AppSetting

DEFAULTS = {
    "allow_signup": ("ALLOW_SIGNUP", bool),
    "ai_daily_limit": ("AI_DAILY_LIMIT", int),
    "ai_enabled": (None, bool),  # kill switch; AI still needs ANTHROPIC_API_KEY
}


def get(name: str):
    row = db.session.get(AppSetting, name)
    if row is not None:
        return row.value
    env_key, _type = DEFAULTS[name]
    return current_app.config[env_key] if env_key else True


def set_value(name: str, value) -> None:
    _env, type_ = DEFAULTS[name]
    row = db.session.get(AppSetting, name) or AppSetting(key=name)
    row.value = type_(value)
    db.session.add(row)


def signup_open() -> bool:
    return bool(get("allow_signup"))


def ai_daily_limit() -> int:
    return int(get("ai_daily_limit"))
