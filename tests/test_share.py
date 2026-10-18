from app.models import Project
from tests.conftest import PASSWORD, make_user
from tests.test_flow import play_to_end
from tests.test_projects import new_project


def enable_link(client, project):
    client.post(f"/p/{project.id}/udostepnianie/link")
    return Project.query.get(project.id).share_token


def test_share_link_lifecycle(auth_client, client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    assert p.share_token is None
    token = enable_link(auth_client, p)
    assert token and len(token) >= 20
    html = auth_client.get(f"/p/{p.id}/udostepnianie").get_data(as_text=True)
    assert f"/s/{token}" in html

    anon = client.application.test_client()
    html = anon.get(f"/s/{token}").get_data(as_text=True)
    assert "tylko do odczytu" in html and "## 1. Opis procesu" in html and 'name="robots" content="noindex"' in html
    assert anon.get(f"/s/{token}/graph.json").json["score"] >= 0
    html = anon.get(f"/s/{token}/symulacja?role=Klient").get_data(as_text=True)
    assert f"/s/{token}/symulacja" in html and f"/p/{p.id}" not in html  # no owner-only links leak

    auth_client.post(f"/p/{p.id}/udostepnianie/nowy-link")
    new_token = Project.query.get(p.id).share_token
    assert new_token != token
    assert anon.get(f"/s/{token}").status_code == 404
    auth_client.post(f"/p/{p.id}/udostepnianie/link")  # turn off
    assert Project.query.get(p.id).share_token is None
    assert anon.get(f"/s/{new_token}").status_code == 404


def test_share_link_is_read_only(auth_client, client):
    p = new_project(auth_client)
    enable_link(auth_client, p)
    anon = client.application.test_client()
    assert anon.get(f"/p/{p.id}").status_code == 302
    assert anon.post(f"/p/{p.id}/answer").status_code == 302


def test_only_owner_manages_sharing(auth_client, db):
    p = new_project(auth_client)
    other = make_user("obcy@example.com")
    c = auth_client.application.test_client()
    c.post("/login", data={"email": other.email, "password": PASSWORD})
    assert c.get(f"/p/{p.id}/udostepnianie").status_code == 404
    assert c.post(f"/p/{p.id}/udostepnianie/link").status_code == 404
    assert Project.query.get(p.id).share_token is None


def test_unknown_token(client, db):
    assert client.get("/s/nie-ma-takiego").status_code == 404
