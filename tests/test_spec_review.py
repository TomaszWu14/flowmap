from types import SimpleNamespace

import pytest

from app.ai import client as ai
from app.models import Project
from app.spec.review import apply_proposal
from app.spec.schema import Entity, Field, Proposal, Spec, load_spec
from tests.test_projects import new_project

OK = {"proposals": [
    {"kind": "set_field_type", "target_key": "entity:rezerwacja", "summary": "utworzono to data i godzina",
     "patch": {"field": "utworzono", "type": "datetime", "name": "", "required": False, "to_entity": "", "kind": "",
               "label": "", "final": False, "from": "", "to": "", "entity": "", "read": "", "create": "",
               "update": "", "delete": "", "trigger": "", "channel": "", "recipient_role": "", "category": "",
               "text": ""}},
    {"kind": "add_nfr", "target_key": "", "summary": "Czas odpowiedzi",
     "patch": {"field": "", "type": "", "name": "", "required": False, "to_entity": "", "kind": "", "label": "",
               "final": False, "from": "", "to": "", "entity": "", "read": "", "create": "", "update": "",
               "delete": "", "trigger": "", "channel": "", "recipient_role": "", "category": "performance",
               "text": "Strony < 1 s"}},
]}


def fake(monkeypatch, app, *payloads):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    queue = list(payloads)
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="tool_use", name=kw["tools"][0]["name"], input=queue.pop(0))])

    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    return calls


def spec_of(p):
    return load_spec(Project.query.get(p.id).spec)


def test_review_creates_proposals_then_accept_and_reject(auth_client, app, monkeypatch):
    calls = fake(monkeypatch, app, OK)
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/specyfikacja/przeglad")
    assert len(calls) == 1 and len(spec_of(p).proposals) == 2
    ids = [x.id for x in spec_of(p).proposals]
    auth_client.post(f"/p/{p.id}/specyfikacja/propozycje/{ids[0]}/accept")
    main = spec_of(p).entities[0]
    assert next(f for f in main.fields if f.name == "utworzono").type == "datetime" and main.source == "ai"
    auth_client.post(f"/p/{p.id}/specyfikacja/propozycje/{ids[1]}/reject")
    assert spec_of(p).proposals == [] and not any(n.text == "Strony < 1 s" for n in spec_of(p).nfr)


def test_review_invalid_then_message(auth_client, app, monkeypatch):
    fake(monkeypatch, app, {"proposals": "zle"}, {"x": 1})
    p = new_project(auth_client)
    r = auth_client.post(f"/p/{p.id}/specyfikacja/przeglad", follow_redirects=True)
    assert "Przegląd AI nieudany" in r.get_data(as_text=True) and spec_of(p).proposals == []


def test_review_requires_ai_and_limit(auth_client, app):
    p = new_project(auth_client)
    r = auth_client.post(f"/p/{p.id}/specyfikacja/przeglad", follow_redirects=True)
    assert "wymaga klucza" in r.get_data(as_text=True)


def test_stale_proposal_cannot_be_applied():
    spec = Spec(entities=[Entity(key="entity:a", name="A", fields=[Field(key="f", name="x")])])
    with pytest.raises(ValueError, match="nieaktualna"):
        apply_proposal(spec, Proposal(id="1", kind="set_field_type", target_key="entity:brak", summary="s",
                                      patch={"field": "x", "type": "money"}))
