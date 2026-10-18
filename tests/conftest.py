import pytest
from flask import g

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db
from app.models import User

PASSWORD = "bardzo-dlugie-haslo"


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """scrypt is deliberately slow; tests only need a correct hash, not a strong one."""
    from functools import partial

    from werkzeug.security import generate_password_hash

    monkeypatch.setattr("app.models.generate_password_hash", partial(generate_password_hash, method="pbkdf2:sha256:1"))


@pytest.fixture
def app():
    app = create_app(TestConfig)

    @app.teardown_request
    def _forget_cached_user(_exc):
        # The fixture keeps one app context open, so `g` would leak the logged-in user between
        # requests of different test clients. In production every request gets a fresh `g`.
        g.pop("_login_user", None)
        g.pop("_user_templates", None)

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


def make_user(email="ala@example.com"):
    user = User(email=email)
    user.set_password(PASSWORD)
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def user(app):
    return make_user()


@pytest.fixture
def auth_client(client, user):
    client.post("/login", data={"email": user.email, "password": PASSWORD})
    return client
