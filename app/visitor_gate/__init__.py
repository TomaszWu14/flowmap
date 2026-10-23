"""Visitor gate: a polite, mandatory self-introduction before the public demo (soft visit control).

Stores only first name, last name and company (no IP, no user agent); records are deleted after 90 days.
Switched on with DEMO_VISITOR_GATE (default: only when APP_ENV=production).
"""

import time
import unicodedata
from datetime import timedelta
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Length, ValidationError

from ..admin.routes import admin_required
from ..extensions import db
from ..models import DemoVisitor, utcnow

bp = Blueprint("visitor_gate", __name__)

RETENTION_DAYS = 90
PASS_DAYS = 30
SESSION_KEY = "visitor_ok"
EXEMPT_ENDPOINTS = {"healthz", "static", "visitor_gate.gate", "visitor_gate.visitors"}


def _clean_text(form, field):
    value = field.data or ""
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ValidationError("Usuń znaki specjalne.")


def _trim(value):
    return value.strip() if isinstance(value, str) else value


def _name_field(label):
    return StringField(label, filters=[_trim], validators=[
        DataRequired(message="To pole jest wymagane."),
        Length(min=2, max=100, message="Wpisz od 2 do 100 znaków."),
        _clean_text,
    ])


class VisitorForm(FlaskForm):
    first_name = _name_field("Imię")
    last_name = _name_field("Nazwisko")
    company = _name_field("Firma")
    consent = BooleanField("Zapoznałem(-am) się z klauzulą informacyjną", validators=[
        DataRequired(message="Potwierdź zapoznanie się z klauzulą.")])
    website = StringField("Website")  # honeypot: humans never see it


def _passed() -> bool:
    ts = session.get(SESSION_KEY)
    return isinstance(ts, int) and 0 <= time.time() - ts < PASS_DAYS * 86400


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and not urlsplit(target).netloc \
            and "\\" not in target:
        return target
    return "/"


@bp.before_app_request
def require_introduction():
    if not current_app.config.get("DEMO_VISITOR_GATE"):
        return None
    endpoint = request.endpoint
    if endpoint is None or endpoint in EXEMPT_ENDPOINTS:
        return None
    if (request.view_args or {}).get("token"):  # share links, password-reset links
        return None
    if current_user.is_authenticated or _passed():
        return None
    if request.headers.get("HX-Request"):
        return "", 401, {"HX-Redirect": url_for("visitor_gate.gate")}
    if request.method not in ("GET", "HEAD"):
        abort(403)
    return redirect(url_for("visitor_gate.gate", next=request.full_path.rstrip("?")))


@bp.route("/wejscie", methods=["GET", "POST"])
def gate():
    target = _safe_next(request.values.get("next"))
    if not current_app.config.get("DEMO_VISITOR_GATE") or current_user.is_authenticated or _passed():
        return redirect(target)
    form = VisitorForm()
    if form.validate_on_submit():
        if form.website.data:  # honeypot filled in
            abort(400)
        now = utcnow()
        DemoVisitor.query.filter(DemoVisitor.created_at < now - timedelta(days=RETENTION_DAYS)).delete()
        db.session.add(DemoVisitor(first_name=form.first_name.data, last_name=form.last_name.data,
                                   company=form.company.data))
        db.session.commit()
        session.permanent = True
        session[SESSION_KEY] = int(time.time())
        return redirect(target)
    return render_template("visitor_gate/gate.html", form=form, next=target)


@bp.get("/admin/odwiedzajacy")
@admin_required
def visitors():
    rows = DemoVisitor.query.order_by(DemoVisitor.created_at.desc(), DemoVisitor.id.desc()).all()
    return render_template("visitor_gate/list.html", visitors=rows, days=RETENTION_DAYS)
