"""Comments on map steps. Anyone with access comments; editors resolve any, viewers only their own;
authors delete their own, the owner deletes any."""

import json

from flask import Blueprint, abort, make_response, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..flow import graph as g
from ..models import Comment

bp = Blueprint("comments", __name__)


def open_comment_counts(project) -> dict[str, int]:
    rows = (db.session.query(Comment.node_key, func.count(Comment.id))
            .filter_by(project_id=project.id, resolved=False).group_by(Comment.node_key).all())
    keys = {n.key for n in project.nodes}
    return {k: c for k, c in rows if k in keys}  # comments of deleted steps do not count


def _render(project, node_key: str, error: str | None = None, changed: bool = False):
    comments = (Comment.query.filter_by(project_id=project.id, node_key=node_key)
                .order_by(Comment.resolved, Comment.id).all())
    html = render_template("comments/_list.html", project=project, node_key=node_key, comments=comments,
                           error=error, can_resolve=project.can_edit)
    resp = make_response(html)
    if changed:
        resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": node_key}})
    return resp


@bp.get("/p/<int:project_id>/node/<key>/komentarze")
@login_required
def list_comments(project_id, key):
    project = g.project_for(project_id, "view")
    g.owned_node(project, key)
    return _render(project, key)


@bp.post("/p/<int:project_id>/node/<key>/komentarze")
@login_required
def add_comment(project_id, key):
    project = g.project_for(project_id, "view")
    g.owned_node(project, key)
    body = (request.form.get("body") or "").strip()
    if not body:
        return _render(project, key, error="Komentarz nie może być pusty.")
    db.session.add(Comment(project_id=project.id, node_key=key, author_id=current_user.id, body=body[:2000]))
    db.session.commit()
    return _render(project, key, changed=True)


def _comment(project, comment_id) -> Comment:
    comment = db.session.get(Comment, comment_id)
    if comment is None or comment.project_id != project.id:
        abort(404)
    return comment


@bp.post("/p/<int:project_id>/komentarze/<int:comment_id>/rozwiaz")
@login_required
def toggle_resolved(project_id, comment_id):
    project = g.project_for(project_id, "view")
    comment = _comment(project, comment_id)
    if not project.can_edit and comment.author_id != current_user.id:
        abort(403, "Z podglądem możesz rozwiązywać tylko własne komentarze.")
    comment.resolved = not comment.resolved
    db.session.commit()
    return _render(project, comment.node_key, changed=True)


@bp.post("/p/<int:project_id>/komentarze/<int:comment_id>/usun")
@login_required
def delete_comment(project_id, comment_id):
    project = g.project_for(project_id, "view")
    comment = _comment(project, comment_id)
    if comment.author_id != current_user.id and project.current_role != "owner":
        abort(403, "Cudze komentarze może usuwać tylko właściciel projektu.")
    key = comment.node_key
    db.session.delete(comment)
    db.session.commit()
    return _render(project, key, changed=True)
