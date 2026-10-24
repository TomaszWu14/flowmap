"""Comments on map steps. Anyone with access comments; editors resolve any, viewers only their own;
authors delete their own, the owner deletes any."""

import json
import re
import smtplib

from flask import Blueprint, abort, current_app, make_response, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..flow import graph as g
from ..mail import mail_enabled, send_mail
from ..models import Comment

bp = Blueprint("comments", __name__)


def open_comment_counts(project) -> dict[str, int]:
    rows = (db.session.query(Comment.node_key, func.count(Comment.id))
            .filter_by(project_id=project.id, resolved=False).group_by(Comment.node_key).all())
    keys = {n.key for n in project.nodes}
    return {k: c for k, c in rows if k in keys}  # comments of deleted steps do not count


MENTION = re.compile(r"@([^\s@,;:()]+@[^\s@,;:()]+\.[a-z]{2,})", re.I)


def notify_mentions(project, node_key: str, body: str) -> str | None:
    """E-mail the project's people mentioned as "@e-mail" in a comment. Returns a note for the author, or None.

    Only the owner and collaborators can be notified — a mention never mails a stranger.
    """
    mentioned = {e.lower().rstrip(".") for e in MENTION.findall(body)}
    if not mentioned:
        return None
    people = [project.owner, *(m.user for m in project.members)]
    targets = [u for u in people if u is not None and u.email.lower() in mentioned and u.id != current_user.id]
    if not targets:
        return "Wzmianka nie trafiła do nikogo: powiadomić można tylko osoby z tego projektu."
    if not mail_enabled():
        return "Wzmianka zapisana, ale e-mail jest wyłączony (brak MAIL_SERVER) — powiadomienia nie wysłano."
    step = project.node_by_key(node_key)
    # nosemgrep: flask-url-for-external-true — host from proxy (Traefik); fixed public URL: open decision
    link = url_for("flow.view", project_id=project.id, _external=True) + f"#krok-{node_key}"
    sent = []
    for user in targets:
        try:
            send_mail(user.email, f"FlowMap: {current_user.email} wspomina o Tobie w „{project.name}”",
                      f"Komentarz przy kroku „{step.title if step else node_key}”:\n\n{body}\n\nOtwórz mapę: {link}\n")
            sent.append(user.email)
        except (OSError, smtplib.SMTPException) as exc:  # a mail failure must not lose the comment
            current_app.logger.warning("mention mail to %s failed: %s", user.email, exc)
    return f"Powiadomiono e-mailem: {', '.join(sent)}." if sent else "Nie udało się wysłać powiadomienia e-mail."


def _render(project, node_key: str, error: str | None = None, changed: bool = False, notice: str | None = None):
    comments = (Comment.query.filter_by(project_id=project.id, node_key=node_key)
                .order_by(Comment.resolved, Comment.id).all())
    html = render_template("comments/_list.html", project=project, node_key=node_key, comments=comments,
                           error=error, notice=notice, can_resolve=project.can_edit)
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
    return _render(project, key, changed=True, notice=notify_mentions(project, key, body[:2000]))


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
