from datetime import timedelta

from app.extensions import db
from app.models import Project, RecruitSession, utcnow
from tests.conftest import PASSWORD, make_user
from tests.test_collaborators import team  # noqa: F401


def enable_ai(app):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"


def start_recruit(client, key="urlopy", minutes=45):
    r = client.post(f"/cwiczenia/{key}/rekrutacja", data={"minutes": minutes})
    project = Project.query.order_by(Project.id.desc()).first()
    return r, project


def expire(project):
    project.recruit.deadline = utcnow() - timedelta(seconds=1)
    db.session.commit()


def test_start_creates_timed_session(auth_client, app):
    enable_ai(app)
    r, p = start_recruit(auth_client, minutes=30)
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/p/{p.id}")
    s = p.recruit
    assert p.exercise_key == "urlopy" and p.learning and s.minutes == 30 and s.finished_at is None
    assert timedelta(minutes=29) < s.deadline - s.started_at <= timedelta(minutes=30)
    html = auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    assert "data-deadline=" in html and "/trener" not in html and "Tryb: Nauka" not in html
    task = auth_client.get(f"/p/{p.id}/cwiczenie/zadanie").get_data(as_text=True)
    assert "Oddaję" in task and "Oddaj etap 1" not in task


def test_start_rejects_bad_minutes_and_unknown_key(auth_client, app):
    enable_ai(app)
    assert auth_client.post("/cwiczenia/urlopy/rekrutacja", data={"minutes": 5}).status_code == 400
    assert auth_client.post("/cwiczenia/nie-ma/rekrutacja", data={"minutes": 30}).status_code == 404
    assert RecruitSession.query.count() == 0


def test_without_ai_recruit_is_unavailable(auth_client):
    html = auth_client.get("/cwiczenia").get_data(as_text=True)
    assert "Tryb rekrutacyjny" in html and "wymaga AI" in html
    r = auth_client.post("/cwiczenia/urlopy/rekrutacja", data={"minutes": 30})
    assert r.status_code == 302 and RecruitSession.query.count() == 0


def test_map_locked_after_deadline(auth_client, app):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    assert auth_client.post(f"/p/{p.id}/layout").status_code != 403  # still editable
    expire(p)
    r = auth_client.post(f"/p/{p.id}/layout")
    assert r.status_code == 403 and "Czas minął" in r.get_data(as_text=True)
    html = auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    assert 'data-readonly="1"' in html and "data-deadline" not in html
    assert auth_client.get(f"/p/{p.id}/graph.json").status_code == 200


def test_finish_early_locks_and_shows_status(auth_client, app):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    page = auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    assert "Oddaję" in page and "45 min" in page
    r = auth_client.post(f"/p/{p.id}/rekrutacja/oddaj")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/p/{p.id}/rekrutacja")
    assert Project.query.get(p.id).recruit.finished_at is not None
    assert auth_client.post(f"/p/{p.id}/layout").status_code == 403
    assert "Mapa oddana" in auth_client.get(f"/p/{p.id}/rekrutacja").get_data(as_text=True)
    first = Project.query.get(p.id).recruit.finished_at
    auth_client.post(f"/p/{p.id}/rekrutacja/oddaj")
    assert Project.query.get(p.id).recruit.finished_at == first  # idempotent


def test_hints_trainer_and_mode_disabled(auth_client, app):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    assert auth_client.post(f"/p/{p.id}/tryb").status_code == 403
    assert auth_client.post(f"/p/{p.id}/podpowiedz", data={"log_id": 1}).status_code == 403
    assert "Podpowiedź" not in auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    chat = auth_client.get(f"/p/{p.id}/trener").get_data(as_text=True)
    assert "wyłączony w trybie rekrutacyjnym" in chat and "<textarea" not in chat
    auth_client.post(f"/p/{p.id}/trener", data={"text": "Podpowiedz mi"})
    assert "Podpowiedz mi" not in auth_client.get(f"/p/{p.id}/trener").get_data(as_text=True)


def test_ordinary_exercise_unchanged_and_stranger_404(auth_client, client, app):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    auth_client.post("/logout")
    other = make_user("obcy@example.com")
    client.post("/login", data={"email": other.email, "password": PASSWORD})
    assert client.get(f"/p/{p.id}/rekrutacja").status_code == 404
    assert client.post(f"/p/{p.id}/rekrutacja/oddaj").status_code == 404


def test_no_graded_feedback_or_ai_help_during_the_case(auth_client, app):
    """Code review 2026-10-20: the results page, guard AI and "Oceń z AI" leaked expert feedback mid-case."""
    enable_ai(app)
    _, p = start_recruit(auth_client)
    assert "Oddaj etap" not in auth_client.get(f"/p/{p.id}/cwiczenie").get_data(as_text=True)
    assert auth_client.post(f"/p/{p.id}/cwiczenie/oddaj", data={"stage": 1}).status_code == 403
    for route in ("guard/review", "guard/fill", "guard/fill/apply", "guard/apply"):
        assert auth_client.post(f"/p/{p.id}/{route}").status_code == 403, route
    guard = auth_client.get(f"/p/{p.id}/guard").get_data(as_text=True)
    assert "Uruchom przegląd AI" not in guard and "przegląd AI jest wyłączony" in guard
    assert auth_client.post(f"/p/{p.id}/ocena/ai").status_code == 403
    assert "Oceń z AI" not in auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
    auth_client.post(f"/p/{p.id}/rekrutacja/oddaj")
    assert auth_client.post(f"/p/{p.id}/ocena/ai").status_code == 302  # fine once handed in


def test_only_the_candidate_edits_and_answers(team, app):  # noqa: F811
    from app.models import RecruitSession

    enable_ai(app)
    p = team["project"]
    p.exercise_key = "urlopy"
    now = utcnow()
    db.session.add(RecruitSession(project_id=p.id, user_id=p.owner_id, minutes=30, started_at=now,
                                  deadline=now + timedelta(minutes=30)))
    db.session.commit()
    r = team["editor"].post(f"/p/{p.id}/layout")
    assert r.status_code == 403 and "tylko kandydat" in r.get_data(as_text=True)
    assert 'data-readonly="1"' in team["editor"].get(f"/p/{p.id}").get_data(as_text=True)
    assert team["editor"].post(f"/p/{p.id}/rekrutacja/oddaj").status_code == 403
    assert team["owner"].post(f"/p/{p.id}/layout").status_code != 403
    team["owner"].post(f"/p/{p.id}/rekrutacja/oddaj")
    assert team["editor"].post(f"/p/{p.id}/rekrutacja/rozmowa").status_code == 403


def test_progress_never_continues_into_a_locked_recruitment_project(auth_client, app):
    enable_ai(app)
    _, p = start_recruit(auth_client)
    auth_client.post(f"/p/{p.id}/rekrutacja/oddaj")
    html = auth_client.get("/postep").get_data(as_text=True)
    assert f'href="/p/{p.id}"' not in html
