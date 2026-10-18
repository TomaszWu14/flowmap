from app.config import TestConfig
from app.models import User


def test_healthz(client):
    assert client.get("/healthz").json == {"status": "ok"}


def test_register_login_logout(client, db):
    r = client.post("/register", data={"email": "Nowy@Example.com", "password": "x" * 12, "password2": "x" * 12})
    assert r.status_code == 302
    user = User.query.filter_by(email="nowy@example.com").one()
    assert user.password_hash != "x" * 12 and user.check_password("x" * 12)
    assert client.get("/projekty").status_code == 200
    client.post("/logout")
    assert client.get("/projekty").status_code == 302


def test_register_rejects_short_password(client, db):
    r = client.post("/register", data={"email": "a@b.pl", "password": "krotkie", "password2": "krotkie"})
    assert r.status_code == 200
    assert "co najmniej 12" in r.get_data(as_text=True)
    assert User.query.count() == 0


def test_signup_switch(db):
    from app import create_app

    class NoSignup(TestConfig):
        ALLOW_SIGNUP = False

    app = create_app(NoSignup)
    assert app.test_client().get("/register").status_code == 404


def test_login_wrong_password(client, user):
    r = client.post("/login", data={"email": user.email, "password": "zle-haslo-123456"})
    assert "Nieprawidłowy" in r.get_data(as_text=True)


def test_open_redirect_blocked(client, user):
    r = client.post("/login?next=https://evil.example", data={"email": user.email, "password": "bardzo-dlugie-haslo"})
    assert r.headers["Location"] == "/projekty"


def test_create_user_cli(app, db):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-user", "cli@example.com", "--password", "cli-haslo-1234"])
    assert result.exit_code == 0, result.output
    assert User.query.filter_by(email="cli@example.com").one()
    result = runner.invoke(args=["create-user", "x@example.com", "--password", "krotkie"])
    assert result.exit_code != 0


def test_csrf_enforced():
    from app import create_app

    class CsrfOn(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfOn)
    with app.app_context():
        from app.extensions import db as _db
        _db.create_all()
        r = app.test_client().post("/login", data={"email": "a@b.pl", "password": "x" * 12})
        assert r.status_code == 400
