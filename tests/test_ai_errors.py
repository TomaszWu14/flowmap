import anthropic
import httpx2 as httpx
import pytest

from app.ai import client as ai
from app.models import AuditEvent
from tests.test_admin import login
from tests.test_ai import fake_ai  # noqa: F401 — fixture

REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def api_error(status, message):
    cls = anthropic.BadRequestError if status == 400 else anthropic.InternalServerError
    return cls(message, response=httpx.Response(status, request=REQ), body=None)


@pytest.mark.parametrize(("status", "message", "expected", "logged"), [
    (400, "You have reached your specified API usage limits.", "wyczerpany limit wydatków", True),
    (400, "Your credit balance is too low", "wyczerpany limit wydatków", True),
    (529, "Overloaded", "przeciążone", False),
    (500, "Internal error", r"chwilowy błąd po stronie API \(500\)", False),
    (400, "tools.0: invalid schema", "błąd API 400", True),
])
def test_api_errors_become_polish_messages(app, fake_ai, status, message, expected, logged):  # noqa: F811
    fake_ai(api_error(status, message))
    with app.test_request_context(), pytest.raises(ai.AIError, match=expected):
        ai.call_tool("x", ai.DRAFT_TOOL, ai.AiDraft)
    assert (AuditEvent.query.filter_by(action="ai_error").count() == 1) is logged


def test_admin_sees_banner_after_ai_error(client, db, app, fake_ai):  # noqa: F811
    from tests.conftest import make_user

    admin = make_user("admin@example.com")
    admin.is_admin = True
    db.session.commit()
    login(client, admin.email)
    assert "AI nie działa" not in client.get("/admin/").get_data(as_text=True)
    fake_ai(api_error(400, "You have reached your specified API usage limits."))
    with app.test_request_context(), pytest.raises(ai.AIError):
        ai.call_tool("x", ai.DRAFT_TOOL, ai.AiDraft)
    html = client.get("/admin/").get_data(as_text=True)
    assert "AI nie działa: wyczerpany limit wydatków" in html
