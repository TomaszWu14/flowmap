from app.exercises import catalog
from app.exercises.progress import criteria_stats, latest, recommend, strengths_and_weaknesses, topic_stats, trend
from app.extensions import db
from app.models import Evaluation, ExerciseAttempt, Project
from tests.test_exercises import start
from tests.test_projects import new_project


def fb(*pairs):
    return {"expectations": [{"text": f"t{i}", "topic": topic, "verdict": verdict}
                             for i, (topic, verdict) in enumerate(pairs)]}


def test_topic_stats_weights_and_minimum():
    stats = topic_stats([fb(("wyjatki", "met"), ("wyjatki", "partial"), ("role", "missed")),
                         fb(("wyjatki", "missed"))], {})
    assert stats == [{"code": "wyjatki", "label": "Wyjątki i błędy", "value": 50, "count": 3, "source": "ćwiczenia"}]


def test_topic_stats_falls_back_to_text_and_skips_unknown():
    old = {"expectations": [{"text": "A", "verdict": "met"}, {"text": "A", "verdict": "met"},
                            {"text": "?", "verdict": "met"}, {"text": "A", "verdict": "dziwny"}]}
    assert [(s["code"], s["value"], s["count"]) for s in topic_stats([old], {"A": "dane"})] == [("dane", 100, 2)]


def test_criteria_stats_and_ranking():
    details = [{"criteria": [{"code": "errors", "label": "Ścieżki błędu", "points": 5, "max": 20},
                             {"code": "roles", "label": "Role", "points": 15, "max": 15}]},
               {"criteria": [{"code": "errors", "label": "Ścieżki błędu", "points": 15, "max": 20}]}]
    stats = criteria_stats(details)
    assert {(s["code"], s["value"], s["count"]) for s in stats} == {("errors", 50, 2), ("roles", 100, 1)}
    strong, weak = strengths_and_weaknesses(stats)
    assert [s["code"] for s in strong] == ["roles"] and [s["code"] for s in weak] == ["errors"]


def test_latest_keeps_newest_per_key():
    rows = [("a", 1), ("b", 2), ("a", 3)]
    assert latest(rows, lambda r: r[0]) == [("a", 3), ("b", 2)]


def test_trend():
    assert trend([50]) is None
    assert trend([40, 55, 70])["delta"] == 30
    t = trend([10] * 5 + [60] * 5)
    assert (t["before"], t["recent"], t["delta"], t["window"]) == (10, 60, 50, 5)


def test_recommend_rules(app):
    exercises = catalog.all_exercises()
    basics = [e for e in exercises if e.level == "podstawowy"]
    pick, why = recommend(exercises, {}, [])
    assert pick.level == "podstawowy" and "podstawowego" in why
    pick, why = recommend(exercises, {e.key: 80 for e in basics}, ["integracje"])
    assert pick.level == "zaawansowany" and any(e.topic == "integracje" for e in pick.stage2)
    pick, why = recommend(exercises, {"urlopy": 60}, ["wyjatki"])
    assert pick.key != "urlopy" and "Wyjątki i błędy" in why
    assert any(e.topic == "wyjatki" for e in pick.stage1 + pick.stage2)
    pick, _ = recommend(exercises, {e.key: 90 for e in exercises} | {"o2c": 40}, [])
    assert pick.key == "o2c"


def test_progress_page_empty(auth_client):
    html = auth_client.get("/postep").get_data(as_text=True)
    assert "Postęp" in html and "Zacznij od ćwiczenia podstawowego" in html and "Rozpocznij" in html
    assert 'href="/postep"' in auth_client.get("/cwiczenia").get_data(as_text=True)
    assert 'href="/postep"' in auth_client.get("/projekty").get_data(as_text=True)


def _attempt(p, user, stage, score, *pairs):
    db.session.add(ExerciseAttempt(project_id=p.id, user_id=user.id, stage=stage, score=score, feedback=fb(*pairs)))
    db.session.commit()


def test_progress_page_with_results(auth_client, user):
    _, p = start(auth_client)
    _attempt(p, user, 1, 40, ("wyjatki", "missed"), ("wyjatki", "missed"), ("role", "met"), ("role", "met"))
    _attempt(p, user, 1, 75, ("wyjatki", "missed"), ("wyjatki", "partial"), ("role", "met"), ("role", "met"))
    plain = new_project(auth_client)
    db.session.add(Evaluation(project_id=plain.id, user_id=user.id, kind="map", score=50, source="rules",
                              details={"criteria": [{"code": "errors", "label": "Ścieżki błędu", "points": 4,
                                                     "max": 20}]}))
    db.session.commit()
    html = auth_client.get("/postep").get_data(as_text=True)
    assert "Wniosek urlopowy" in html and "40 → 75" in html and "+35" in html
    strong, weak = html.split("Mocne strony")[1].split("Do poprawy")
    assert "Role w procesie" in strong
    assert "Wyjątki i błędy" in weak and "25%" in weak and "Ścieżki błędu" in weak
    assert "Kontynuuj" in html or "Rozpocznij" in html
    assert f"/p/{p.id}/cwiczenie" in html


def test_progress_shows_only_own_data(auth_client, user, client):
    _, p = start(auth_client)
    _attempt(p, user, 1, 88, ("role", "met"), ("role", "met"))
    auth_client.post("/logout")
    from tests.conftest import PASSWORD, make_user
    other = make_user("inny@example.com")
    client.post("/login", data={"email": other.email, "password": PASSWORD})
    html = client.get("/postep").get_data(as_text=True)
    assert "88" not in html and "Zacznij od ćwiczenia podstawowego" in html
    assert Project.query.count() == 1


def test_program_path_statuses():
    from app.exercises import catalog
    from app.exercises.progress import PASS, PROGRAM, program

    exercises = {e.key: e for e in catalog.all_exercises()}
    assert set(PROGRAM) == set(exercises)  # every exercise is on the path
    steps = program(exercises, {"urlopy": 80, "onboarding": PASS - 1, "logistyka": 90})
    assert [s["status"] for s in steps] == ["done", "next", "later", "done", "later", "later", "later"]
    assert [s["status"] for s in program(exercises, {})][:2] == ["next", "later"]


def test_program_on_exercise_catalogue(auth_client):
    html = auth_client.get("/cwiczenia").get_data(as_text=True)
    assert "Program: 0 z 7 zaliczone" in html and 'aria-current="step"' in html and "Wniosek urlopowy" in html
