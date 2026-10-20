from types import SimpleNamespace

import pytest

from app.ai import client as ai
from app.ai.pricing import cost_usd
from app.extensions import db
from app.models import AiUsage, User
from tests.test_exercise_grading import graded, submit
from tests.test_exercises import start


def test_cost_from_price_table():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 100_000) == pytest.approx(2 + 1)
    assert cost_usd("claude-haiku-4-5", 2000, 1000) == pytest.approx(0.002 + 0.005)
    assert cost_usd("nieznany-model", 10, 10) is None


def fake_with_usage(monkeypatch, app, payload, tokens=(3000, 1200)):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"

    def create(**kw):
        return SimpleNamespace(stop_reason="tool_use", usage=SimpleNamespace(input_tokens=tokens[0],
                                                                             output_tokens=tokens[1]),
                               content=[SimpleNamespace(type="tool_use", name=kw["tools"][0]["name"], input=payload)])

    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_every_call_is_logged_even_when_the_answer_is_rejected(auth_client, app, user, monkeypatch):
    _, p = start(auth_client)
    app.config["ANTHROPIC_MODEL"] = "claude-sonnet-5-5"
    fake_with_usage(monkeypatch, app, graded())
    submit(auth_client, p)
    [row] = AiUsage.query.all()
    assert (row.feature, row.model, row.input_tokens, row.output_tokens, row.user_id) == (
        "grade_exercise", "claude-sonnet-5-5", 3000, 1200, user.id)
    assert row.cost_usd == pytest.approx(3000 * 2e-6 + 1200 * 10e-6)
    fake_with_usage(monkeypatch, app, graded(drop=1))  # invalid twice -> AIError, but both calls were billed
    submit(auth_client, p)
    assert AiUsage.query.count() == 3


def test_admin_cost_page(auth_client, app, user):
    db.session.add_all([AiUsage(user_id=user.id, feature="grade_exercise", model="claude-sonnet-5-5",
                                input_tokens=3000, output_tokens=1200, cost_usd=0.018),
                        AiUsage(user_id=user.id, feature="trainer_chat", model="claude-sonnet-5-5",
                                input_tokens=1600, output_tokens=900, cost_usd=0.0122)])
    db.session.commit()
    assert auth_client.get("/admin/koszty").status_code == 404  # admin pages stay hidden
    user.is_admin = True
    db.session.commit()
    html = auth_client.get("/admin/koszty").get_data(as_text=True)
    assert "Koszty AI" in html and "Ocena ćwiczenia" in html and "Czat trenera" in html
    assert "$0.0302" in html and user.email in html and "claude-sonnet-5-5" in html
    assert "$0.0302" in auth_client.get("/admin/").get_data(as_text=True)  # 30-day tile


def test_usage_without_login_is_kept_anonymous(app):
    with app.test_request_context():
        ai._log_usage("draft_process_map", "claude-sonnet-5-5", SimpleNamespace(input_tokens=10, output_tokens=5))
    row = AiUsage.query.one()
    assert row.user_id is None and row.cost_usd > 0
    assert User.query.count() == 0
