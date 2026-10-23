import time
from datetime import timedelta

import pytest

from app.models import DemoVisitor
from app.visitor_gate import activity, notify

DATA = {"first_name": "Jan", "last_name": "Kowalski", "company": "ACME", "consent": "y"}
URL = "https://ntfy.example/tajny-temat"


@pytest.fixture(autouse=True)
def gate_on(app):
    app.config.update(DEMO_VISITOR_GATE=True, NTFY_URL="", NTFY_ENGAGED_VIEWS=10, NTFY_WATCH_COMPANIES="")


@pytest.fixture
def pushes(app, monkeypatch):
    app.config["NTFY_URL"] = URL
    calls = []
    monkeypatch.setattr(notify, "_start", calls.append)
    return calls


def _visitor():
    return DemoVisitor.query.one()


def enter(client):
    assert client.post("/wejscie", data=DATA).status_code == 302


def test_three_pages_counted(client, db):
    enter(client)
    assert _visitor().page_views == 0 and _visitor().last_seen_at is None
    for path in ("/przyklad", "/przyklad", "/"):
        assert client.get(path).status_code in (200, 302)
    db.session.expire_all()
    v = _visitor()
    views = sum(v.sections.values())
    assert v.page_views == views and v.page_views >= 2
    assert v.sections["przyklad"] == 2
    assert v.last_seen_at is not None and v.last_seen_at >= v.created_at


def test_three_html_gets(client, db, app):
    @app.get("/demo-a/<int:n>")
    def demo_a(n):
        return "<p>a</p>"

    enter(client)
    for path in ("/demo-a/1", "/demo-a/2", "/demo-a/3"):
        assert client.get(path).status_code == 200
    db.session.expire_all()
    v = _visitor()
    assert v.page_views == 3 and v.sections == {"demo-a": 3} and v.last_seen_at


def test_not_counted(client, db, app):
    @app.get("/api/public/x")
    def api_x():
        return {"ok": True}

    enter(client)
    client.get("/healthz")
    client.get("/static/nonexistent.css")
    client.get("/api/public/x")
    client.get("/nie-ma-takiej-strony")
    client.get("/przyklad", headers={"HX-Request": "true"})
    client.post("/przyklad")
    db.session.expire_all()
    assert _visitor().page_views == 0


def test_visitor_without_flag_not_counted(client, db, app):
    enter(client)
    other = app.test_client()
    other.get("/przyklad")  # redirected to the gate, no flag
    with other.session_transaction() as s:  # legacy pass from before this change: no record id
        s["visitor_ok"] = int(time.time())
    assert other.get("/przyklad").status_code == 200
    db.session.expire_all()
    assert _visitor().page_views == 0


def test_forged_cookie_not_counted(client, db, app):
    enter(client)
    forger = app.test_client()
    forger.set_cookie("session", '{"visitor_ok": 9999999999, "visitor_id": 1}')
    forger.get("/przyklad")
    db.session.expire_all()
    assert _visitor().page_views == 0


def test_expired_flag_not_counted(client, db):
    enter(client)
    with client.session_transaction() as s:
        s["visitor_ok"] -= 31 * 86400
    client.get("/przyklad")
    db.session.expire_all()
    assert _visitor().page_views == 0


def test_engaged_push_exactly_once(client, db, app, pushes):
    app.config.update(NTFY_ENGAGED_VIEWS=3, NTFY_WATCH_COMPANIES="")
    enter(client)
    assert len(pushes) == 1  # the "new visitor" push
    for _ in range(6):
        client.get("/przyklad")
    engaged = pushes[1:]
    assert len(engaged) == 1
    headers = {k.lower(): v for k, v in engaged[0].header_items()}
    assert headers["tags"] == "eyes" and headers["priority"] == "default"
    assert headers["title"] == "Gosc oglada demo: FlowMap"
    assert engaged[0].data.decode("utf-8") == "Jan Kowalski (ACME) obejrzał już 3 ekranów w FlowMap"


def test_engaged_push_urgent_for_watched_company(client, app, pushes):
    app.config.update(NTFY_ENGAGED_VIEWS=1, NTFY_WATCH_COMPANIES="acme")
    enter(client)
    client.get("/przyklad")
    headers = {k.lower(): v for k, v in pushes[-1].header_items()}
    assert headers["tags"] == "eyes" and headers["priority"] == "urgent"


def test_engaged_push_disabled_with_zero(client, app, pushes):
    app.config["NTFY_ENGAGED_VIEWS"] = 0
    enter(client)
    for _ in range(3):
        client.get("/przyklad")
    assert len(pushes) == 1


def test_counting_error_does_not_break_response(client, db, monkeypatch):
    enter(client)

    def boom(*args):
        raise RuntimeError("db down")

    monkeypatch.setattr(activity, "record_view", boom)
    r = client.get("/przyklad")
    assert r.status_code == 200 and "<html" in r.get_data(as_text=True).lower()


def test_section_limit_20(app, db):
    v = DemoVisitor(first_name="A", last_name="B", company="C", sections={f"s{i}": 1 for i in range(20)})
    db.session.add(v)
    db.session.commit()
    with app.test_request_context():
        activity.record_view(v.id, "/nowa-sekcja/1")
        activity.record_view(v.id, "/s3")
    db.session.expire_all()
    v = db.session.get(DemoVisitor, v.id)
    assert len(v.sections) == 20 and "nowa-sekcja" not in v.sections
    assert v.sections["s3"] == 2 and v.page_views == 2


@pytest.mark.parametrize("path, expected", [
    ("/", "start"), ("/palety/123", "palety"), ("/Projekty", "projekty"), ("/zażółć", "za"),
    ("/" + "a" * 60, "a" * 40), ("/%3Cscript%3E/x", "3cscript3e"),
])
def test_section_of(path, expected):
    assert activity.section_of(path) == expected


def test_list_shows_activity_columns(client, app, db):
    from tests.conftest import make_user

    v = DemoVisitor(first_name="Anna", last_name="Nowak", company="Firma", page_views=7,
                    sections={"przyklad": 4, "projekty": 2, "start": 1, "inne": 1})
    db.session.add(v)
    db.session.add(DemoVisitor(first_name="Bez", last_name="Ruchu", company="Firma"))
    db.session.commit()
    v.last_seen_at = v.created_at + timedelta(minutes=12, seconds=10)
    db.session.commit()
    admin = make_user("admin@example.com")
    admin.is_admin = True
    db.session.commit()
    with client.session_transaction() as s:
        s["_user_id"] = str(admin.id)
        s["_fresh"] = True
    body = client.get("/admin/odwiedzajacy").get_data(as_text=True)
    for header in ("Ekrany", "Czas", "Najczęściej"):
        assert f"<th>{header}</th>" in body
    assert "ok. 12 min" in body and "przyklad, projekty, inne" in body and "<td>7</td>" in body
    assert "—" in body


def test_cookie_signed_with_other_key_not_counted(client, db, app):
    from flask.sessions import SecureCookieSessionInterface

    enter(client)
    other_app = type(app)("other")
    other_app.secret_key = "not-the-real-key"
    forged = SecureCookieSessionInterface().get_signing_serializer(other_app).dumps(
        {"visitor_ok": int(time.time()), "visitor_id": _visitor().id})
    forger = app.test_client()
    forger.set_cookie("session", forged)
    assert forger.get("/przyklad").status_code == 302  # back to the gate
    db.session.expire_all()
    assert _visitor().page_views == 0
