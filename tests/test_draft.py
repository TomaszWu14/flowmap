from types import SimpleNamespace

from app.ai import client as ai
from app.ai.draft import draft_from_text, guess_type
from app.flow import questions as q
from app.models import Project

TEXT = """Klient zgłasza reklamację przez formularz.
System nadaje numer zgłoszenia i wysyła e-mail.
Czy produkt jest na gwarancji?
Serwisant naprawia produkt.
Kurier zleca odbiór, płatność przy odbiorze.
Klient czeka 3 dni. Koniec."""


def test_heuristic_types_actors_and_branches():
    g = draft_from_text(TEXT)
    types = [n["type"] for n in g["nodes"]]
    assert types == ["start", "automation", "decision", "user_action", "integration", "wait", "end"]
    by = {n["key"]: n for n in g["nodes"]}
    assert by["s0"]["actor"] == "Klient" and by["s1"]["actor"] == "System" and by["s3"]["actor"] == "Serwisant"
    assert by["s2"]["data"]["branches"] == ["tak", "nie"]
    assert {"source": "s2", "target": "s3", "label": "tak", "condition": ""} in g["edges"]
    assert len(g["edges"]) == len(g["nodes"]) - 1


def test_heuristic_edge_cases():
    assert guess_type("Jeśli brak zgody, to odrzucenie") == "decision"
    assert guess_type("Pracownik sprawdza dokumenty") == "user_action"
    g = draft_from_text("- Start\n- Koniec sprawy\n- Dalszy krok")  # 'koniec' only closes on the last line
    assert [n["type"] for n in g["nodes"]] == ["start", "user_action", "user_action"]
    assert len(draft_from_text("\n".join(f"Krok {i}" for i in range(100)))["nodes"]) == 40


def test_from_document_without_ai_leaves_open_branch_for_questions(auth_client):
    r = auth_client.post("/projekty/z-dokumentu", data={"name": "Reklamacje", "text": TEXT, "mode": "quick"})
    assert r.status_code == 302
    p = Project.query.one()
    assert len(p.nodes) == 7 and p.versions[0].description == "Mapa z dokumentu (reguły)"
    pending = q.pending_nodes(p)
    assert [n.type for n in pending] == ["decision"]  # the "nie" branch is asked next
    assert "→ nie" in auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)


def test_from_document_validation(auth_client):
    r = auth_client.post("/projekty/z-dokumentu", data={"name": "X", "text": "za krótko", "mode": "quick"})
    assert r.status_code == 200 and Project.query.count() == 0


def fake_tool(monkeypatch, app, payload):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"

    def create(**kw):
        return SimpleNamespace(stop_reason="tool_use",
                               content=[SimpleNamespace(type="tool_use", name=kw["tools"][0]["name"], input=payload)])

    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_from_document_with_ai(auth_client, app, monkeypatch):
    fake_tool(monkeypatch, app, {
        "steps": [
            {"key": "s0", "type": "start", "title": "Klient zgłasza reklamację", "actor": "Klient", "description": "",
             "branches": []},
            {"key": "s1", "type": "decision", "title": "Czy na gwarancji?", "actor": "System", "description": "",
             "branches": ["tak", "nie"]},
            {"key": "s2", "type": "end", "title": "Naprawa", "actor": "Serwisant", "description": "", "branches": []},
        ],
        "edges": [{"source": "s0", "target": "s1", "label": ""}, {"source": "s1", "target": "s2", "label": "tak"}],
    })
    auth_client.post("/projekty/z-dokumentu", data={"name": "R", "text": TEXT, "mode": "quick"})
    p = Project.query.one()
    assert p.versions[0].description == "Mapa z dokumentu (AI)" and p.start_sentence == "Klient zgłasza reklamację"
    assert [n.type for n in p.nodes] == ["start", "decision", "end"]


def test_from_document_invalid_ai_falls_back(auth_client, app, monkeypatch):
    fake_tool(monkeypatch, app, {"steps": [{"key": "a", "type": "end", "title": "X", "actor": "", "description": "",
                                            "branches": []}] * 2, "edges": []})
    r = auth_client.post("/projekty/z-dokumentu", data={"name": "R", "text": TEXT, "mode": "quick"},
                         follow_redirects=True)
    assert "AI niedostępne" in r.get_data(as_text=True)
    assert Project.query.one().versions[0].description == "Mapa z dokumentu (reguły)"
