"""Push notification (ntfy) to the owner's phone when a visitor passes the gate.

Without NTFY_URL this is a no-op (no network traffic). Sent from a daemon thread so the visitor
never waits; any failure is only logged.
"""

import logging
import threading
import urllib.request

from flask import current_app

APP = "FlowMap"
TIMEOUT_SECONDS = 5
MAX_BODY = 300

log = logging.getLogger(__name__)


def build_request(url: str, token: str, first_name: str, last_name: str, company: str) -> urllib.request.Request:
    body = f"{first_name} {last_name} ({company}) wszedł do {APP}"[:MAX_BODY]
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Title": f"Nowy gosc: {APP}",
        "Tags": "bell",
        "Priority": "high",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")


def _send(req: urllib.request.Request) -> None:
    try:
        # Scheme limited to http(s) in notify_visitor; URL comes from operator config.
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):  # noqa: S310  # nosec B310
            pass
    except Exception as exc:  # never surface to the visitor
        log.warning("ntfy visitor notification failed: %s", exc)


def _start(req: urllib.request.Request) -> None:
    threading.Thread(target=_send, args=(req,), daemon=True, name="ntfy-visitor").start()


def notify_visitor(first_name: str, last_name: str, company: str) -> None:
    """Fire-and-forget notification about a successfully recorded visitor."""
    try:
        url = current_app.config.get("NTFY_URL") or ""
        if not url:
            return
        if not url.lower().startswith(("https://", "http://")):
            log.warning("NTFY_URL ignored: only http(s) URLs are allowed")
            return
        req = build_request(url, current_app.config.get("NTFY_TOKEN") or "", first_name, last_name, company)
        _start(req)
    except Exception as exc:
        log.warning("ntfy visitor notification not started: %s", exc)
