import io
import json

from app.models import Project, QuestionLog, UserTemplate
from tests.conftest import PASSWORD, make_user
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def build_leave_map(client):
    """Generic (no template) map: start -> custom screen -> custom decision -> ..."""
    p = new_project(client, sentence="Pracownik składa wniosek urlopowy")
    client.get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id).one()
    client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "other": "1", "text": "Formularz wniosku urlopowego",
                                           "type": "screen", "actor": "Pracownik"})
    answer_first_tile(client, p)
    return Project.query.get(p.id)


def save(client, p, name="Urlopy", keywords="urlop, delegacja"):
    return client.post(f"/p/{p.id}/zapisz-szablon", data={"name": name, "keywords": keywords}, follow_redirects=True)


def test_save_and_reuse_template(auth_client):
    p = build_leave_map(auth_client)
    html = save(auth_client, p).get_data(as_text=True)
    assert "Zapisano szablon" in html and "Urlopy" in html and "urlop" in html
    tpl = UserTemplate.query.one()
    assert tpl.keywords == ["urlop", "delegacja"]
    assert all(n["x"] is None and set(n["data"]) <= {"branches"} for n in tpl.graph["nodes"])

    # auto-match by keyword: the first tile comes from the saved map, not the generic rules
    q = new_project(auth_client, sentence="Kierownik zatwierdza delegację")
    assert q.template is None  # "delegację" != "delegacja" -> no match
    q = new_project(auth_client, sentence="Nowy wniosek o urlop")
    assert q.template == f"user:{tpl.id}"
    auth_client.get(f"/p/{q.id}/panel")
    log = QuestionLog.query.filter_by(project_id=q.id).one()
    assert log.options["options"][0]["steps"][0]["title"] == "Formularz wniosku urlopowego"


def test_template_offered_in_new_project_form(auth_client):
    p = build_leave_map(auth_client)
    save(auth_client, p)
    tpl = UserTemplate.query.one()
    assert "Mój: Urlopy" in auth_client.get("/projekty/nowy").get_data(as_text=True)
    q = new_project(auth_client, sentence="Cokolwiek innego", template=f"user:{tpl.id}")
    assert q.template == f"user:{tpl.id}"


def test_save_validation(auth_client):
    p = new_project(auth_client)
    html = save(auth_client, p).get_data(as_text=True)
    assert "co najmniej 3 krokami" in html
    html = save(auth_client, build_leave_map(auth_client), name=" ").get_data(as_text=True)
    assert "Podaj nazwę" in html
    assert UserTemplate.query.count() == 0


def test_templates_are_private(auth_client, app):
    p = build_leave_map(auth_client)
    save(auth_client, p)
    tpl = UserTemplate.query.one()
    other = make_user("obcy@example.com")
    c = app.test_client()
    c.post("/login", data={"email": other.email, "password": PASSWORD})
    assert "Urlopy" not in c.get("/szablony").get_data(as_text=True)
    assert "Mój: Urlopy" not in c.get("/projekty/nowy").get_data(as_text=True)
    assert c.post(f"/szablony/{tpl.id}/usun").status_code == 404
    # someone else's template cannot be borrowed through the form or a crafted import
    r = c.post("/projekty/nowy", data={"name": "X", "start_sentence": "Nowy urlop", "mode": "quick",
                                       "template": f"user:{tpl.id}"})
    assert r.status_code == 200  # form rejects a choice that is not offered
    crafted = {"format": "flowmap/1", "project": {"name": "X", "start_sentence": "urlop", "template": f"user:{tpl.id}"},
               "nodes": [{"key": "s", "type": "start", "title": "S"}], "edges": []}
    c.post("/projekty/import", data={"file": (io.BytesIO(json.dumps(crafted).encode()), "x.json")},
           content_type="multipart/form-data")
    assert Project.query.filter_by(owner_id=other.id).one().template is None
    # auto-match never uses another user's template
    c.post("/projekty/nowy", data={"name": "Y", "start_sentence": "Nowy urlop", "mode": "quick", "template": "auto"})
    assert Project.query.filter_by(owner_id=other.id, name="Y").one().template is None


def test_delete_template_keeps_projects(auth_client):
    p = build_leave_map(auth_client)
    save(auth_client, p)
    tpl = UserTemplate.query.one()
    q = new_project(auth_client, sentence="Wniosek o urlop")
    auth_client.post(f"/szablony/{tpl.id}/usun")
    assert UserTemplate.query.count() == 0
    html = auth_client.get(f"/p/{q.id}/panel").get_data(as_text=True)  # falls back to generic rules
    assert "Co dzieje się dalej" in html
