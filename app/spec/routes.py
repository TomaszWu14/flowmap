"""Read-only 'Specyfikacja' tab: sections derived from the map, rebuild on a broken document."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..flow import graph as g
from .schema import CHANNEL_LABELS, DIRECTION_LABELS, FIELD_TYPE_LABELS, NFR_LABELS, PERM_LABELS, SECTIONS

bp = Blueprint("spec", __name__)
SECTION_LABELS = {"entities": "Encje", "screens": "Ekrany", "roles": "Role", "states": "Statusy",
                  "notifications": "Powiadomienia", "integrations": "Integracje", "nfr": "Wymagania (NFR)"}


def _context(project, section: str) -> dict:
    spec = g.project_spec(project)
    names = {}
    if spec is not None:
        names = {e.key: e.name for e in spec.entities} | {r.key: r.name for r in spec.roles}
    return {"project": project, "spec": spec, "section": section, "sections": SECTION_LABELS,
            "type_labels_f": FIELD_TYPE_LABELS, "perm_labels": PERM_LABELS, "channel_labels": CHANNEL_LABELS,
            "direction_labels": DIRECTION_LABELS, "nfr_labels": NFR_LABELS, "names": names,
            "can_edit": project.current_role in ("owner", "editor")}


@bp.get("/p/<int:project_id>/specyfikacja")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    if project.spec is None:
        g.refresh_spec(project)
        db.session.commit()
    section = request.args.get("sekcja", "entities")
    if section not in SECTIONS:
        abort(400)
    return render_template("spec/view.html", **_context(project, section))


@bp.post("/p/<int:project_id>/specyfikacja/odbuduj")
@login_required
def rebuild(project_id):
    project = g.project_for(project_id, "edit")
    project.spec = None
    g.save_version(project, "Specyfikacja odbudowana z mapy")
    db.session.commit()
    flash("Specyfikacja odbudowana z mapy.", "success")
    return redirect(url_for("spec.view", project_id=project.id))
