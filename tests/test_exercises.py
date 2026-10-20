import json

import pytest

from app.exercises import catalog
from app.extensions import db
from app.models import ExerciseAttempt, Project
from tests.conftest import PASSWORD, make_user

VALID = {"key": "x", "title": "T", "domain": "HR", "level": "podstawowy", "brief": "Zadanie.",
         "start_sentence": "Ktoś coś robi", "stage1": ["Mapa ma start"], "stage2": ["Są przypadki użycia"]}


def test_repository_exercises_are_valid():
    exercises = catalog.load(catalog.DATA_DIR)
    assert set(exercises) == {"urlopy", "reklamacje", "p2p", "o2c", "onboarding", "incydenty-it", "logistyka"}
    assert {ex.level for ex in exercises.values()} == {"podstawowy", "zaawansowany"}
    for key, ex in exercises.items():
        assert ex.key == key and ex.stage1 and ex.stage2


@pytest.mark.parametrize("broken", [
    {"title": None}, {"level": "ekspert"}, {"stage1": []}, {"key": "inny"}, {"extra": 1},
])
def test_broken_file_names_the_file(tmp_path, broken):
    (tmp_path / "x.json").write_text(json.dumps({**VALID, **broken}), encoding="utf-8")
    with pytest.raises(ValueError, match="x.json"):
        catalog.load(tmp_path)


def test_catalog_lists_exercises_without_expectations(auth_client):
    html = auth_client.get("/cwiczenia").get_data(as_text=True)
    ex = catalog.get("urlopy")
    assert ex.title in html and catalog.get("reklamacje").title in html
    assert ex.stage1[0] not in html and ex.stage2[0] not in html
    assert 'href="/cwiczenia"' in auth_client.get("/projekty").get_data(as_text=True)


def start(client, key="urlopy"):
    r = client.post(f"/cwiczenia/{key}/start")
    project = Project.query.order_by(Project.id.desc()).first()
    return r, project


def test_start_creates_learning_project(auth_client):
    r, p = start(auth_client)
    ex = catalog.get("urlopy")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/p/{p.id}")
    assert (p.name, p.start_sentence, p.learning, p.exercise_key, p.exercise_stage) == (
        ex.title, ex.start_sentence, True, "urlopy", 1)
    assert p.nodes[0].title == ex.start_sentence
    assert auth_client.post("/cwiczenia/nie-ma/start").status_code == 404


def test_task_button_and_panel(auth_client):
    _, p = start(auth_client)
    ex = catalog.get("urlopy")
    assert f"/p/{p.id}/cwiczenie/zadanie" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    html = auth_client.get(f"/p/{p.id}/cwiczenie/zadanie").get_data(as_text=True)
    assert ex.brief in html and "Etap 1 z 2" in html and ex.stage1[0] not in html
    auth_client.post("/projekty/nowy", data={"name": "Zwykły", "start_sentence": "Klient coś robi", "mode": "quick",
                                             "template": "auto"})
    plain = Project.query.order_by(Project.id.desc()).first()
    assert "cwiczenie/zadanie" not in auth_client.get(f"/p/{plain.id}").get_data(as_text=True)
    assert auth_client.get(f"/p/{plain.id}/cwiczenie/zadanie").status_code == 404


def test_stranger_gets_404(auth_client, client):
    _, p = start(auth_client)
    auth_client.post("/logout")
    other = make_user("obcy@example.com")
    client.post("/login", data={"email": other.email, "password": PASSWORD})
    assert client.get(f"/p/{p.id}/cwiczenie/zadanie").status_code == 404


def test_card_shows_best_score(auth_client, user):
    _, p = start(auth_client)
    for score in (40, 72):
        db.session.add(ExerciseAttempt(project_id=p.id, user_id=user.id, stage=1, score=score, feedback={}))
    db.session.commit()
    assert "72/100" in auth_client.get("/cwiczenia").get_data(as_text=True)
