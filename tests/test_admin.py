from app.models import User
from tests.conftest import PASSWORD, make_user
from tests.test_projects import new_project


def login(client, email):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def test_admin_panel_hidden_from_regular_users(auth_client):
    assert auth_client.get("/admin/").status_code == 404
    assert auth_client.post("/admin/users/1/block").status_code == 404
    assert "Admin" not in auth_client.get("/projekty").get_data(as_text=True)


def test_admin_panel_requires_login(client, db):
    assert client.get("/admin/").status_code == 302


def test_admin_sees_stats_and_users_but_not_project_content(client, db):
    admin = make_user("admin@example.com")
    admin.is_admin = True
    other = make_user("ola@example.com")
    db.session.commit()
    login(client, other.email)
    new_project(client, "Klient chce umówić wizytę w tajnym salonie")
    client.post("/logout")
    login(client, admin.email)
    html = client.get("/admin/").get_data(as_text=True)
    assert "ola@example.com" in html and "Użytkownicy" in html and "Rejestracja" in html
    assert "tajnym salonie" not in html
    assert admin.last_login_at is not None


def test_block_ends_session_and_prevents_login(client, db):
    admin = make_user("admin@example.com")
    admin.is_admin = True
    other = make_user("ola@example.com")
    db.session.commit()
    other_client = client.application.test_client()
    login(other_client, other.email)
    assert other_client.get("/projekty").status_code == 200

    login(client, admin.email)
    client.post(f"/admin/users/{other.id}/block")
    assert db.session.get(User, other.id).is_blocked
    assert other_client.get("/projekty").status_code == 302  # session no longer valid
    r = login(other_client, other.email)
    assert "zablokowane" in r.get_data(as_text=True)

    client.post(f"/admin/users/{other.id}/unblock")
    assert login(other_client, other.email).status_code == 302


def test_grant_admin_and_self_protection(client, db):
    admin = make_user("admin@example.com")
    admin.is_admin = True
    other = make_user("ola@example.com")
    db.session.commit()
    login(client, admin.email)
    client.post(f"/admin/users/{other.id}/grant-admin")
    assert db.session.get(User, other.id).is_admin
    r = client.post(f"/admin/users/{admin.id}/block", follow_redirects=True)
    assert "własnego konta" in r.get_data(as_text=True)
    assert not db.session.get(User, admin.id).is_blocked
    client.post(f"/admin/users/{admin.id}/revoke-admin")
    assert db.session.get(User, admin.id).is_admin
    assert client.post(f"/admin/users/{other.id}/delete").status_code == 404


def make_admin(client, db):
    admin = make_user("admin@example.com")
    admin.is_admin = True
    db.session.commit()
    login(client, admin.email)
    return admin


def test_settings_toggle_signup_and_limit(client, db):
    from app import settings

    make_admin(client, db)
    assert settings.signup_open() is True
    r = client.post("/admin/settings", data={"ai_daily_limit": "7"}, follow_redirects=True)
    assert "Ustawienia zapisane" in r.get_data(as_text=True)
    assert settings.signup_open() is False and settings.ai_daily_limit() == 7
    client.post("/logout")
    assert client.get("/register").status_code == 404
    assert "Załóż konto" not in client.get("/").get_data(as_text=True)


def test_settings_validation_and_access(client, db):
    from app import settings

    make_admin(client, db)
    r = client.post("/admin/settings", data={"ai_daily_limit": "-1", "allow_signup": "on"}, follow_redirects=True)
    assert "od 0 do 10000" in r.get_data(as_text=True)
    assert settings.ai_daily_limit() == 100
    other = make_user("ola@example.com")
    client.post("/logout")
    login(client, other.email)
    assert client.post("/admin/settings", data={"ai_daily_limit": "1"}).status_code == 404


def test_ai_kill_switch(client, db, app):
    from app import settings
    from app.ai.client import ai_enabled

    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    make_admin(client, db)
    with app.test_request_context():
        assert ai_enabled()
    client.post("/admin/settings", data={"ai_daily_limit": "5", "allow_signup": "on"})
    assert settings.get("ai_enabled") is False
    with app.test_request_context():
        assert not ai_enabled()


def test_audit_log_records_events(client, db):
    from app.models import AuditEvent

    admin = make_admin(client, db)
    other = make_user("ola@example.com")
    client.post(f"/admin/users/{other.id}/block")
    client.post("/admin/settings", data={"ai_daily_limit": "9", "allow_signup": "on"})
    anon = client.application.test_client()
    anon.post("/login", data={"email": "ola@example.com", "password": PASSWORD})  # blocked
    anon.post("/login", data={"email": "nikt@example.com", "password": "zle-haslo-123456"})
    actions = [e.action for e in AuditEvent.query.order_by(AuditEvent.id)]
    assert actions == ["login", "user_blocked", "settings_changed", "login_blocked", "login_failed"]
    failed = AuditEvent.query.filter_by(action="login_failed").one()
    assert failed.actor_id is None and failed.actor_email == "nikt@example.com"
    assert AuditEvent.query.filter_by(action="user_blocked").one().actor_id == admin.id

    html = client.get("/admin/zdarzenia?action=login_failed").get_data(as_text=True)
    assert "nikt@example.com" in html and "Zablokowanie konta" not in html.split("<tbody>")[1]
    html = client.get("/admin/zdarzenia?q=ola@").get_data(as_text=True)
    assert "ola@example.com" in html


def test_audit_register_and_projects(client, db):
    from app.models import AuditEvent

    client.post("/register", data={"email": "n@example.com", "password": "x" * 12, "password2": "x" * 12})
    new_project(client)
    from app.models import Project

    pid = Project.query.one().id
    client.post(f"/p/{pid}/usun")
    client.post("/logout")
    actions = [e.action for e in AuditEvent.query.order_by(AuditEvent.id)]
    assert actions == ["register", "project_created", "project_deleted", "logout"]
    assert client.get("/admin/zdarzenia").status_code == 302
