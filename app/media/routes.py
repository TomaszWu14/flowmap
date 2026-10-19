"""Images in projects: per step (screenshots, workstation photos, scans) and project materials (cover, gallery).

Stored in the database (backed up with the projects, no extra volume). The browser shrinks photos to ≤ 1600 px
before upload; the server accepts only real PNG/JPEG/WebP/GIF (checked by content, not by name).
"""

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required

from .. import audit
from ..extensions import db
from ..flow import graph as g
from ..models import Attachment, Project

bp = Blueprint("media", __name__)
MAX_BYTES = 2 * 1024 * 1024
MAX_PER_PROJECT = 60
SIGNATURES = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"),
              (b"GIF89a", "image/gif")]


def sniff(data: bytes) -> str | None:
    """Image type from the file's first bytes; None for anything else (SVG and HTML are refused on purpose)."""
    for magic, mime in SIGNATURES:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def images_of(project, node_key: str = "") -> list[Attachment]:
    return (Attachment.query.filter_by(project_id=project.id, node_key=node_key)
            .order_by(Attachment.id).all())


def image_counts(project) -> dict[str, tuple[int, int]]:
    """node key -> (number of images, id of the first one) — for the map badge, tooltip and playback."""
    out: dict[str, tuple[int, int]] = {}
    rows = (db.session.query(Attachment.node_key, Attachment.id)
            .filter(Attachment.project_id == project.id, Attachment.node_key != "").order_by(Attachment.id).all())
    for key, att_id in rows:
        count, first = out.get(key, (0, att_id))
        out[key] = (count + 1, first)
    return out


def _gallery(project, node_key: str, error: str | None = None):
    return render_template("media/_gallery.html", project=project, node_key=node_key,
                           images=images_of(project, node_key), error=error)


@bp.post("/p/<int:project_id>/grafiki")
@login_required
def upload(project_id):
    project = g.project_for(project_id, "edit")
    node_key = request.form.get("node_key", "")
    if node_key:
        g.owned_node(project, node_key)
    file = request.files.get("file")
    data = file.read(MAX_BYTES + 1) if file else b""
    mime = sniff(data)
    if not data:
        return _gallery(project, node_key, "Wybierz plik graficzny.")
    if len(data) > MAX_BYTES:
        return _gallery(project, node_key, "Plik jest za duży (maks. 2 MB).")
    if mime is None:
        return _gallery(project, node_key, "To nie jest obraz PNG, JPEG, WebP ani GIF.")
    if Attachment.query.filter_by(project_id=project.id).count() >= MAX_PER_PROJECT:
        return _gallery(project, node_key, f"Projekt ma już {MAX_PER_PROJECT} grafik — usuń niepotrzebne.")
    db.session.add(Attachment(project_id=project.id, node_key=node_key, author_id=current_user.id, mime=mime,
                              data=data, filename=(file.filename or "grafika")[:200],
                              caption=(request.form.get("caption") or "").strip()[:200]))
    audit.log("image_added", f"{project.name}: {(file.filename or 'grafika')[:80]}")
    db.session.commit()
    return _hx(_gallery(project, node_key))


def _hx(html):
    resp = Response(html)
    resp.headers["HX-Trigger"] = '{"mapChanged": {}}'
    return resp


def _attachment(project, att_id: int) -> Attachment:
    att = db.session.get(Attachment, att_id)
    if att is None or att.project_id != project.id:
        abort(404)
    return att


def _send(att: Attachment) -> Response:
    resp = Response(att.data, mimetype=att.mime)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.get("/p/<int:project_id>/grafiki/<int:att_id>")
@login_required
def show(project_id, att_id):
    return _send(_attachment(g.project_for(project_id, "view"), att_id))


@bp.get("/s/<token>/grafiki/<int:att_id>")
def show_shared(token, att_id):
    project = Project.query.filter_by(share_token=token).first()
    if project is None:
        abort(404)
    return _send(_attachment(project, att_id))


@bp.post("/p/<int:project_id>/grafiki/<int:att_id>/usun")
@login_required
def delete(project_id, att_id):
    project = g.project_for(project_id, "edit")
    att = _attachment(project, att_id)
    node_key = att.node_key
    db.session.delete(att)
    db.session.commit()
    return _hx(_gallery(project, node_key))


@bp.post("/p/<int:project_id>/grafiki/<int:att_id>/okladka")
@login_required
def cover(project_id, att_id):
    project = g.project_for(project_id, "edit")
    att = _attachment(project, att_id)
    Attachment.query.filter_by(project_id=project.id, is_cover=True).update({"is_cover": False})
    att.is_cover = True
    db.session.commit()
    return _gallery(project, att.node_key)


@bp.get("/p/<int:project_id>/materialy")
@login_required
def materials(project_id):
    project = g.project_for(project_id, "view")
    return render_template("media/materials.html", project=project, node_key="", images=images_of(project),
                           error=None)
