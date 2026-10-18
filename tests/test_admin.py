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
