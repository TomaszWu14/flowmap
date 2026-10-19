from app.models import Evaluation
from app.trainer.rubric import mix
from tests.test_projects import new_project
from tests.test_spec_review import fake

AI_OK = {"criteria": [
    {"code": "naming", "score": 4, "reason": "Kroki nazwane czasownikami"},
    {"code": "business", "score": 3, "reason": "Brak kroku obsługi rezygnacji"},
    {"code": "exceptions", "score": 2, "reason": "Nie ma ścieżki dla nieobecności klienta"},
    {"code": "decisions", "score": 5, "reason": "Bramki mają komplet odpowiedzi"}],
    "top_fix": "Dodaj ścieżkę „klient nie przyszedł na wizytę”."}


def test_mix_weights_rules_and_ai():
    results = [{"kind": "map", "label": "Mapa", "score": 80, "criteria": []}]
    out = mix(results, {"criteria": AI_OK["criteria"], "top_fix": AI_OK["top_fix"], "pct": 70})
    assert out[0]["score"] == round(0.7 * 80 + 0.3 * 70) and out[0]["rules_score"] == 80
    assert out[0]["ai"]["top_fix"].startswith("Dodaj")


def test_ai_evaluation_saves_mixed_scores(auth_client, app, monkeypatch):
    calls = fake(monkeypatch, app, AI_OK)
    p = new_project(auth_client)
    assert "Oceń z AI" in auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
    assert auth_client.post(f"/p/{p.id}/ocena/ai").status_code == 302
    assert len(calls) == 1 and calls[0]["tools"][0]["name"] == "assess_quality"
    rows = Evaluation.query.filter_by(project_id=p.id).all()
    assert len(rows) == 2 and {r.source for r in rows} == {"mixed"}
    assert all(r.score == round(0.7 * r.details["rules_score"] + 0.3 * 70) for r in rows)
    html = auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
    assert "Ocena AI" in html and "klient nie przyszedł" in html and "Wyjątki branżowe" in html


def test_ai_failure_falls_back_to_rules(auth_client, app, monkeypatch):
    fake(monkeypatch, app, {"criteria": "zle"}, {"x": 1})
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/ocena/ai")
    rows = Evaluation.query.filter_by(project_id=p.id).all()
    assert len(rows) == 2 and {r.source for r in rows} == {"rules"}
    assert "nieudana" in auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)


def test_ai_button_hidden_without_key(auth_client):
    p = new_project(auth_client)
    assert "Oceń z AI" not in auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
