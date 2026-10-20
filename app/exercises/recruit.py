"""Recruitment mode: an exercise map against the clock, locked when time is up (then the AI interview)."""

from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..ai.client import ai_enabled
from ..extensions import db
from ..flow import graph as g
from ..models import RecruitSession, utcnow
from . import catalog
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
                           ex=catalog.get(project.exercise_key))


@bp.post("/p/<int:project_id>/rekrutacja/oddaj")
@login_required
def finish(project_id):
    project, session = _session(project_id)
    if project.current_role == "viewer":
        abort(403)
    if session.finished_at is None:
        session.finished_at = min(utcnow(), session.deadline)
        db.session.commit()
    return redirect(url_for("recruit.view", project_id=project.id))
