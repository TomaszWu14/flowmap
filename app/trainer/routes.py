"""'Ocena' tab: rule-based scores (optionally mixed with a qualitative AI part) with history per user."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..ai.client import AIError, ai_enabled, spend_ai_request
from ..extensions import db
from ..flow import graph as g
from ..models import Evaluation, utcnow
from .ai_review import assess
from .chat import history, reply
from .rubric import evaluate, mix

bp = Blueprint("trainer", __name__)


@bp.get("/p/<int:project_id>/ocena")
@login_required
def score(project_id):
    project = g.project_for(project_id, "view")
    rows = (Evaluation.query.filter_by(project_id=project.id, user_id=current_user.id)
            .order_by(Evaluation.id.desc()).limit(20).all())
    latest, previous = {}, {}
    for e in rows:
        if e.kind not in latest:
            latest[e.kind] = e
        elif e.kind not in previous:
            previous[e.kind] = e
    design_at = {e.created_at: e.score for e in rows if e.kind == "design"}
    history = [(e.created_at, e.score, design_at.get(e.created_at), e.source) for e in rows if e.kind == "map"][:10]
    return render_template("trainer/score.html", project=project, latest=latest, previous=previous, history=history,
                           ai=ai_enabled())


def _save(project, results: list[dict], source: str):
    now = utcnow()  # one moment for both scores, so the history pairs them
    for result in results:
        db.session.add(Evaluation(project_id=project.id, user_id=current_user.id, kind=result["kind"],
                                  score=result["score"], details=result, source=source, created_at=now))
    db.session.commit()
    return redirect(url_for("trainer.score", project_id=project.id))


@bp.post("/p/<int:project_id>/ocena")
@login_required
def score_now(project_id):
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
    return _save(project, evaluate(project), "rules")


@bp.post("/p/<int:project_id>/ocena/ai")
@login_required
def score_ai(project_id):
    project = g.project_for(project_id, "view")
    g.forbid_assist(project, running_only=True)
    g.ensure_spec(project)
    results = evaluate(project)
    reason = spend_ai_request()
    if reason:
        flash(f"{reason} — zapisano ocenę z reguł.", "error")
        return _save(project, results, "rules")
    try:
        ai = assess(project, project.graph(), g.project_spec(project), results)
    except AIError as exc:
        flash(f"Ocena AI nieudana ({exc}) — zapisano ocenę z reguł.", "error")
        return _save(project, results, "rules")
    return _save(project, mix(results, ai), "mixed")


def _chat(project, error=None, draft=""):
    return render_template("trainer/_chat.html", project=project, messages=history(project, current_user),
                           ai=ai_enabled() and not project.recruit, error=error, draft=draft)


@bp.get("/p/<int:project_id>/trener")
@login_required
def chat_panel(project_id):
    return _chat(g.project_for(project_id, "view"))


@bp.post("/p/<int:project_id>/trener")
@login_required
def chat(project_id):
    project = g.project_for(project_id, "view")
    if project.recruit:
        return _chat(project)
    text = (request.form.get("text") or "").strip()
    if not text:
        return _chat(project, "Napisz pytanie do trenera.")
    if len(text) > 2000:
        return _chat(project, "Wiadomość może mieć najwyżej 2000 znaków.", draft=text[:2000])
    reason = spend_ai_request()
    if reason:
        return _chat(project, f"{reason}.", draft=text)
    try:
        reply(project, current_user, text)
    except AIError as exc:
        return _chat(project, f"Trener nie odpowiedział: {exc}.", draft=text)
    return _chat(project)
