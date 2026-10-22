"""Recruitment mode: an exercise map against the clock, locked when time is up (then the AI interview)."""

from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..ai.client import AIError, ai_enabled, spend_ai_request
from ..export import builders
from ..extensions import db
from ..flow import graph as g
from ..models import ExerciseAttempt, RecruitSession, Version, utcnow
from . import catalog, interview
from .grading import grade
from .routes import RECRUIT_MINUTES, new_exercise_project

bp = Blueprint("recruit", __name__)


@bp.post("/cwiczenia/<key>/rekrutacja")
@login_required
def start(key):
    ex = catalog.get(key) or abort(404)
    minutes = request.form.get("minutes", type=int)
    if minutes not in RECRUIT_MINUTES:
        abort(400, "Wybierz czas: 30, 45 albo 60 minut.")
    if not ai_enabled():
        flash("Tryb rekrutacyjny wymaga AI — rozmowę z rekruterem prowadzi model.", "error")
        return redirect(url_for("exercises.index"))
    project = new_exercise_project(ex)
    now = utcnow()
    db.session.add(RecruitSession(project_id=project.id, user_id=current_user.id, minutes=minutes, started_at=now,
                                  deadline=now + timedelta(minutes=minutes)))
    db.session.commit()
    flash(f"Start! Masz {minutes} min na mapę procesu. Podpowiedzi i trener są wyłączone.", "success")
    return redirect(url_for("flow.view", project_id=project.id))


def _session(project_id):
    project = g.project_for(project_id, "view")
    if project.recruit is None:
        abort(404)
    return project, project.recruit


@bp.get("/p/<int:project_id>/rekrutacja")
@login_required
def view(project_id):
    project, session = _session(project_id)
    return render_template("exercises/recruit.html", project=project, session=session,
                           ex=catalog.get(project.exercise_key), ai=ai_enabled(), total=interview.QUESTIONS,
                           answer_max=interview.ANSWER_MAX, recommendations=interview.RECOMMENDATIONS,
                           map_pct=round(100 * interview.MAP_WEIGHT))


PAUSE_SECONDS = 180  # a gap this long between edits is shown as thinking time


@bp.get("/p/<int:project_id>/rekrutacja/przebieg")
@login_required
def replay(project_id):
    """How the map was built: every saved change with its time from the start, after the session ended."""
    project, session = _session(project_id)
    if not session.ended:
        abort(403, "Przebieg jest dostępny po oddaniu mapy.")
    end = session.finished_at or session.deadline
    versions = (Version.query.filter(Version.project_id == project.id, Version.created_at >= session.started_at,
                                     Version.created_at <= end).order_by(Version.id).all())
    steps, prev = [], session.started_at
    for v in versions:
        steps.append({"v": v, "offset": int((v.created_at - session.started_at).total_seconds()),
                      "pause": (v.created_at - prev).total_seconds() >= PAUSE_SECONDS,
                      "nodes": sum(1 for n in v.snapshot.get("nodes", []) if n["type"] != "start")})
        prev = v.created_at
    chosen = next((s for s in steps if s["v"].id == request.args.get("v", type=int)), steps[-1] if steps else None)
    return render_template("exercises/replay.html", project=project, session=session, steps=steps, chosen=chosen,
                           mermaid=chosen and builders.to_mermaid(chosen["v"].snapshot),
                           total=int((end - session.started_at).total_seconds()))


@bp.post("/p/<int:project_id>/rekrutacja/oddaj")
@login_required
def finish(project_id):
    project, session = _session(project_id)
    if session.user_id != current_user.id:
        abort(403, "Mapę oddaje tylko kandydat.")
    if session.finished_at is None:
        session.finished_at = min(utcnow(), session.deadline)
        db.session.commit()
    return redirect(url_for("recruit.view", project_id=project.id))


def _candidate(project_id):
    """The session's interview steps: map handed in, caller is the candidate."""
    project, session = _session(project_id)
    if session.user_id != current_user.id:
        abort(403, "Na pytania rekrutera odpowiada tylko kandydat.")
    if not session.ended:
        abort(400, "Najpierw oddaj mapę.")
    return project, session, catalog.get(project.exercise_key) or abort(404)


def _ai(step) -> bool:
    """Spend one AI request and run step(); flash the reason and return False on failure."""
    reason = spend_ai_request()
    if reason:
        flash(f"{reason}.", "error")
        return False
    try:
        step()
    except AIError as exc:
        flash(f"Rekruter AI nie odpowiedział ({exc}) — spróbuj ponownie.", "error")
        return False
    return True


@bp.post("/p/<int:project_id>/rekrutacja/rozmowa")
@login_required
def start_interview(project_id):
    project, session, ex = _candidate(project_id)
    if session.questions is not None:
        abort(400, "Rozmowa już trwa.")
    back = redirect(url_for("recruit.view", project_id=project.id))

    def grade_map():  # kept on failure of the next step, so a retry does not grade (and charge) twice
        feedback = grade(project, ex, 1, None) | {"mode": "recruit"}
        session.grade = feedback
        db.session.add(ExerciseAttempt(project_id=project.id, user_id=current_user.id, stage=1,
                                       score=feedback["score"], feedback=feedback))
        db.session.commit()

    def ask():
        session.questions = interview.questions(project, ex, session.grade)
        db.session.commit()

    if session.grade is None and not _ai(grade_map):
        return back
    _ai(ask)
    return back


def _report(project, session, ex):
    def write():
        session.report = interview.report(project, ex, session.grade, session.questions, session.answers)
        db.session.commit()
    return _ai(write)


@bp.post("/p/<int:project_id>/rekrutacja/odpowiedz")
@login_required
def answer(project_id):
    # ponytail: double submit is stopped client-side (data-once); add a row lock if concurrent clients ever matter
    project, session, ex = _candidate(project_id)
    if session.questions is None or len(session.answers) >= interview.QUESTIONS:
        abort(400, "Nie ma pytania, na które można odpowiedzieć.")
    text = (request.form.get("text") or "").strip()
    if not text or len(text) > interview.ANSWER_MAX:
        flash(f"Odpowiedź musi mieć od 1 do {interview.ANSWER_MAX} znaków.", "error")
    else:
        session.answers = session.answers + [text]  # new list: JSON columns do not track in-place changes
        db.session.commit()
        if len(session.answers) == interview.QUESTIONS:
            _report(project, session, ex)
    return redirect(url_for("recruit.view", project_id=project.id))


@bp.post("/p/<int:project_id>/rekrutacja/raport")
@login_required
def make_report(project_id):
    project, session, ex = _candidate(project_id)
    if len(session.answers) < interview.QUESTIONS or session.report is not None:
        abort(400, "Raport powstaje po ostatniej odpowiedzi.")
    _report(project, session, ex)
    return redirect(url_for("recruit.view", project_id=project.id))
