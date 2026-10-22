"""Exercises: catalogue of fixed tasks, starting one as a learning-mode project, the task panel on the map."""

from statistics import mean

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from .. import audit
from ..ai.client import AIError, ai_enabled, spend_ai_request
from ..export import builders
from ..extensions import db
from ..flow import graph as g
from ..models import Evaluation, ExerciseAttempt, Project
from ..projects.service import create_project
from . import catalog, progress
from .grading import VERDICTS, grade

bp = Blueprint("exercises", __name__)
RECRUIT_MINUTES = (30, 45, 60)


@bp.get("/cwiczenia")
@login_required
def index():
    best = dict(db.session.query(Project.exercise_key, func.max(ExerciseAttempt.score))
                .join(Project, ExerciseAttempt.project_id == Project.id)
                .filter(ExerciseAttempt.user_id == current_user.id).group_by(Project.exercise_key).all())
    return render_template("exercises/index.html", exercises=catalog.all_exercises(), best=best,
                           levels=catalog.LEVELS, ai=ai_enabled(), recruit_minutes=RECRUIT_MINUTES)


@bp.post("/cwiczenia/<key>/start")
@login_required
def start(key):
    project = new_exercise_project(catalog.get(key) or abort(404))
    db.session.commit()
    return redirect(url_for("flow.view", project_id=project.id))


def new_exercise_project(ex) -> Project:
    """Exercise project in learning mode; the caller commits."""
    project = create_project(current_user, ex.title, ex.start_sentence, "quick")
    project.learning = True
    project.exercise_key = ex.key
    audit.log("exercise_started", ex.key)
    return project


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
    solution = ex.solution_graph() if stages[0]["latest"] else None  # revealed after the first graded map
    return render_template("exercises/results.html", project=project, ex=ex, stages=stages, verdicts=VERDICTS,
                           ai=ai_enabled(), solution=solution and builders.to_mermaid(solution),
                           mine=solution and builders.to_mermaid(project.graph()))


@bp.post("/p/<int:project_id>/cwiczenie/oddaj")
@login_required
def submit(project_id):
    project = g.project_for(project_id, "edit")
    g.forbid_assist(project)  # recruitment: the map is graded once, after "Oddaję" (exercises/recruit.py)
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


@bp.get("/postep")
@login_required
def progress_page():
    rows = (db.session.query(ExerciseAttempt, Project.exercise_key)
            .join(Project, ExerciseAttempt.project_id == Project.id)
            .filter(ExerciseAttempt.user_id == current_user.id).order_by(ExerciseAttempt.id).all())
    stages: dict[tuple, dict] = {}  # (exercise key, stage) -> first, best, count
    for a, key in rows:
        s = stages.setdefault((key, a.stage), {"first": a.score, "best": a.score, "count": 0})
        s["best"] = max(s["best"], a.score)
        s["count"] += 1
    exercises = catalog.all_exercises()
    topic_of_text = {e.text: e.topic for ex in exercises for e in ex.stage1 + ex.stage2}
    latest_attempts = progress.latest(rows, lambda r: (r[1], r[0].stage))
    topics = progress.topic_stats([a.feedback for a, _ in latest_attempts], topic_of_text)
    evaluations = Evaluation.query.filter_by(user_id=current_user.id).order_by(Evaluation.id).all()
    latest_evals = progress.latest(evaluations, lambda e: (e.project_id, e.kind))
    stats = topics + progress.criteria_stats([e.details for e in latest_evals])
    strong, weak = progress.strengths_and_weaknesses(stats)
    weak_topics = [t["code"] for t in sorted(topics, key=lambda t: t["value"]) if t["value"] < progress.STRONG]
    score = {ex.key: round(mean(s["best"] for (k, _), s in stages.items() if k == ex.key))
             for ex in exercises if any(k == ex.key for k, _ in stages)}
    continuable = Project.query.filter(Project.owner_id == current_user.id, Project.exercise_key.isnot(None),
                                       ~Project.recruit.has())  # recruitment projects are locked
    projects = {p.exercise_key: p for p in continuable.order_by(Project.id)}
    return render_template("exercises/progress.html", exercises=exercises, stages=stages, score=score,
                           strong=strong, weak=weak, trend=progress.trend([a.score for a, _ in rows]),
                           attempts=len(rows), evaluated=len({e.project_id for e in latest_evals}),
                           pick=progress.recommend(exercises, score, weak_topics), projects=projects,
                           levels=catalog.LEVELS, strong_at=progress.STRONG)
