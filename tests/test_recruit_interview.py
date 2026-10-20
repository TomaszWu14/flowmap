from app.exercises import catalog
from app.exercises.interview import QUESTIONS
from app.models import ExerciseAttempt, Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_exercise_grading import graded
from tests.test_recruit import enable_ai, start_recruit
from tests.test_spec_review import fake

QS = {"questions": [{"question": f"Pytanie {i}: dlaczego tak?", "focus": "decyzje"} for i in range(QUESTIONS)]}


def report_payload(scores=(5, 4, 3, 2, 1), recommendation="invite"):
    return {"answers": [{"index": i, "score": s, "comment": f"komentarz {i}"} for i, s in enumerate(scores)],
            "strengths": ["Jasne decyzje", "Dobre role"], "risks": ["Słabe wyjątki", "Brak terminów"],
            "recommendation": recommendation, "reason": "Myśli procesowo."}


def finished(client, app):
    enable_ai(app)
    _, p = start_recruit(client)
    client.post(f"/p/{p.id}/rekrutacja/oddaj")
    return p


def session(p):
    return Project.query.get(p.id).recruit


def answer(client, p, text="Bo kierownik musi znać saldo przed decyzją."):
    return client.post(f"/p/{p.id}/rekrutacja/odpowiedz", data={"text": text})


def test_full_interview(auth_client, app, monkeypatch):
    p = finished(auth_client, app)
    assert "Rozpocznij rozmowę" in auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    calls = fake(monkeypatch, app, graded(score=60), QS, report_payload())
    r = auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa")
    assert r.status_code == 302
    s = session(p)
    assert s.grade["score"] == 60 and len(s.questions) == QUESTIONS and s.answers == []
    [attempt] = ExerciseAttempt.query.filter_by(project_id=p.id).all()
    assert (attempt.stage, attempt.score, attempt.feedback["mode"]) == (1, 60, "recruit")
    q_prompt = calls[1]["messages"][0]["content"]
    assert catalog.get("urlopy").brief in q_prompt and "uwaga 0" in q_prompt  # targets grading gaps
    html = auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Pytanie 0:" in html and "Pytanie 1:" not in html and "1 z 5" in html
    for i in range(QUESTIONS):
        answer(auth_client, p, f"Odpowiedź {i}")
    s = session(p)
    assert s.answers == [f"Odpowiedź {i}" for i in range(QUESTIONS)]
    report_prompt = calls[2]["messages"][0]["content"]
    assert "Pytanie 4" in report_prompt and "Odpowiedź 4" in report_prompt
    rep = s.report
    assert rep["interview_score"] == 60 and rep["final_score"] == 60  # 0.6*60 + 0.4*60
    assert rep["answers"][0]["score"] == 5 and rep["recommendation"] == "invite"
    html = auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Zaprosił(a)bym" in html and "Słabe wyjątki" in html and "komentarz 4" in html and "60/100" in html
    assert answer(auth_client, p).status_code == 400  # interview over


def test_answer_validation_and_order(auth_client, app, monkeypatch):
    p = finished(auth_client, app)
    assert answer(auth_client, p).status_code == 400  # no questions yet
    fake(monkeypatch, app, graded(), QS)
    auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa")
    assert auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa").status_code == 400  # already started
    answer(auth_client, p, "   ")
    answer(auth_client, p, "x" * 1501)
    assert session(p).answers == []
    html = auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Pytanie 0" in html


def test_interview_only_after_the_map_is_handed_in(auth_client, app, monkeypatch):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    fake(monkeypatch, app, graded(), QS)
    assert auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa").status_code == 400
    assert session(p).questions is None


def test_ai_failure_keeps_progress(auth_client, app, monkeypatch):
    p = finished(auth_client, app)
    bad_questions = {"questions": QS["questions"][:3]}
    fake(monkeypatch, app, graded(score=50), bad_questions, bad_questions)
    auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa")
    s = session(p)
    assert s.grade["score"] == 50 and s.questions is None  # grading kept, questions to retry
    calls = fake(monkeypatch, app, QS)
    auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa")
    assert len(calls) == 1 and len(session(p).questions) == QUESTIONS  # map not graded twice
    assert ExerciseAttempt.query.filter_by(project_id=p.id).count() == 1
    fake(monkeypatch, app, report_payload(scores=(1, 1, 1)), report_payload(scores=(1, 1, 1)))
    for _ in range(QUESTIONS):
        answer(auth_client, p)
    assert session(p).report is None and len(session(p).answers) == QUESTIONS
    assert "Wygeneruj raport" in auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    fake(monkeypatch, app, report_payload(recommendation="not_yet"))
    auth_client.post(f"/p/{p.id}/rekrutacja/raport")
    assert session(p).report["recommendation"] == "not_yet"


def test_without_key_interview_button_disabled(auth_client, app):
    p = finished(auth_client, app)
    app.config["ANTHROPIC_API_KEY"] = ""
    html = auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Rozpocznij rozmowę" in html and "disabled" in html
    auth_client.post(f"/p/{p.id}/rekrutacja/rozmowa")
    assert session(p).grade is None


def test_viewer_sees_but_cannot_answer(team, app, monkeypatch):  # noqa: F811
    from datetime import timedelta

    from app.extensions import db
    from app.models import RecruitSession, utcnow

    p = team["project"]
    p.exercise_key = "urlopy"
    now = utcnow()
    db.session.add(RecruitSession(project_id=p.id, minutes=30, started_at=now - timedelta(hours=1),
                                  deadline=now - timedelta(minutes=30)))
    db.session.commit()
    enable_ai(app)
    fake(monkeypatch, app, graded(), QS)
    html = team["viewer"].get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Czas minął" in html and "Rozpocznij rozmowę" not in html
    assert team["viewer"].post(f"/p/{p.id}/rekrutacja/rozmowa").status_code == 403
    assert team["outsider"].post(f"/p/{p.id}/rekrutacja/rozmowa").status_code == 404
    assert session(p).grade is None
