from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from wtforms import RadioField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length

from .. import audit
from ..ai.client import AIError, ai_enabled, draft_map, spend_ai_request
from ..ai.draft import draft_from_text
from ..ai.templates import TEMPLATE_CHOICES, USER_PREFIX
from ..extensions import db
from ..flow import graph as g
from ..flow.diff import diff_graphs, node_status
from ..flow.routes import graph_payload
from ..models import Attachment, Node, Project, ProjectMember, UserTemplate, Version
from ..text import steps_label
from .service import copy_project, create_project, project_from_graph

bp = Blueprint("projects", __name__)


class ProjectForm(FlaskForm):
    name = StringField("Nazwa projektu", validators=[DataRequired(), Length(max=200)])
    start_sentence = StringField(
        "Zdanie startowe", validators=[DataRequired(), Length(min=5, max=500)],
        description="Np. „Klient chce umówić wizytę w salonie”.",
    )
    mode = RadioField("Tryb", choices=[("quick", "Szybki — ok. 5 pytań"),
                                       ("thorough", "Dokładny — ok. 20 pytań i wyjątki")],
                      default="quick")
    template = SelectField("Szablon procesu (tryb bez AI)", choices=TEMPLATE_CHOICES, default="auto")


class DraftForm(FlaskForm):
    name = StringField("Nazwa projektu", validators=[DataRequired(), Length(max=200)])
    text = TextAreaField("Opis procesu", validators=[DataRequired(), Length(min=20, max=20000)],
                         description="Notatki, opis słowny albo lista kroków — najlepiej jeden krok na linię.")
    mode = RadioField("Tryb dopytywania", choices=[("quick", "Szybki"), ("thorough", "Dokładny")], default="quick")


@bp.get("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("projects.index"))
    return render_template("home.html")


@bp.get("/projekty")
@login_required
def index():
    projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.updated_at.desc()).all()
    shared = (ProjectMember.query.filter_by(user_id=current_user.id).join(Project)
              .options(joinedload(ProjectMember.project).joinedload(Project.owner))
              .order_by(Project.updated_at.desc()).all())
    ids = [p.id for p in projects] + [m.project_id for m in shared]
    steps = dict(db.session.query(Node.project_id, func.count(Node.id))
                 .filter(Node.project_id.in_(ids)).group_by(Node.project_id).all()) if ids else {}
    covers = dict(db.session.query(Attachment.project_id, Attachment.id)
                  .filter(Attachment.project_id.in_(ids), Attachment.is_cover.is_(True)).all()) if ids else {}
    return render_template("projects/index.html", projects=projects, shared=shared, role_labels=g.ROLE_LABELS,
                           steps=steps, covers=covers)


@bp.route("/projekty/nowy", methods=["GET", "POST"])
@login_required
def new():
    form = ProjectForm()
    own = UserTemplate.query.filter_by(owner_id=current_user.id).order_by(UserTemplate.name).all()
    form.template.choices = TEMPLATE_CHOICES + [(f"{USER_PREFIX}{t.id}", f"Mój: {t.name}") for t in own]
    if form.validate_on_submit():
        project = create_project(current_user, form.name.data, form.start_sentence.data, form.mode.data,
                                 form.template.data)
        audit.log("project_created", project.name)
        db.session.commit()
        return redirect(url_for("flow.view", project_id=project.id))
    return render_template("projects/new.html", form=form)


@bp.route("/projekty/z-dokumentu", methods=["GET", "POST"])
@login_required
def from_document():
    form = DraftForm()
    if form.validate_on_submit():
        text = form.text.data.strip()
        graph, note = None, "Mapa z dokumentu (reguły)"
        if ai_enabled():
            reason = spend_ai_request()
            if reason:
                flash(f"{reason} — mapa z reguł.", "info")
            else:
                try:
                    graph, note = draft_map(text), "Mapa z dokumentu (AI)"
                except AIError as exc:
                    flash(f"AI niedostępne ({exc}) — mapa z reguł.", "info")
        if graph is None:
            graph = draft_from_text(text)
        start = next(n for n in graph["nodes"] if n["type"] == "start")
        project = project_from_graph(current_user, form.name.data, start["title"], form.mode.data, None, graph, note)
        audit.log("project_created", f"{project.name} (z dokumentu)")
        db.session.commit()
        flash(f"Szkic mapy gotowy: {steps_label(len(graph['nodes']))}. "
              "Uzupełnij brakujące gałęzie w pytaniach.", "success")
        return redirect(url_for("flow.view", project_id=project.id))
    return render_template("projects/from_document.html", form=form)


@bp.post("/p/<int:project_id>/zapisz-szablon")
@login_required
def save_template(project_id):
    project = g.project_for(project_id, "view")
    name = (request.form.get("name") or "").strip()[:120]
    keywords = [k.strip().lower()[:40] for k in (request.form.get("keywords") or "").split(",") if k.strip()][:15]
    graph = project.graph()
    if not name:
        flash("Podaj nazwę szablonu.", "error")
    elif not any(n["type"] == "start" for n in graph["nodes"]) or len(graph["nodes"]) < 3:
        flash("Szablon potrzebuje mapy z krokiem startowym i co najmniej 3 krokami.", "error")
    else:
        for n in graph["nodes"]:
            n["x"] = n["y"] = None
            n["data"] = {k: v for k, v in (n.get("data") or {}).items() if k == "branches"}
        db.session.add(UserTemplate(owner_id=current_user.id, name=name, keywords=keywords, graph=graph))
        db.session.commit()
        flash(f"Zapisano szablon „{name}”. Wybierzesz go przy nowym projekcie.", "success")
        return redirect(url_for("projects.templates"))
    return redirect(url_for("export.index", project_id=project.id))


@bp.get("/szablony")
@login_required
def templates():
    own = UserTemplate.query.filter_by(owner_id=current_user.id).order_by(UserTemplate.created_at.desc()).all()
    return render_template("projects/templates.html", templates=own)


@bp.post("/szablony/<int:template_id>/usun")
@login_required
def delete_template(template_id):
    tpl = db.session.get(UserTemplate, template_id)
    if tpl is None or tpl.owner_id != current_user.id:
        abort(404)
    db.session.delete(tpl)
    db.session.commit()
    flash("Szablon usunięty. Projekty, które z niego powstały, zostają.", "success")
    return redirect(url_for("projects.templates"))


@bp.post("/p/<int:project_id>/usun")
@login_required
def delete(project_id):
    project = g.project_for(project_id, "owner")
    audit.log("project_deleted", project.name)
    db.session.delete(project)
    db.session.commit()
    flash("Projekt usunięty.", "success")
    return redirect(url_for("projects.index"))


@bp.post("/p/<int:project_id>/kopia")
@login_required
def copy(project_id):
    copy = copy_project(g.project_for(project_id, "view"), current_user)
    audit.log("project_created", f"{copy.name} (kopia)")
    db.session.commit()
    flash("Utworzono kopię projektu.", "success")
    return redirect(url_for("flow.view", project_id=copy.id))


@bp.get("/p/<int:project_id>/wersje")
@login_required
def versions(project_id):
    from ..models import ClientReview

    project = g.project_for(project_id, "view")
    reviews: dict[int, list] = {}
    for r in ClientReview.query.filter_by(project_id=project.id).order_by(ClientReview.id):
        reviews.setdefault(r.version_id, []).append(r)
    return render_template("projects/versions.html", project=project, reviews=reviews,
                           versions=sorted(project.versions, key=lambda v: v.id, reverse=True))


def _version(project, version_id) -> Version:
    version = db.session.get(Version, version_id)
    if version is None or version.project_id != project.id:
        abort(404)
    return version


@bp.get("/p/<int:project_id>/wersje/porownaj")
@login_required
def compare(project_id):
    project = g.project_for(project_id, "view")
    versions = sorted(project.versions, key=lambda v: v.id, reverse=True)
    if len(versions) < 2:
        flash("Do porównania potrzebne są co najmniej dwie wersje.", "info")
        return redirect(url_for("projects.versions", project_id=project.id))
    new = _version(project, request.args.get("do", type=int) or versions[0].id)
    older = [v for v in versions if v.id < new.id]
    old = _version(project, request.args.get("od", type=int) or (older[0].id if older else versions[-1].id))
    if old.id > new.id:
        old, new = new, old
    return render_template("projects/diff.html", project=project, versions=versions, old=old, new=new,
                           diff=diff_graphs(old.snapshot, new.snapshot))


@bp.post("/p/<int:project_id>/wersje/<int:version_id>/as-is")
@login_required
def mark_as_is(project_id, version_id):
    """Pin a version as the current state ("jak jest"); the live map is then the target ("jak ma być")."""
    project = g.project_for(project_id, "edit")
    version = _version(project, version_id)
    project.display = dict(project.display or {}) | {"as_is": version.id}
    db.session.commit()
    flash(f"Wersja „{version.description}” jest teraz stanem obecnym (AS-IS).", "success")
    return redirect(url_for("projects.as_is_to_be", project_id=project.id))


@bp.get("/p/<int:project_id>/as-is-to-be")
@login_required
def as_is_to_be(project_id):
    """AS-IS (pinned version) next to TO-BE (the live map): diagrams, step changes, time, cost and hand-offs."""
    from ..export.builders import to_mermaid
    from ..flow import timing
    from ..flow.lanes import lanes_info

    project = g.project_for(project_id, "view")
    pinned = db.session.get(Version, (project.display or {}).get("as_is") or 0)
    if pinned is None or pinned.project_id != project.id:
        return render_template("projects/as_is_to_be.html", project=project, pinned=None)
    old, new = pinned.snapshot, project.graph()

    def measures(graph):
        t = timing.analyze(graph) or {}
        return {"steps": sum(1 for n in graph["nodes"] if n["type"] not in ("start", "end")),
                "handoffs": lanes_info(graph, project.display)["handoffs"], "minutes": t.get("minutes"),
                "cost": t.get("cost")}

    return render_template("projects/as_is_to_be.html", project=project, pinned=pinned,
                           diff=diff_graphs(old, new), before=measures(old), after=measures(new),
                           mermaid_old=to_mermaid(old), mermaid_new=to_mermaid(new))


@bp.get("/p/<int:project_id>/wersje/<int:version_id>/graph.json")
@login_required
def version_graph(project_id, version_id):
    """A version's map with diff status per node (against ?od=<older version>)."""
    project = g.project_for(project_id, "view")
    version = _version(project, version_id)
    graph = version.snapshot
    status = {}
    if request.args.get("od", type=int):
        status = node_status(diff_graphs(_version(project, request.args.get("od", type=int)).snapshot, graph))
    payload = graph_payload(graph, display=project.display)
    for n in payload["nodes"]:
        n["diff"] = status.get(n["key"], "")
    return payload


@bp.post("/p/<int:project_id>/wersje/<int:version_id>/przywroc")
@login_required
def restore(project_id, version_id):
    project = g.project_for(project_id, "edit")
    version = _version(project, version_id)
    g.restore_version(project, version)
    db.session.commit()
    flash(f"Przywrócono wersję „{version.description}”.", "success")
    return redirect(url_for("flow.view", project_id=project.id))
