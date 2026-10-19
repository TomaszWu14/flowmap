"""'Ocena' tab: rule-based scores with history per user."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..flow import graph as g
from ..models import Evaluation, utcnow
from .rubric import evaluate

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
    history = [(e.created_at, e.score, design_at.get(e.created_at)) for e in rows if e.kind == "map"][:10]
    return render_template("trainer/score.html", project=project, latest=latest, previous=previous, history=history)


@bp.post("/p/<int:project_id>/ocena")
@login_required
def score_now(project_id):
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
    now = utcnow()  # one moment for both scores, so the history pairs them
    for result in evaluate(project):
        db.session.add(Evaluation(project_id=project.id, user_id=current_user.id, kind=result["kind"],
                                  score=result["score"], details=result, created_at=now))
    db.session.commit()
    return redirect(url_for("trainer.score", project_id=project.id))
