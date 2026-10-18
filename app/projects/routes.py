from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import RadioField, SelectField, StringField
from wtforms.validators import DataRequired, Length

from .. import audit
from ..ai.templates import TEMPLATE_CHOICES, USER_PREFIX
from ..extensions import db
from ..flow import graph as g
from ..flow.diff import diff_graphs, node_status
from ..flow.routes import graph_payload
from ..models import Project, ProjectMember, UserTemplate, Version
from .service import copy_project, create_project

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
              .order_by(Project.updated_at.desc()).all())
    return render_template("projects/index.html", projects=projects, shared=shared, role_labels=g.ROLE_LABELS)


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
    flash("Utworzono kopię projektu.", "success")
    return redirect(url_for("flow.view", project_id=copy.id))


@bp.get("/p/<int:project_id>/wersje")
@login_required
def versions(project_id):
    project = g.project_for(project_id, "view")
    return render_template("projects/versions.html", project=project,
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
    payload = graph_payload(graph)
    for n in payload["nodes"]:
        n["diff"] = status.get(n["key"], "")
    return payload


@bp.post("/p/<int:project_id>/wersje/<int:version_id>/przywroc")
@login_required
def restore(project_id, version_id):
    project = g.project_for(project_id, "edit")
    version = db.session.get(Version, version_id)
    if version is None or version.project_id != project.id:
        return render_template("error.html", code=404, message="Nie ma takiej wersji."), 404
    g.restore_version(project, version)
    db.session.commit()
    flash(f"Przywrócono wersję „{version.description}”.", "success")
    return redirect(url_for("flow.view", project_id=project.id))
