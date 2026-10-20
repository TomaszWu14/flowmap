"""Exercises: catalogue of fixed tasks, starting one as a learning-mode project, the task panel on the map."""

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from .. import audit
from ..extensions import db
from ..flow import graph as g
from ..models import ExerciseAttempt, Project
from ..projects.service import create_project
from . import catalog

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
                           levels=catalog.LEVELS)
