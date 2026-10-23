from datetime import timedelta

import pytest

from app.models import DemoVisitor, Project, utcnow
from tests.conftest import make_user

DATA = {"first_name": "Jan", "last_name": "Kowalski", "company": "ACME", "consent": "y"}


@pytest.fixture(autouse=True)
def gate_on(app):
    app.config["DEMO_VISITOR_GATE"] = True


def test_gate_off_by_default_config(app):
    app.config["DEMO_VISITOR_GATE"] = False
    assert app.test_client().get("/przyklad").status_code == 200


def test_redirects_to_gate_without_data(client):
    r = client.get("/przyklad")
    assert r.status_code == 302 and r.headers["Location"].startswith("/wejscie?next=/przyklad")
    page = client.get("/wejscie?next=/przyklad").get_data(as_text=True)
    assert "Zanim wejdziesz do wersji demonstracyjnej, przedstaw się, proszę." in page
    assert "art. 6 ust. 1 lit. f RODO" in page
    assert client.get("/register").status_code == 302


def test_submit_records_and_grants_access(client, db):
    r = client.post("/wejscie?next=/przyklad", data={**DATA, "next": "/przyklad"})
    assert r.status_code == 302 and r.headers["Location"] == "/przyklad"
    v = DemoVisitor.query.one()
    assert (v.first_name, v.last_name, v.company) == ("Jan", "Kowalski", "ACME")
    assert client.get("/przyklad").status_code == 200
    assert client.get("/register").status_code == 200


@pytest.mark.parametrize("bad", [
    {"first_name": "J"}, {"last_name": "  "}, {"company": "x" * 101}, {"company": "AC\x00ME"},
    {"consent": ""},
])
def test_invalid_input_refused(client, bad):
    r = client.post("/wejscie", data={**DATA, **bad})
    assert r.status_code == 200 and DemoVisitor.query.count() == 0
    assert client.get("/przyklad").status_code == 302


def test_values_are_trimmed(client):
    client.post("/wejscie", data={**DATA, "first_name": "  Jan  "})
    assert DemoVisitor.query.one().first_name == "Jan"


def test_honeypot_refused(client):
    r = client.post("/wejscie", data={**DATA, "website": "http://spam"})
    assert r.status_code == 400 and DemoVisitor.query.count() == 0
    assert client.get("/przyklad").status_code == 302


def test_unsafe_next_ignored(client):
    r = client.post("/wejscie", data={**DATA, "next": "//evil.example"})
    assert r.headers["Location"] == "/"


def test_exempt_paths(client, db):
    assert client.get("/healthz").status_code == 200
    assert client.get("/static/nonexistent.css").status_code == 404  # not redirected to the gate
    assert client.get("/s/nie-ma-takiego-tokenu").status_code == 404
    # HTMX from an anonymous visitor is sent to the gate instead of getting a fragment
    r = client.get("/przyklad", headers={"HX-Request": "true"})
    assert r.status_code == 401 and "/wejscie" in r.headers["HX-Redirect"]


def test_share_link_with_token_not_blocked(client, db, user):
    project = Project(name="P", start_sentence="Start", owner_id=user.id, share_token="tajny-token-123")
    db.session.add(project)
    db.session.commit()
    assert client.get("/s/tajny-token-123").status_code == 200


def test_logged_in_user_skips_gate(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)
        s["_fresh"] = True
    assert client.get("/projekty").status_code == 200
    assert client.get("/projekty", headers={"HX-Request": "true"}).status_code == 200


def test_expired_pass_requires_gate_again(client):
    client.post("/wejscie", data=DATA)
    with client.session_transaction() as s:
        s["visitor_ok"] -= 31 * 86400
    assert client.get("/przyklad").status_code == 302


def test_retention_90_days(client, db):
    db.session.add_all([
        DemoVisitor(first_name="Stary", last_name="Wpis", company="X", created_at=utcnow() - timedelta(days=91)),
        DemoVisitor(first_name="Nowy", last_name="Wpis", company="X", created_at=utcnow() - timedelta(days=89)),
    ])
    db.session.commit()
    client.post("/wejscie", data=DATA)
    assert sorted(v.first_name for v in DemoVisitor.query) == ["Jan", "Nowy"]


def _login(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)
        s["_fresh"] = True


def test_list_only_for_admin(client, app, db):
    db.session.add(DemoVisitor(first_name="Anna", last_name="Nowak", company="Firma", created_at=utcnow()))
    db.session.add(DemoVisitor(first_name="Beata", last_name="Zawsze", company="Firma",
                               created_at=utcnow() + timedelta(seconds=5)))
    db.session.commit()
    assert client.get("/admin/odwiedzajacy").status_code in (302, 401)
    regular = make_user("zwykly@example.com")
    _login(client, regular)
    assert client.get("/admin/odwiedzajacy").status_code == 404
    admin = make_user("admin@example.com")
    admin.is_admin = True
    db.session.commit()
    c2 = app.test_client()
    _login(c2, admin)
    body = c2.get("/admin/odwiedzajacy").get_data(as_text=True)
    assert body.index("Beata") < body.index("Anna")
