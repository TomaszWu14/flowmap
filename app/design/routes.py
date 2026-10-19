"""'Projekt aplikacji' tab: UML views of the spec with a Mermaid preview and the UML guard."""

from flask import Blueprint, abort, render_template, request
from flask_login import login_required

from ..extensions import db
from ..flow import graph as g
from .lint import lint
from .uml import class_diagram

bp = Blueprint("design", __name__)
DESIGN_SECTIONS = {"classes": "Klasy"}
DIAGRAMS = {"classes": class_diagram}
HELP = {"classes": "Diagram klas UML: encje (klasy) z polami i relacjami. Krotność „1 → *” czytaj: "
                   "jeden rekord po lewej ma wiele po prawej."}


@bp.get("/p/<int:project_id>/projekt-aplikacji")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    if project.spec is None:
        g.refresh_spec(project)
        db.session.commit()
    section = request.args.get("sekcja", "classes")
    if section not in DESIGN_SECTIONS:
        abort(400)
    spec = g.project_spec(project)
    ctx = {"project": project, "spec": spec, "section": section, "sections": DESIGN_SECTIONS,
           "help": HELP[section], "diagram": "", "issues": []}
    if spec is not None:
        ctx.update(diagram=DIAGRAMS[section](spec), issues=lint(spec))
    return render_template("design/view.html", **ctx)
