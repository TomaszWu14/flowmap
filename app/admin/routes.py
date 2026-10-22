"""Administrator panel: stats and user management. Project contents stay private to their owners."""

from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from .. import audit, settings
from ..ai.client import month_cost_usd
from ..ai.pricing import FEATURES, PRICES
from ..auth.tokens import make_reset_token
from ..extensions import db
from ..models import AiUsage, AuditEvent, Project, QuestionLog, User, utcnow
from ..text import warsaw_midnight_utc, warsaw_today

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
        "ai_today": sum(u.ai_usage_count for u in users if u.ai_usage_date == warsaw_today()),
        "ai_cost_30d": _cost_since(utcnow() - timedelta(days=30))[1],
    }
    config = {
        "ai_key": bool(current_app.config["ANTHROPIC_API_KEY"]),
        "ai_enabled": bool(settings.get("ai_enabled")),
        "model": settings.get("ai_model"),
        "chat_model": settings.get("ai_chat_model"),
        "models": list(PRICES),
        "ai_limit": settings.ai_daily_limit(),
        "budget": settings.ai_monthly_budget(),
        "month_cost": month_cost_usd(),
        "signup": settings.signup_open(),
        "env": current_app.config["APP_ENV"],
    }
    ai_error = AuditEvent.query.filter(AuditEvent.action == "ai_error", AuditEvent.created_at >= utcnow() - timedelta(
        days=1)).order_by(AuditEvent.created_at.desc()).first()
    return render_template("admin/index.html", users=users, stats=stats, config_info=config,
                           project_counts=project_counts, today=warsaw_today(), ai_error=ai_error)


def _cost_since(since):
    """(calls, cost in USD) of AI calls made since the given moment."""
    calls, cost = db.session.query(func.count(AiUsage.id), func.sum(AiUsage.cost_usd)).filter(
        AiUsage.created_at >= since).one()
    return calls, cost or 0.0


@bp.get("/koszty")
@admin_required
def costs():
    now = utcnow()
    month = now - timedelta(days=30)
    periods = [(label, *_cost_since(since)) for label, since in (
        ("Dziś", warsaw_midnight_utc(warsaw_today())), ("7 dni", now - timedelta(days=7)),
        ("Ten miesiąc", warsaw_midnight_utc(warsaw_today().replace(day=1))), ("30 dni", month),
        ("Od początku", now.replace(year=2000)))]
    by_feature = (db.session.query(AiUsage.feature, func.count(AiUsage.id), func.sum(AiUsage.input_tokens),
                                   func.sum(AiUsage.output_tokens), func.sum(AiUsage.cost_usd))
                  .filter(AiUsage.created_at >= month).group_by(AiUsage.feature)
                  .order_by(func.sum(AiUsage.cost_usd).desc()).all())
    by_user = (db.session.query(User.email, func.count(AiUsage.id), func.sum(AiUsage.cost_usd))
               .outerjoin(User, AiUsage.user_id == User.id).filter(AiUsage.created_at >= month)
               .group_by(User.email).order_by(func.sum(AiUsage.cost_usd).desc()).limit(20).all())
    unpriced = AiUsage.query.filter(AiUsage.cost_usd.is_(None)).count()
    return render_template("admin/costs.html", periods=periods, by_feature=by_feature, by_user=by_user,
                           features=FEATURES, prices=PRICES, unpriced=unpriced,
                           model=settings.get("ai_model"), chat_model=settings.get("ai_chat_model"),
                           budget=settings.ai_monthly_budget())


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
    budget = request.form.get("ai_monthly_budget", settings.ai_monthly_budget(), type=float)
    models = {k: request.form.get(k, settings.get(k)) for k in ("ai_model", "ai_chat_model")}
    error = ("Limit AI musi być liczbą od 0 do 10000." if limit is None or not 0 <= limit <= 10000 else
             "Budżet musi być kwotą od 0 do 10000 USD." if budget is None or not 0 <= budget <= 10000 else
             "Wybierz model z cennika." if any(m not in PRICES for m in models.values()) else None)
    if error:
        flash(error, "error")
        return redirect(url_for("admin.index"))
    settings.set_value("allow_signup", request.form.get("allow_signup") == "on")
    settings.set_value("ai_enabled", request.form.get("ai_enabled") == "on")
    settings.set_value("ai_daily_limit", limit)
    settings.set_value("ai_monthly_budget", budget)
    for key, value in models.items():
        settings.set_value(key, value)
    summary = (f"rejestracja={settings.signup_open()}, ai={settings.get('ai_enabled')}, limit={limit}, "
               f"budżet=${budget:g}, model={models['ai_model']}, czat={models['ai_chat_model']}")
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
    # nosemgrep: flask-url-for-external-true — host from proxy (Traefik); fixed public URL: open decision
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
