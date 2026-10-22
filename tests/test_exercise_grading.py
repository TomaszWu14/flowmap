from app.exercises import catalog
from app.extensions import db
from app.models import AiCache, ExerciseAttempt, Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_exercises import start
from tests.test_spec_review import fake


def graded(stage=1, score=70, drop=0):
    n = len(catalog.get("urlopy").expectations(stage)) - drop
    return {"expectations": [{"index": i, "verdict": "met" if i % 2 else "partial", "comment": f"uwaga {i}"}
                             for i in range(n)],
            "score": score, "strengths": ["Jasne role", "Dobry start"], "fixes": ["Popraw A", "Popraw B", "Popraw C"]}


def submit(client, p, stage=1):
    return client.post(f"/p/{p.id}/cwiczenie/oddaj", data={"stage": stage})


def attempts(p):
    return ExerciseAttempt.query.filter_by(project_id=p.id).order_by(ExerciseAttempt.id).all()


def test_submit_stage1(auth_client, app, monkeypatch):
    _, p = start(auth_client)
    ex = catalog.get("urlopy")
    results = auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)
    assert ex.brief in results and ex.stage1[0].text not in results  # hidden before the first submission
    calls = fake(monkeypatch, app, graded())
    r = submit(auth_client, p)
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/p/{p.id}/cwiczenie")
    prompt = calls[0]["messages"][0]["content"]
    assert ex.brief in prompt and ex.stage1[-1].text in prompt and ex.start_sentence in prompt
    assert calls[0]["model"] == app.config["ANTHROPIC_MODEL"]
    [a] = attempts(p)
    assert (a.stage, a.score, a.feedback["mode"]) == (1, 70, "learning")
    assert a.feedback["expectations"][0] == {"text": ex.stage1[0].text, "topic": "przebieg", "verdict": "partial",
                                         "comment": "uwaga 0"}
    assert Project.query.get(p.id).exercise_stage == 2
    html = auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)
    assert ex.stage1[0].text in html and "Popraw C" in html and "70/100" in html and ex.stage2[0].text not in html
    assert "Etap 2 z 2" in auth_client.get(f"/p/{p.id}/cwiczenie/zadanie").get_data(as_text=True)


def test_stage2_locked_then_graded_with_spec(auth_client, app, monkeypatch):
    _, p = start(auth_client)
    assert submit(auth_client, p, stage=2).status_code == 400
    assert submit(auth_client, p, stage=3).status_code == 400
    fake(monkeypatch, app, graded(score=40))
    submit(auth_client, p)
    calls = fake(monkeypatch, app, graded(stage=2, score=55), graded(score=80))
    submit(auth_client, p, stage=2)
    prompt = calls[0]["messages"][0]["content"]
    assert catalog.get("urlopy").stage2[0].text in prompt and "classDiagram" in prompt
    AiCache.query.delete()  # same map as the first submission: otherwise the cached grade comes back
    submit(auth_client, p, stage=1)  # resubmitting stage 1 keeps stage 2 open
    assert [(a.stage, a.score) for a in attempts(p)] == [(1, 40), (2, 55), (1, 80)]
    assert Project.query.get(p.id).exercise_stage == 2
    html = auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)
    assert "80/100" in html and "55/100" in html
    assert "80/100" in auth_client.get("/cwiczenia").get_data(as_text=True)


def test_invalid_ai_answer_saves_nothing(auth_client, app, monkeypatch):
    _, p = start(auth_client)
    fake(monkeypatch, app, graded(drop=1), graded(score=101))
    r = submit(auth_client, p)
    assert r.status_code == 302 and attempts(p) == []
    assert Project.query.get(p.id).exercise_stage == 1
    assert "Ocena nieudana" in auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)


def test_without_key_button_disabled_and_nothing_saved(auth_client):
    _, p = start(auth_client)
    html = auth_client.get(f"/p/{p.id}/cwiczenie/zadanie").get_data(as_text=True)
    assert "Oddaj etap 1" in html and "disabled" in html and "ANTHROPIC_API_KEY" in html
    submit(auth_client, p)
    assert attempts(p) == []


def test_work_mode_is_noted(auth_client, app, monkeypatch):
    _, p = start(auth_client)
    auth_client.post(f"/p/{p.id}/tryb")  # switch to Praca
    fake(monkeypatch, app, graded())
    submit(auth_client, p)
    assert attempts(p)[0].feedback["mode"] == "work"
    assert "w trybie Praca" in auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)


def test_permissions(team, app, monkeypatch):  # noqa: F811
    p = team["project"]
    p.exercise_key = "urlopy"
    db.session.commit()
    fake(monkeypatch, app, graded())
    assert submit(team["viewer"], p).status_code == 403
    assert team["viewer"].get(f"/p/{p.id}/cwiczenie").status_code == 200
    assert team["outsider"].get(f"/p/{p.id}/cwiczenie").status_code == 404
    assert submit(team["outsider"], p).status_code == 404
    assert attempts(p) == []
    assert submit(team["editor"], p).status_code == 302 and len(attempts(p)) == 1
