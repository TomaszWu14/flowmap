from app.extensions import db
from app.models import Project, QuestionLog
from tests.test_collaborators import team  # noqa: F401
from tests.test_projects import new_project


def learning_project(client):
    p = new_project(client)
    client.post(f"/p/{p.id}/tryb")
    assert Project.query.get(p.id).learning
    return p


def open_log(p):
    return QuestionLog.query.filter_by(project_id=p.id, answer="").order_by(QuestionLog.id.desc()).first()


def level(log_id):
    return db.session.get(QuestionLog, log_id).hint_level


def test_toggle_mode(auth_client):
    p = new_project(auth_client)
    assert not Project.query.get(p.id).learning
    r = auth_client.post(f"/p/{p.id}/tryb")
    assert r.status_code == 302 and Project.query.get(p.id).learning
    assert "Tryb: Nauka" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    auth_client.post(f"/p/{p.id}/tryb")
    assert not Project.query.get(p.id).learning


def test_learning_hides_tiles_and_reveals_hints_step_by_step(auth_client):
    p = learning_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert 'name="option"' not in html and "Podpowiedź" in html and "Twój krok" in html
    log = open_log(p)
    html = auth_client.post(f"/p/{p.id}/podpowiedz", data={"log_id": log.id}).get_data(as_text=True)
    assert "hint-guide" in html and 'name="option"' not in html
    html = auth_client.post(f"/p/{p.id}/podpowiedz", data={"log_id": log.id}).get_data(as_text=True)
    assert html.count('name="option"') == 1
    html = auth_client.post(f"/p/{p.id}/podpowiedz", data={"log_id": log.id}).get_data(as_text=True)
    assert html.count('name="option"') == len(log.options["options"]) and level(log.id) == 3
    assert "Podpowiedź (" not in html  # all hints used
    auth_client.post(f"/p/{p.id}/podpowiedz", data={"log_id": log.id})
    assert level(log.id) == 3  # capped


def test_hidden_tile_cannot_be_chosen(auth_client):
    p = learning_project(auth_client)
    auth_client.get(f"/p/{p.id}/panel")
    log = open_log(p)
    assert auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "option": 0}).status_code == 400
    r = auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "other": "1", "text": "Pracownik sprawdza termin",
                                                     "type": "user_action", "actor": "Pracownik"})
    assert r.status_code == 200 and db.session.get(QuestionLog, log.id).answer


def test_work_mode_unchanged(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert 'name="option"' in html and "Podpowiedź" not in html


def test_viewer_cannot_toggle_or_hint(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].post(f"/p/{p.id}/tryb").status_code in (403, 404)
    assert team["viewer"].post(f"/p/{p.id}/podpowiedz", data={"log_id": 1}).status_code in (403, 404)
