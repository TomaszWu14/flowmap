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


def test_client_accepts_or_asks_for_changes_without_account(auth_client, client, app, monkeypatch):
    from app.models import AuditEvent, ClientReview

    p = new_project(auth_client)
    token = enable_link(auth_client, p)
    anon = client.application.test_client()
    assert "Twoja decyzja" in anon.get(f"/s/{token}").get_data(as_text=True)
    r = anon.post(f"/s/{token}/opinia", data={"name": "Jan z ACME", "decision": "changes"}, follow_redirects=True)
    assert "Napisz, co zmienić" in r.get_data(as_text=True) and ClientReview.query.count() == 0
    mails = []
    app.config["MAIL_SERVER"] = "smtp.example.com"
    monkeypatch.setattr("app.mail.send_mail", lambda to, subject, body: mails.append((to, subject)))
    r = anon.post(f"/s/{token}/opinia", data={"name": "Jan z ACME", "decision": "accept"}, follow_redirects=True)
    assert "decyzja zapisana" in r.get_data(as_text=True) and "Jan z ACME" in r.get_data(as_text=True)
    review = ClientReview.query.one()
    assert review.version_id == Project.query.get(p.id).version_cursor_id and review.version_label
    assert mails and mails[0][0] == p.owner.email and "akceptuje" in mails[0][1]
    assert AuditEvent.query.filter_by(action="client_review").count() == 1
    html = auth_client.get(f"/p/{p.id}/wersje").get_data(as_text=True)
    assert "✓ Jan z ACME: akceptuje" in html
    assert anon.post("/s/zly-token/opinia", data={"name": "X", "decision": "accept"}).status_code == 404


def test_client_reviews_are_rate_limited(auth_client, client, monkeypatch):
    from app.models import ClientReview
    from app.share import routes as share

    monkeypatch.setattr(share, "REVIEWS_PER_DAY", 2)
    p = new_project(auth_client)
    token = enable_link(auth_client, p)
    anon = client.application.test_client()
    for _ in range(3):
        r = anon.post(f"/s/{token}/opinia", data={"name": "Bot", "decision": "accept"}, follow_redirects=True)
    assert "spróbuj jutro" in r.get_data(as_text=True) and ClientReview.query.count() == 2
