"""Public read-only share link: map, specification and simulation without logging in."""

import secrets

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import login_required

from .. import audit
from ..export import builders
from ..extensions import db
from ..flow import graph as g
from ..flow.routes import graph_payload, render_simulation
from ..models import Project

bp = Blueprint("share", __name__)


def _shared(token: str) -> Project:
    project = Project.query.filter_by(share_token=token).first() if token else None
    if project is None:
        abort(404)
    return project


def _meta(project) -> dict:
    return {"name": project.name, "start_sentence": project.start_sentence, "mode": project.mode}


@bp.get("/p/<int:project_id>/udostepnianie")
@login_required
def settings(project_id):
    project = g.owned_project(project_id)
    return render_template("share/settings.html", project=project)


@bp.post("/p/<int:project_id>/udostepnianie/link")
@login_required
def toggle_link(project_id):
    project = g.owned_project(project_id)
    if project.share_token:
        project.share_token = None
        flash("Link publiczny wyłączony — stary adres już nie działa.", "success")
    else:
        project.share_token = secrets.token_urlsafe(18)
        audit.log("project_shared", project.name)
        flash("Link publiczny włączony.", "success")
    db.session.commit()
    return redirect(url_for("share.settings", project_id=project.id))


@bp.post("/p/<int:project_id>/udostepnianie/nowy-link")
@login_required
def regenerate_link(project_id):
    project = g.owned_project(project_id)
    project.share_token = secrets.token_urlsafe(18)
    audit.log("project_shared", f"{project.name} (nowy link)")
    db.session.commit()
    flash("Wygenerowano nowy link — poprzedni przestał działać.", "success")
    return redirect(url_for("share.settings", project_id=project.id))


@bp.get("/s/<token>")
def view(token):
    project = _shared(token)
    graph = project.graph()
    return render_template("share/view.html", project=project, token=token,
                           spec=builders.to_markdown(_meta(project), graph), mermaid=builders.to_mermaid(graph))


@bp.get("/s/<token>/graph.json")
def graph_json(token):
    return graph_payload(_shared(token).graph())


@bp.get("/s/<token>/symulacja")
def simulate(token):
    project = _shared(token)
    return render_simulation(project, url_for("share.view", token=token),
                             lambda **kw: url_for("share.simulate", token=token, **kw))
