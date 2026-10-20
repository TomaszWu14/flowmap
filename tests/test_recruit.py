from datetime import timedelta

from app.extensions import db
from app.models import Project, RecruitSession, utcnow
from tests.conftest import PASSWORD, make_user


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
