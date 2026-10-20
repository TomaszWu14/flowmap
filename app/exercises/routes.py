"""Exercises: catalogue of fixed tasks, starting one as a learning-mode project, the task panel on the map."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from .. import audit
from ..ai.client import AIError, ai_enabled, spend_ai_request
from ..extensions import db
from ..flow import graph as g
from ..models import ExerciseAttempt, Project
from ..projects.service import create_project
from . import catalog
from .grading import VERDICTS, grade

bp = Blueprint("exercises", __name__)


@bp.get("/cwiczenia")
@login_required
def index():
    best = dict(db.session.query(Project.exercise_key, func.max(ExerciseAttempt.score))
                .join(Project, ExerciseAttempt.project_id == Project.id)
                .filter(ExerciseAttempt.user_id == current_user.id).group_by(Project.exercise_key).all())
    return render_template("exercises/index.html", exercises=catalog.all_exercises(), best=best,
                           levels=catalog.LEVELS)


@bp.post("/cwiczenia/<key>/start")
@login_required
def start(key):
    ex = catalog.get(key) or abort(404)
    project = create_project(current_user, ex.title, ex.start_sentence, "quick")
    project.learning = True
    project.exercise_key = ex.key
    audit.log("exercise_started", ex.key)
    db.session.commit()
    return redirect(url_for("flow.view", project_id=project.id))


@bp.get("/p/<int:project_id>/cwiczenie/zadanie")
@login_required
def task_panel(project_id):
    project = g.project_for(project_id, "view")
    ex = catalog.get(project.exercise_key) or abort(404)
    return render_template("exercises/_task.html", project=project, ex=ex, stages=catalog.STAGES,
                           levels=catalog.LEVELS, ai=ai_enabled())


@bp.get("/p/<int:project_id>/cwiczenie")
@login_required
def results(project_id):
    project = g.project_for(project_id, "view")
    ex = catalog.get(project.exercise_key) or abort(404)
    rows = (ExerciseAttempt.query.filter_by(project_id=project.id)
            .order_by(ExerciseAttempt.id.desc()).all())
    stages = []
    for stage in range(1, catalog.STAGES + 1):
        done = [a for a in rows if a.stage == stage]
        stages.append({"number": stage, "attempts": done, "latest": done[0] if done else None,
                       "best": max((a.score for a in done), default=None),
                       "open": stage <= project.exercise_stage})
    return render_template("exercises/results.html", project=project, ex=ex, stages=stages, verdicts=VERDICTS,
                           ai=ai_enabled())


@bp.post("/p/<int:project_id>/cwiczenie/oddaj")
@login_required
def submit(project_id):
    project = g.project_for(project_id, "edit")
    ex = catalog.get(project.exercise_key) or abort(404)
    stage = request.form.get("stage", type=int)
    if stage not in range(1, project.exercise_stage + 1):
        abort(400, "Ten etap nie jest jeszcze otwarty.")
    back = redirect(url_for("exercises.results", project_id=project.id))
    spec = None
    if stage == 2:
        g.ensure_spec(project)
        spec = g.project_spec(project)
        if spec is None:
            flash("Specyfikacja jest uszkodzona — odbuduj ją z mapy i oddaj ponownie.", "error")
            return back
    reason = spend_ai_request()
    if reason:
        flash(f"{reason} — nie można oddać etapu.", "error")
        return back
    try:
        feedback = grade(project, ex, stage, spec)
    except AIError as exc:
        flash(f"Ocena nieudana ({exc}) — spróbuj oddać ponownie.", "error")
        return back
    db.session.add(ExerciseAttempt(project_id=project.id, user_id=current_user.id, stage=stage,
                                   score=feedback["score"], feedback=feedback))
    if stage == project.exercise_stage < catalog.STAGES:
        project.exercise_stage = stage + 1
    db.session.commit()
    flash(f"Etap {stage} oceniony: {feedback['score']}/100.", "success")
    return back
