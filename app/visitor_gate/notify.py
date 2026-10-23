"""Push notifications (ntfy) to the owner's phone about demo visitors.

Without NTFY_URL this is a no-op (no network traffic). Sent from a daemon thread so the visitor
never waits; any failure is only logged. Companies listed in NTFY_WATCH_COMPANIES (comma-separated
phrases, configured only in the environment) raise the push to urgent.
"""

import logging
import re
import threading
import unicodedata
import urllib.request

from flask import current_app

APP = "FlowMap"
TIMEOUT_SECONDS = 5
MAX_BODY = 300
MIN_PHRASE = 2

log = logging.getLogger(__name__)


def normalize(text: str) -> str:
    """casefold, strip diacritics (NFKD; also Polish ł), collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", (text or "").casefold().replace("ł", "l"))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", plain).strip()


def is_watched(company: str, phrases: str) -> bool:
    name = normalize(company)
    for phrase in (phrases or "").split(","):
        needle = normalize(phrase)
        if len(needle) >= MIN_PHRASE and needle in name:
            return True
    return False


def _request(url: str, token: str, body: str, title: str, tags: str, priority: str) -> urllib.request.Request:
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Title": title,
        "Tags": tags,
        "Priority": priority,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, data=body[:MAX_BODY].encode("utf-8"), headers=headers, method="POST")


def build_request(url: str, token: str, first_name: str, last_name: str, company: str,
                  watched: bool = False) -> urllib.request.Request:
    body = f"{first_name} {last_name} ({company}) wszedł do {APP}"
    if watched:
        return _request(url, token, "⚠️ " + body, f"UWAGA firma z listy: {APP}", "rotating_light", "urgent")
    return _request(url, token, body, f"Nowy gosc: {APP}", "bell", "high")


def build_engaged_request(url: str, token: str, first_name: str, last_name: str, company: str, views: int,
                          watched: bool = False) -> urllib.request.Request:
    body = f"{first_name} {last_name} ({company}) obejrzał już {views} ekranów w {APP}"
    return _request(url, token, body, f"Gosc oglada demo: {APP}", "eyes", "urgent" if watched else "default")


def _send(req: urllib.request.Request) -> None:
    try:
        # Scheme limited to http(s) in _dispatch; URL comes from operator config.
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):  # noqa: S310  # nosec B310
            pass
    except Exception as exc:  # never surface to the visitor
        log.warning("ntfy visitor notification failed: %s", exc)


def _start(req: urllib.request.Request) -> None:
    threading.Thread(target=_send, args=(req,), daemon=True, name="ntfy-visitor").start()


def _dispatch(build, *args) -> None:
    try:
        url = current_app.config.get("NTFY_URL") or ""
        if not url:
            return
        if not url.lower().startswith(("https://", "http://")):
            log.warning("NTFY_URL ignored: only http(s) URLs are allowed")
            return
        token = current_app.config.get("NTFY_TOKEN") or ""
        company = args[2]
        watched = is_watched(company, current_app.config.get("NTFY_WATCH_COMPANIES") or "")
        _start(build(url, token, *args, watched=watched))
    except Exception as exc:
        log.warning("ntfy visitor notification not started: %s", exc)


def notify_visitor(first_name: str, last_name: str, company: str) -> None:
    """Fire-and-forget notification about a successfully recorded visitor."""
    _dispatch(build_request, first_name, last_name, company)


def notify_engaged(first_name: str, last_name: str, company: str, views: int) -> None:
    """Fire-and-forget notification: the visitor has viewed NTFY_ENGAGED_VIEWS screens."""
    _dispatch(build_engaged_request, first_name, last_name, company, views)
