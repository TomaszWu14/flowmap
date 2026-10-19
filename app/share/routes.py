"""Public read-only share link: map, specification and simulation without logging in."""

import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from .. import audit
from ..export import builders
from ..extensions import db
from ..flow import graph as g
from ..flow.routes import graph_payload, render_simulation
from ..models import Project, ProjectMember, User

bp = Blueprint("share", __name__)


def _shared(token: str) -> Project:
    project = Project.query.filter_by(share_token=token).first() if token else None
    if project is None:
        abort(404)
    return project


@bp.get("/p/<int:project_id>/udostepnianie")
@login_required
def settings(project_id):
    project = g.project_for(project_id, "owner")
    return render_template("share/settings.html", project=project, role_labels=g.ROLE_LABELS)


@bp.post("/p/<int:project_id>/udostepnianie/link")
@login_required
def toggle_link(project_id):
    project = g.project_for(project_id, "owner")
    if project.share_token:
        project.share_token = None
        audit.log("share_link_disabled", project.name)
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
    project = g.project_for(project_id, "owner")
    project.share_token = secrets.token_urlsafe(18)
    audit.log("project_shared", f"{project.name} (nowy link)")
    db.session.commit()
    flash("Wygenerowano nowy link — poprzedni przestał działać.", "success")
    return redirect(url_for("share.settings", project_id=project.id))


@bp.post("/p/<int:project_id>/czlonkowie")
@login_required
def member_add(project_id):
    project = g.project_for(project_id, "owner")
    email = (request.form.get("email") or "").strip().lower()
    role = request.form.get("role")
    user = User.query.filter_by(email=email).first() if email else None
    if role not in ("editor", "viewer"):
        abort(400)
    if user is None:
        flash("Nie ma konta z tym adresem — ta osoba musi najpierw się zarejestrować.", "error")
    elif user.id == project.owner_id or any(m.user_id == user.id for m in project.members):
        flash("Ta osoba ma już dostęp do projektu.", "error")
    else:
        project.members.append(ProjectMember(user_id=user.id, role=role))
        audit.log("member_added", f"{project.name}: {user.email} ({role})")
        db.session.commit()
        flash(f"Dodano {user.email} jako {g.ROLE_LABELS[role]}.", "success")
    return redirect(url_for("share.settings", project_id=project.id))


def _member(project, member_id) -> ProjectMember:
    member = next((m for m in project.members if m.id == member_id), None)
    if member is None:
        abort(404)
    return member


@bp.post("/p/<int:project_id>/czlonkowie/<int:member_id>/rola")
@login_required
def member_role(project_id, member_id):
    project = g.project_for(project_id, "owner")
    member = _member(project, member_id)
    role = request.form.get("role")
    if role not in ("editor", "viewer"):
        abort(400)
    member.role = role
    audit.log("member_role_changed", f"{project.name}: {member.user.email} ({role})")
    db.session.commit()
    flash(f"{member.user.email}: {g.ROLE_LABELS[role]}.", "success")
    return redirect(url_for("share.settings", project_id=project.id))


@bp.post("/p/<int:project_id>/czlonkowie/<int:member_id>/usun")
@login_required
def member_remove(project_id, member_id):
    project = g.project_for(project_id, "owner")
    member = _member(project, member_id)
    audit.log("member_removed", f"{project.name}: {member.user.email}")
    project.members.remove(member)
    db.session.delete(member)
    db.session.commit()
    flash("Usunięto dostęp.", "success")
    return redirect(url_for("share.settings", project_id=project.id))


@bp.get("/s/<token>")
def view(token):
    project = _shared(token)
    graph = project.graph()
    spec = builders.to_markdown(project.meta, graph, g.project_spec(project))
    return render_template("share/view.html", project=project, token=token, spec=spec,
                           mermaid=builders.to_mermaid(graph))


@bp.get("/s/<token>/graph.json")
def graph_json(token):
    project = _shared(token)
    return graph_payload(project.graph(), display=project.display)


@bp.get("/s/<token>/symulacja")
def simulate(token):
    project = _shared(token)
    return render_simulation(project, url_for("share.view", token=token),
                             lambda **kw: url_for("share.simulate", token=token, **kw))
