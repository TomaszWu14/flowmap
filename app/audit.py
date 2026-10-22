"""Audit trail of security-relevant events, shown in the admin panel."""

from flask import has_request_context, request
from flask_login import current_user

from .extensions import db
from .models import AuditEvent

ACTIONS = {
    "login": "Logowanie",
    "login_failed": "Nieudane logowanie",
    "login_blocked": "Logowanie zablokowanego konta",
    "logout": "Wylogowanie",
    "register": "Rejestracja",
    "password_reset_requested": "Prośba o reset hasła",
    "password_reset": "Reset hasła",
    "user_blocked": "Zablokowanie konta",
    "user_unblocked": "Odblokowanie konta",
    "admin_granted": "Nadanie admina",
    "admin_revoked": "Odebranie admina",
    "settings_changed": "Zmiana ustawień",
    "project_created": "Nowy projekt",
    "project_deleted": "Usunięcie projektu",
    "exercise_started": "Rozpoczęcie ćwiczenia",
    "project_shared": "Udostępnienie projektu",
    "member_added": "Dodanie współpracownika",
    "member_removed": "Usunięcie współpracownika",
    "member_role_changed": "Zmiana roli współpracownika",
    "share_link_disabled": "Wyłączenie linku publicznego",
    "ai_error": "Błąd AI",
}


def log(action: str, target: str = "", actor=None, email: str | None = None) -> None:
    """Add an event to the session (committed together with the caller's change)."""
    if actor is None and has_request_context() and current_user.is_authenticated:
        actor = current_user
    db.session.add(AuditEvent(
        action=action,
        actor_id=actor.id if actor is not None else None,
        actor_email=(email or (actor.email if actor is not None else ""))[:255],
        target=target[:300],
        ip=(request.remote_addr or "")[:64] if has_request_context() else "",
    ))
