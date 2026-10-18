import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db
from app.models import User

PASSWORD = "bardzo-dlugie-haslo"


@pytest.fixture
def app():
    app = create_app(TestConfig)
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
