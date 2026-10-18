from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from app.ai import client as ai
from app.models import QuestionLog, User
from tests.test_projects import new_project

GOOD = {
    "question": "Co robi klient po wyborze usługi?",
    "options": [
        {"label": "Wybiera termin", "connect_to_key": "",
         "steps": [{"type": "screen", "title": "Kalendarz", "actor": "Klient", "description": "", "branches": []}]},
        {"label": "Loguje się", "connect_to_key": "",
         "steps": [{"type": "decision", "title": "Czy ma konto?", "actor": "System", "description": "",
                    "branches": ["tak"]}]},
        {"label": "Płaci", "connect_to_key": "nie-istnieje",
         "steps": [{"type": "integration", "title": "Płatność", "actor": "System", "description": "",
                    "branches": []}]},
    ],
}


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="text", text="ok"),
            SimpleNamespace(type="tool_use", name=kwargs["tools"][0]["name"], input=item),
        ])


@pytest.fixture
def fake_ai(app, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"

    def install(*responses):
        messages = FakeMessages(responses)
        monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(messages=messages))
        return messages

    return install


def first_question(client, project):
    client.get(f"/p/{project.id}/panel")
    return QuestionLog.query.filter_by(project_id=project.id).order_by(QuestionLog.id.desc()).first()


def test_no_key_means_rules_and_no_sdk_call(auth_client, monkeypatch):
    monkeypatch.setattr(ai, "_client", lambda: pytest.fail("SDK must not be called without a key"))
    p = new_project(auth_client)
    log = first_question(auth_client, p)
    assert log.source == "rules"


def test_ai_question_validated_and_sanitised(auth_client, fake_ai):
    messages = fake_ai(GOOD)
    p = new_project(auth_client)
    log = first_question(auth_client, p)
    assert log.source == "ai"
    opts = log.options["options"]
    assert opts[0]["label"] == "Wybiera termin"
    assert opts[1]["steps"][0]["branches"] == ["tak", "nie"]  # decision always gets >= 2 branches
    assert opts[2]["connect_to"] == ""  # unknown node key dropped
    assert opts[-1]["label"] == "Koniec procesu"
    call = messages.calls[0]
    assert call["tools"][0]["strict"] is True and call["tool_choice"] == {"type": "auto"}
    sent = call["messages"][0]["content"]
    assert "ala@example.com" not in sent  # no account data goes to the model


def test_invalid_payload_retried_once(auth_client, fake_ai):
    messages = fake_ai({"question": "?", "options": []}, GOOD)
    p = new_project(auth_client)
    assert first_question(auth_client, p).source == "ai"
    assert len(messages.calls) == 2


def test_invalid_twice_falls_back_to_rules(auth_client, fake_ai):
    fake_ai({"question": "x"}, {"options": "zle"})
    p = new_project(auth_client)
    log = first_question(auth_client, p)
    assert log.source == "rules"
    assert "AI niedostępne" in log.options["notice"]


def test_api_error_falls_back(auth_client, fake_ai):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_ai(anthropic.APITimeoutError(request=request))
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert "przekroczono czas" in html
    assert "Wybór usługi" in html  # rules tiles shown


def test_daily_limit(auth_client, fake_ai, app, db):
    app.config["AI_DAILY_LIMIT"] = 0
    fake_ai()
    p = new_project(auth_client)
    log = first_question(auth_client, p)
    assert log.source == "rules" and "limit" in log.options["notice"]


def test_consume_ai_request_counter(db):
    u = User(email="x@y.pl", password_hash="x")
    assert u.consume_ai_request(2) and u.consume_ai_request(2)
    assert not u.consume_ai_request(2)


def test_ai_review_suggestion_applied_in_one_click(auth_client, fake_ai, db):
    p = new_project(auth_client)
    start = p.nodes[0]
    fake_ai({"suggestions": [{"problem": "Brak anulowania", "node_key": start.key, "edge_label": "rezygnacja",
                              "steps": [{"type": "end", "title": "Klient rezygnuje", "actor": "Klient",
                                         "description": "", "branches": []}]},
                             {"problem": "Zły klucz", "node_key": "zzz", "edge_label": "", "steps": [
                                 {"type": "end", "title": "X", "actor": "", "description": "", "branches": []}]}]})
    html = auth_client.post(f"/p/{p.id}/guard/review").get_data(as_text=True)
    assert "Brak anulowania" in html and "Zły klucz" not in html
    log = QuestionLog.query.filter_by(project_id=p.id, kind="review").one()
    auth_client.post(f"/p/{p.id}/guard/apply", data={"log_id": log.id, "index": 0})
    assert any(n.title == "Klient rezygnuje" for n in p.nodes)
    assert any(e.label == "rezygnacja" and e.condition == "error" for e in p.edges)


def test_review_without_key_is_friendly(auth_client):
    p = new_project(auth_client)
    html = auth_client.post(f"/p/{p.id}/guard/review").get_data(as_text=True)
    assert "wymaga klucza" in html
