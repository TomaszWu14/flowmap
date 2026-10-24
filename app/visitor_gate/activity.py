"""What a gate visitor looks at: screens viewed, time on the demo, most visited sections.

Counted in an after_request hook for successful full-page HTML GETs from a visitor whose signed
session carries the record id (no IP, no user agent). Any failure is logged; the response is untouched.
"""

import logging
import re

from flask import current_app, request

from ..extensions import db
from ..models import DemoVisitor, utcnow
from .notify import notify_engaged

MAX_SECTIONS = 20
SECTION_LEN = 40
VISITOR_ID_KEY = "visitor_id"
SKIP_ENDPOINTS = {"healthz", "static"}
SKIP_PREFIXES = ("/api/", "/static/")

log = logging.getLogger(__name__)


def section_of(path: str) -> str:
    """First path segment, [a-z0-9_-] only, max 40 chars; '/' -> 'start'; '' when nothing is left."""
    first = (path or "/").lstrip("/").split("/", 1)[0]
    if not first:
        return "start"
    return re.sub(r"[^a-z0-9_-]", "", first.lower())[:SECTION_LEN]


def countable(response) -> bool:
    return (request.method == "GET" and response.status_code < 400 and response.mimetype == "text/html"
            and not request.headers.get("HX-Request") and request.endpoint not in SKIP_ENDPOINTS
            and not request.path.startswith(SKIP_PREFIXES))


def record_view(visitor_id: int, path: str) -> None:
    visitor = db.session.get(DemoVisitor, visitor_id, with_for_update=True)
    if visitor is None:  # deleted by retention or a stale id
        return
    visitor.page_views = (visitor.page_views or 0) + 1
    visitor.last_seen_at = utcnow()
    name = section_of(path)
    sections = dict(visitor.sections or {})
    if name and (name in sections or len(sections) < MAX_SECTIONS):
        sections[name] = int(sections.get(name, 0)) + 1
        visitor.sections = sections  # new dict, so the JSON column is marked dirty
    db.session.commit()
    threshold = current_app.config.get("NTFY_ENGAGED_VIEWS") or 0
    if threshold > 0 and visitor.page_views == threshold:
        notify_engaged(visitor.first_name, visitor.last_name, visitor.company, visitor.page_views)


def track(visitor_id, path: str, response=None) -> None:
    """Count one view (when the response is a countable page); never raises."""
    if not isinstance(visitor_id, int) or isinstance(visitor_id, bool):
        return
    try:
        if response is None or countable(response):
            record_view(visitor_id, path)
    except Exception as exc:
        db.session.rollback()
        log.warning("visitor activity not recorded: %s", exc)


def top_sections(sections, limit: int = 3) -> list[str]:
    items = (sections or {}).items() if isinstance(sections, dict) else []
    return [name for name, _ in sorted(items, key=lambda kv: (-kv[1], kv[0]))[:limit]]


def visit_minutes(visitor) -> str:
    if not visitor.last_seen_at:
        return "—"
    seconds = (visitor.last_seen_at - visitor.created_at).total_seconds()
    return f"ok. {max(1, round(seconds / 60))} min"
