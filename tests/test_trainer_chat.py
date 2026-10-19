from types import SimpleNamespace

import anthropic
import pytest

from app.ai import client as ai
from app.ai.client import AIError
from app.extensions import db
from app.models import Evaluation, Project, TrainerMessage
from app.trainer.chat import reply, system_prompt
from tests.test_collaborators import team  # noqa: F401
from tests.test_projects import new_project


def fake_text(monkeypatch, app, *answers):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    queue, calls = list(answers), []

    def create(**kw):
        calls.append(kw)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=answer)])

    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    return calls


def test_system_prompt_depends_on_mode_and_includes_context(auth_client, user):
    p = new_project(auth_client)
    db.session.add(Evaluation(project_id=p.id, user_id=user.id, kind="map", score=61, details={}))
    db.session.commit()
    work = system_prompt(p, user)
    assert "konkretne propozycje" in work and p.start_sentence in work and "61" in work
    p.learning = True
    assert "nie podawaj gotowych rozwiązań" in system_prompt(p, user)


def test_reply_sends_history_to_chat_model(auth_client, app, user, monkeypatch):
    calls = fake_text(monkeypatch, app, "Kto przyjmuje zgłoszenie?", "Dobrze, a co przy braku płatności?")
    p = new_project(auth_client)
    assert reply(p, user, "Od czego zacząć?") == "Kto przyjmuje zgłoszenie?"
    reply(p, user, "Recepcja")
    assert calls[1]["model"] == app.config["ANTHROPIC_CHAT_MODEL"]
    assert [m["role"] for m in calls[1]["messages"]] == ["user", "assistant", "user"]
    assert calls[1]["messages"][-1]["content"] == "Recepcja"
    assert TrainerMessage.query.filter_by(project_id=p.id).count() == 4


def test_api_error_becomes_ai_error_and_saves_nothing(auth_client, app, user, monkeypatch):
    request = SimpleNamespace(method="POST", url="https://api.anthropic.com")
    fake_text(monkeypatch, app, anthropic.APIConnectionError(request=request))
    p = new_project(auth_client)
    with pytest.raises(AIError):
        reply(p, user, "Pytanie")
    assert TrainerMessage.query.count() == 0


def test_chat_panel_routes(auth_client, app, monkeypatch):
    p = new_project(auth_client)
    assert "Trener wymaga AI" in auth_client.get(f"/p/{p.id}/trener").get_data(as_text=True)
    fake_text(monkeypatch, app, "Zacznij od zdarzenia startowego.")
    html = auth_client.get(f"/p/{p.id}/trener").get_data(as_text=True)
    assert 'name="text"' in html
    html = auth_client.post(f"/p/{p.id}/trener", data={"text": "Od czego zacząć?"}).get_data(as_text=True)
    assert "Od czego zacząć?" in html and "Zacznij od zdarzenia startowego." in html
    html = auth_client.post(f"/p/{p.id}/trener", data={"text": "  "}).get_data(as_text=True)
    assert "Napisz pytanie" in html and TrainerMessage.query.count() == 2
    html = auth_client.post(f"/p/{p.id}/trener", data={"text": "x" * 2001}).get_data(as_text=True)
    assert "2000" in html and TrainerMessage.query.count() == 2
    assert f"/p/{p.id}/trener" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    assert f"/p/{p.id}/trener" in auth_client.get(f"/p/{p.id}/projekt-aplikacji").get_data(as_text=True)


def test_threads_are_private_and_outsider_blocked(team, app, monkeypatch):  # noqa: F811
    p = team["project"]
    fake_text(monkeypatch, app, "Odpowiedź dla widza")
    team["viewer"].post(f"/p/{p.id}/trener", data={"text": "Pytanie widza"})
    assert "Pytanie widza" not in team["owner"].get(f"/p/{p.id}/trener").get_data(as_text=True)
    assert team["outsider"].get(f"/p/{p.id}/trener").status_code == 404
    assert Project.query.get(p.id) is not None
