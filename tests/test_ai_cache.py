from datetime import timedelta

import pytest

from app.ai import client as ai
from app.models import AiCache, utcnow
from tests.test_ai import fake_ai  # noqa: F401 — fixture

DRAFT = {"steps": [{"key": "s", "type": "start", "title": "Klient zamawia", "actor": "Klient", "description": "",
                    "branches": []},
                   {"key": "e", "type": "end", "title": "Koniec", "actor": "System", "description": "",
                    "branches": []}],
         "edges": [{"source": "s", "target": "e", "label": ""}]}


def draft(app, prompt="opis"):
    with app.test_request_context():
        return ai.call_tool(prompt, ai.DRAFT_TOOL, ai.AiDraft)


def test_same_request_is_served_from_cache(app, fake_ai):  # noqa: F811
    calls = fake_ai(DRAFT, DRAFT)
    first, second = draft(app), draft(app)
    assert first == second and len(calls.calls) == 1
    draft(app, "inny opis")  # different prompt → new call
    assert len(calls.calls) == 2


def test_cache_expires_and_ignores_other_model(app, fake_ai):  # noqa: F811
    calls = fake_ai(DRAFT, DRAFT, DRAFT)
    draft(app)
    AiCache.query.one().created_at = utcnow() - timedelta(days=ai.CACHE_DAYS + 1)
    draft(app)
    assert len(calls.calls) == 2
    app.config["ANTHROPIC_MODEL"] = "claude-haiku-4-5"
    draft(app)
    assert len(calls.calls) == 3


def test_rejected_answer_is_not_cached(app, fake_ai):  # noqa: F811
    fake_ai({"steps": []}, {"steps": []})
    with pytest.raises(ai.AIError):
        draft(app)
    assert AiCache.query.count() == 0
