import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db

COMMON = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@pytest.mark.parametrize("path", ["/login", "/healthz", "/static/app.css", "/nie-ma-takiej-strony"])
def test_security_headers_on_every_response(client, db, path):
    r = client.get(path)
    for name, value in COMMON.items():
        assert r.headers[name] == value, name
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "camera=()" in r.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in r.headers  # TestConfig: no HTTPS


def test_json_is_not_cached_but_static_files_keep_their_policy(client, db):
    assert client.get("/healthz").headers["Cache-Control"] == "no-store"
    assert "no-store" not in client.get("/static/app.css").headers.get("Cache-Control", "")


def test_hsts_only_when_served_over_https():
    class HttpsConfig(TestConfig):
        SESSION_COOKIE_SECURE = True

    app = create_app(HttpsConfig)
    with app.app_context():
        _db.create_all()
        r = app.test_client().get("/healthz")
        _db.drop_all()
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
