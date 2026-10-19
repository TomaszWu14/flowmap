from app.extensions import db
from app.flow import graph as g
from app.models import Project
from tests.test_projects import new_project
from tests.test_spec_review import fake


def step(type, title, actor="System"):
    return {"type": type, "title": title, "actor": actor, "description": "", "branches": []}


def setup_decision(auth_client):
    p = new_project(auth_client, template="none")
    project = Project.query.get(p.id)
    dec = g.add_node(project, "decision", "Czy termin jest wolny?", "System", data={"branches": ["tak", "nie"]})
    g.add_edge(project, project.nodes[0], dec)
    g.save_version(project, "setup")
    db.session.commit()
    return p, dec.key


def test_fill_proposes_then_applies_one_and_all(auth_client, app, monkeypatch):
    p, dec = setup_decision(auth_client)
    calls = fake(monkeypatch, app, {"items": [
        {"node_key": dec, "slot": "tak", "summary": "Rezerwacja i potwierdzenie",
         "steps": [step("automation", "Rezerwacja terminu"), step("end", "Wizyta umówiona")]},
        {"node_key": dec, "slot": "nie", "summary": "Brak terminu",
         "steps": [step("screen", "Komunikat: brak terminu", "Klient"), step("end", "Koniec")]},
        {"node_key": dec, "slot": "nie", "summary": "duplikat", "steps": [step("end", "X")]},
        {"node_key": "brak", "slot": "", "summary": "zmyślony klucz", "steps": [step("end", "Y")]},
    ]})
    html = auth_client.post(f"/p/{p.id}/guard/fill").get_data(as_text=True)
    assert len(calls) == 1 and "Rezerwacja i potwierdzenie" in html
    assert "zmyślony" not in html and "duplikat" not in html
    from app.models import QuestionLog
    log = QuestionLog.query.filter_by(kind="fill").one()
    assert len(log.options["items"]) == 2
    r = auth_client.post(f"/p/{p.id}/guard/fill/apply", data={"log_id": log.id, "index": 0})
    assert "Dodano 1." in r.get_data(as_text=True) and "mapChanged" in r.headers["HX-Trigger"]
    auth_client.post(f"/p/{p.id}/guard/fill/apply", data={"log_id": log.id, "index": "all"})
    project = Project.query.get(p.id)
    node = project.node_by_key(dec)
    assert {(e.label, e.target.title) for e in project.edges if e.source_id == node.id} == {
        ("tak", "Rezerwacja terminu"), ("nie", "Komunikat: brak terminu")}
    app.config["ANTHROPIC_API_KEY"] = ""  # the panel after undo would ask AI for the next step
    auth_client.post(f"/p/{p.id}/undo")
    assert len([e for e in Project.query.get(p.id).edges if e.source.key == dec]) == 1


def test_fill_skips_slot_answered_meanwhile(auth_client, app, monkeypatch):
    p, dec = setup_decision(auth_client)
    fake(monkeypatch, app, {"items": [{"node_key": dec, "slot": "tak", "summary": "Rezerwacja",
                                       "steps": [step("end", "Umówione")]}]})
    auth_client.post(f"/p/{p.id}/guard/fill")
    from app.models import QuestionLog
    log = QuestionLog.query.filter_by(kind="fill").one()
    project = Project.query.get(p.id)
    node = project.node_by_key(dec)
    g.add_edge(project, node, g.add_node(project, "end", "Ręcznie", "System"), "tak")
    db.session.commit()
    r = auth_client.post(f"/p/{p.id}/guard/fill/apply", data={"log_id": log.id, "index": "all"})
    assert "Pominięto 1" in r.get_data(as_text=True)
    assert len([e for e in Project.query.get(p.id).edges if e.source.key == dec and e.label == "tak"]) == 1


def test_fill_needs_ai(auth_client):
    p, _dec = setup_decision(auth_client)
    html = auth_client.get(f"/p/{p.id}/guard").get_data(as_text=True)
    assert "Uzupełnij otwarte gałęzie" not in html
    assert "wymaga klucza" in auth_client.post(f"/p/{p.id}/guard/fill").get_data(as_text=True)
