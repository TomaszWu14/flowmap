import re

import pytest

from app.auth.tokens import make_reset_token, user_from_token
from app.models import AuditEvent
from tests.conftest import PASSWORD, make_user


@pytest.fixture
def outbox(app, monkeypatch):
    app.config["MAIL_SERVER"] = "smtp.test"
    sent = []
    monkeypatch.setattr("app.auth.routes.send_mail", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def test_forgot_without_mail_points_to_admin(client, db):
    html = client.get("/nie-pamietam-hasla").get_data(as_text=True)
    assert "Poproś administratora" in html


def test_full_reset_flow(client, user, outbox):
    r = client.post("/nie-pamietam-hasla", data={"email": "ALA@example.com"}, follow_redirects=True)
    assert "Jeśli konto istnieje" in r.get_data(as_text=True)
    assert len(outbox) == 1 and outbox[0][0] == user.email
    link = re.search(r"http\S+/reset-hasla/\S+", outbox[0][2]).group(0)
    path = link.split("localhost", 1)[1]
    assert "Ustaw nowe hasło" in client.get(path).get_data(as_text=True)
    client.post(path, data={"password": "nowe-haslo-12345", "password2": "nowe-haslo-12345"})
    assert user.check_password("nowe-haslo-12345")
    # the link is single-use: the password hash changed
    r = client.get(path, follow_redirects=True)
    assert "wygasł albo został już użyty" in r.get_data(as_text=True)
    assert {"password_reset_requested", "password_reset"} <= {e.action for e in AuditEvent.query}


def test_unknown_email_gets_same_answer_and_no_mail(client, db, outbox):
    r = client.post("/nie-pamietam-hasla", data={"email": "nikt@example.com"}, follow_redirects=True)
    assert "Jeśli konto istnieje" in r.get_data(as_text=True)
    assert outbox == []


def test_blocked_user_gets_no_mail(client, user, db, outbox):
    user.is_blocked = True
    db.session.commit()
    client.post("/nie-pamietam-hasla", data={"email": user.email})
    assert outbox == []


def test_token_validity(app, user, db):
    with app.test_request_context():
        token = make_reset_token(user, 1)
        assert user_from_token(token) == user
        assert user_from_token(token + "x") is None
        user.set_password("inne-haslo-123456")
        db.session.commit()
        assert user_from_token(token) is None


def test_token_expiry(app, user, monkeypatch):
    from datetime import datetime, timedelta

    import app.auth.tokens as tokens

    with app.test_request_context():
        token = make_reset_token(user, 1)
        assert user_from_token(token) == user

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(hours=2)

        monkeypatch.setattr(tokens, "datetime", Later)
        assert user_from_token(token) is None  # older than its own 1h window


def test_admin_reset_link(client, db):
    admin = make_user("admin@example.com")
    admin.is_admin = True
    other = make_user("ola@example.com")
    db.session.commit()
    client.post("/login", data={"email": admin.email, "password": PASSWORD})
    r = client.post(f"/admin/users/{other.id}/reset-link", follow_redirects=True)
    html = r.get_data(as_text=True)
    path = re.search(r"/reset-hasla/[^\s<\"]+", html).group(0)
    client.post("/logout")
    client.post(path, data={"password": "od-admina-12345", "password2": "od-admina-12345"})
    assert other.check_password("od-admina-12345")
    assert client.post(f"/admin/users/{other.id}/reset-link").status_code in (302, 404)
