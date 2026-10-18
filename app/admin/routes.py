"""Administrator panel: stats and user management. Project contents stay private to their owners."""

from datetime import date, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from .. import audit, settings
from ..auth.tokens import make_reset_token
from ..extensions import db
from ..models import AuditEvent, Project, QuestionLog, User, utcnow

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    """Non-admins get 404, so the panel does not reveal it exists."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(404)
        return view(*args, **kwargs)
    return wrapper


@bp.get("/")
@admin_required
def index():
    week_ago = utcnow() - timedelta(days=7)
    project_counts = dict(db.session.query(Project.owner_id, func.count(Project.id)).group_by(Project.owner_id).all())
    users = User.query.order_by(User.created_at.desc()).all()
    stats = {
        "users": len(users),
        "users_new": sum(1 for u in users if u.created_at >= week_ago),
        "blocked": sum(1 for u in users if u.is_blocked),
        "projects": Project.query.count(),
        "projects_complete": Project.query.filter_by(status="complete").count(),
        "projects_new": Project.query.filter(Project.created_at >= week_ago).count(),
        "answers": QuestionLog.query.filter(QuestionLog.answer != "").count(),
        "ai_today": sum(u.ai_usage_count for u in users if u.ai_usage_date == date.today()),
    }
    config = {
        "ai_key": bool(current_app.config["ANTHROPIC_API_KEY"]),
        "ai_enabled": bool(settings.get("ai_enabled")),
        "model": current_app.config["ANTHROPIC_MODEL"],
        "ai_limit": settings.ai_daily_limit(),
        "signup": settings.signup_open(),
        "env": current_app.config["APP_ENV"],
    }
    return render_template("admin/index.html", users=users, stats=stats, config_info=config,
                           project_counts=project_counts, today=date.today())


@bp.get("/zdarzenia")
@admin_required
def events():
    action = request.args.get("action", "")
    q = (request.args.get("q") or "").strip().lower()
    query = AuditEvent.query
    if action in audit.ACTIONS:
        query = query.filter_by(action=action)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AuditEvent.actor_email.ilike(like), AuditEvent.target.ilike(like)))
    rows = query.order_by(AuditEvent.id.desc()).limit(300).all()
    return render_template("admin/events.html", rows=rows, actions=audit.ACTIONS, action=action, q=q)


@bp.post("/settings")
@admin_required
def save_settings():
    limit = request.form.get("ai_daily_limit", type=int)
    if limit is None or not 0 <= limit <= 10000:
        flash("Limit AI musi być liczbą od 0 do 10000.", "error")
        return redirect(url_for("admin.index"))
    settings.set_value("allow_signup", request.form.get("allow_signup") == "on")
    settings.set_value("ai_enabled", request.form.get("ai_enabled") == "on")
    settings.set_value("ai_daily_limit", limit)
    summary = f"rejestracja={settings.signup_open()}, ai={settings.get('ai_enabled')}, limit={limit}"
    audit.log("settings_changed", summary)
    db.session.commit()
    flash("Ustawienia zapisane.", "success")
    return redirect(url_for("admin.index"))


def _target(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("Nie możesz zmieniać uprawnień ani blokady własnego konta.", "error")
        return None
    return user


@bp.post("/users/<int:user_id>/reset-link")
@admin_required
def reset_link(user_id):
    """One-time 24h reset link to hand over manually (works without e-mail)."""
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    link = url_for("auth.reset_password", token=make_reset_token(user, 24), _external=True)
    audit.log("password_reset_requested", f"{user.email} (link od admina)")
    db.session.commit()
    flash(f"Link do ustawienia hasła dla {user.email} (ważny 24 h, jednorazowy): {link}", "info")
    return redirect(url_for("admin.index"))


@bp.post("/users/<int:user_id>/<action>")
@admin_required
def user_action(user_id, action):
    if action not in ("block", "unblock", "grant-admin", "revoke-admin"):
        abort(404)
    user = _target(user_id)
    if user is not None:
        if action in ("block", "unblock"):
            user.is_blocked = action == "block"
        else:
            user.is_admin = action == "grant-admin"
        audit.log({"block": "user_blocked", "unblock": "user_unblocked", "grant-admin": "admin_granted",
                   "revoke-admin": "admin_revoked"}[action], user.email)
        db.session.commit()
        messages = {
            "block": "zablokowane", "unblock": "odblokowane",
            "grant-admin": "ma teraz uprawnienia administratora", "revoke-admin": "nie jest już administratorem",
        }
        flash(f"Konto {user.email} {messages[action]}.", "success")
    return redirect(url_for("admin.index"))
