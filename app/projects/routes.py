from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import RadioField, SelectField, StringField
from wtforms.validators import DataRequired, Length

from .. import audit
from ..ai.templates import TEMPLATE_CHOICES
from ..extensions import db
from ..flow import graph as g
from ..models import Project, ProjectMember, Version
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
    if form.validate_on_submit():
        project = create_project(current_user, form.name.data, form.start_sentence.data, form.mode.data,
                                 form.template.data)
        audit.log("project_created", project.name)
        db.session.commit()
        return redirect(url_for("flow.view", project_id=project.id))
    return render_template("projects/new.html", form=form)


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
