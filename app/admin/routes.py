"""Administrator panel: stats and user management. Project contents stay private to their owners."""

from datetime import date, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import Project, QuestionLog, User, utcnow

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
        "ai": bool(current_app.config["ANTHROPIC_API_KEY"]),
        "model": current_app.config["ANTHROPIC_MODEL"],
        "ai_limit": current_app.config["AI_DAILY_LIMIT"],
        "signup": current_app.config["ALLOW_SIGNUP"],
        "env": current_app.config["APP_ENV"],
    }
    return render_template("admin/index.html", users=users, stats=stats, config_info=config,
                           project_counts=project_counts, today=date.today())


def _target(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("Nie możesz zmieniać uprawnień ani blokady własnego konta.", "error")
        return None
    return user


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
        db.session.commit()
        messages = {
            "block": "zablokowane", "unblock": "odblokowane",
            "grant-admin": "ma teraz uprawnienia administratora", "revoke-admin": "nie jest już administratorem",
        }
        flash(f"Konto {user.email} {messages[action]}.", "success")
    return redirect(url_for("admin.index"))
