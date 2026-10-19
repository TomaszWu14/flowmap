from types import SimpleNamespace

import pytest

from app.ai import client as ai
from app.models import Project
from app.spec.review import apply_proposal
from app.spec.schema import Entity, Field, Proposal, Role, Spec, StateMachine, Status, load_spec
from tests.test_projects import new_project

OK = {"proposals": [
    {"kind": "set_field_type", "target_key": "entity:rezerwacja", "summary": "utworzono to data i godzina",
     "patch": {"field": "utworzono", "type": "datetime", "name": "", "required": False, "to_entity": "", "kind": "",
               "label": "", "final": False, "from": "", "to": "", "entity": "", "read": "", "create": "",
               "update": "", "delete": "", "trigger": "", "channel": "", "recipient_role": "", "category": "",
               "text": "", "condition": "", "result": ""}},
    {"kind": "add_nfr", "target_key": "", "summary": "Czas odpowiedzi",
     "patch": {"field": "", "type": "", "name": "", "required": False, "to_entity": "", "kind": "", "label": "",
               "final": False, "from": "", "to": "", "entity": "", "read": "", "create": "", "update": "",
               "delete": "", "trigger": "", "channel": "", "recipient_role": "", "category": "performance",
               "text": "Strony < 1 s", "condition": "", "result": ""}},
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


def test_invalid_patch_flashes_polish_not_raw_schema_text(auth_client, app, db):
    p = new_project(auth_client)
    spec = spec_of(p)
    entity = spec.entities[0]
    field_name = entity.fields[0].name
    spec.proposals = [Proposal(id="bad1", kind="set_field_type", target_key=entity.key, summary="s",
                               patch={"field": field_name, "type": "varchar"})]
    project = Project.query.get(p.id)
    project.spec = spec.model_dump(mode="json")
    db.session.commit()
    r = auth_client.post(f"/p/{p.id}/specyfikacja/propozycje/bad1/accept", follow_redirects=True)
    assert r.status_code == 200
    assert "niepoprawne dane" in r.get_data(as_text=True)
    after = spec_of(p)
    assert len(after.proposals) == 1
    assert after.entities[0].fields[0].type != "varchar"


def test_accept_all_skips_invalid_patch(auth_client, app, db):
    p = new_project(auth_client)
    spec = spec_of(p)
    entity = spec.entities[0]
    field_name = entity.fields[0].name
    spec.proposals = [Proposal(id="bad1", kind="set_field_type", target_key=entity.key, summary="s",
                               patch={"field": field_name, "type": "varchar"})]
    project = Project.query.get(p.id)
    project.spec = spec.model_dump(mode="json")
    db.session.commit()
    r = auth_client.post(f"/p/{p.id}/specyfikacja/propozycje/wszystkie", follow_redirects=True)
    assert r.status_code == 200
    assert "Pominięto 1" in r.get_data(as_text=True)
    assert len(spec_of(p).proposals) == 1


def test_set_permission_rejects_unknown_entity():
    spec = Spec(roles=[Role(key="role:a", name="A")])
    with pytest.raises(ValueError, match="nieaktualna"):
        apply_proposal(spec, Proposal(id="1", kind="set_permission", target_key="role:a", summary="s",
                                      patch={"entity": "entity:brak", "read": "all"}))


def test_set_permission_rejects_invalid_value():
    spec = Spec(entities=[Entity(key="entity:a", name="A")], roles=[Role(key="role:a", name="A")])
    with pytest.raises(ValueError, match="nieaktualna"):
        apply_proposal(spec, Proposal(id="1", kind="set_permission", target_key="role:a", summary="s",
                                      patch={"entity": "entity:a", "read": "write"}))


def test_add_transition_rejects_unknown_status():
    spec = Spec(states=[StateMachine(key="state:a", entity="entity:a",
                                     statuses=[Status(name="nowa"), Status(name="zamkniete")])])
    with pytest.raises(ValueError, match="nieaktualna"):
        apply_proposal(spec, Proposal(id="1", kind="add_transition", target_key="state:a", summary="s",
                                      patch={"from": "nowa", "to": "brak"}))


def test_proposal_for_wrong_section_is_rejected_in_polish():
    spec = Spec(roles=[Role(key="role:a", name="A")])
    with pytest.raises(ValueError, match="niewłaściwy element"):
        apply_proposal(spec, Proposal(id="1", kind="set_field_type", target_key="role:a", summary="s",
                                      patch={"field": "x", "type": "money"}))


def test_second_review_appends_and_panel_is_polish(auth_client, app, monkeypatch):
    fake(monkeypatch, app, OK, OK)
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/specyfikacja/przeglad")
    html = auth_client.post(f"/p/{p.id}/specyfikacja/przeglad", follow_redirects=True).get_data(as_text=True)
    assert len(spec_of(p).proposals) == 4
    assert "zmiana typu pola" in html and "set_field_type" not in html
