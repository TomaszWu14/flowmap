from datetime import date, datetime, timedelta

import pytest

from app import settings
from app.ai import client as ai
from app.models import AiUsage
from app.text import warsaw_midnight_utc, warsaw_today
from tests.test_admin import make_admin
from tests.test_ai import fake_ai  # noqa: F401 — fixture


def test_polish_midnight_in_utc_winter_and_summer():
    assert warsaw_midnight_utc(date(2026, 1, 15)) == datetime(2026, 1, 14, 23, 0)
    assert warsaw_midnight_utc(date(2026, 7, 1)) == datetime(2026, 6, 30, 22, 0)


def test_monthly_budget_stops_ai_and_warns_admin(client, db, app, fake_ai):  # noqa: F811
    admin = make_admin(client, db)
    calls = fake_ai()  # any SDK call would pop from an empty list and fail
    client.post("/admin/settings", data={"ai_daily_limit": "50", "ai_enabled": "on", "ai_monthly_budget": "1",
                                         "ai_model": "claude-sonnet-5-5", "ai_chat_model": "claude-sonnet-5-5"})
    db.session.add(AiUsage(user_id=admin.id, feature="draft_process_map", model="claude-sonnet-5-5",
                           input_tokens=1, output_tokens=1, cost_usd=0.85))
    db.session.commit()
    assert "85% miesięcznego budżetu" in client.get("/admin/").get_data(as_text=True)
    db.session.add(AiUsage(user_id=admin.id, feature="draft_process_map", model="claude-sonnet-5-5",
                           input_tokens=1, output_tokens=1, cost_usd=0.2))
    db.session.commit()
    with app.test_request_context():
        from flask_login import login_user

        login_user(admin)
        assert "budżet AI został wyczerpany" in ai.spend_ai_request()
    assert "AI jest wstrzymane" in client.get("/admin/").get_data(as_text=True)
    assert calls.calls == []


def test_model_chosen_in_admin_is_used(client, db, app, fake_ai):  # noqa: F811
    make_admin(client, db)
    resp = client.post("/admin/settings", data={"ai_daily_limit": "50", "ai_enabled": "on", "ai_monthly_budget": "0",
                                                "ai_model": "gpt-5", "ai_chat_model": "claude-sonnet-5-5"})
    assert "Wybierz model z cennika" in client.get(resp.headers["Location"]).get_data(as_text=True)
    client.post("/admin/settings", data={"ai_daily_limit": "50", "ai_enabled": "on", "ai_monthly_budget": "0",
                                         "ai_model": "claude-haiku-4-5", "ai_chat_model": "claude-sonnet-5-5"})
    assert settings.get("ai_model") == "claude-haiku-4-5"
    calls = fake_ai({"steps": [], "edges": []}, {"steps": [], "edges": []})  # invalid twice: model is what matters
    with app.test_request_context(), pytest.raises(ai.AIError):
        ai.call_tool("x", ai.DRAFT_TOOL, ai.AiDraft)
    assert calls.calls[0]["model"] == "claude-haiku-4-5"
    assert "claude-haiku-4-5" in client.get("/admin/koszty").get_data(as_text=True)


def test_today_counts_from_polish_midnight(client, db, app):
    admin = make_admin(client, db)
    today_start = warsaw_midnight_utc(warsaw_today())
    db.session.add_all([
        AiUsage(user_id=admin.id, feature="x", model="m", input_tokens=1, output_tokens=1, cost_usd=0.5,
                created_at=today_start.replace(microsecond=1)),
        AiUsage(user_id=admin.id, feature="x", model="m", input_tokens=1, output_tokens=1, cost_usd=0.25,
                created_at=today_start - timedelta(minutes=1)),
    ])
    db.session.commit()
    html = client.get("/admin/koszty").get_data(as_text=True)
    assert "$0.5000" in html and "Ten miesiąc" in html
