import pytest

from app.models import AuditEvent, Project, ProjectMember, QuestionLog
from tests.conftest import PASSWORD, make_user
from tests.test_projects import new_project


def client_for(app, email):
    c = app.test_client()
    c.post("/login", data={"email": email, "password": PASSWORD})
    return c


@pytest.fixture
def team(app, auth_client, db):
    """Owner (auth_client) with a project, an editor, a viewer and an outsider."""
    p = new_project(auth_client)
    for email in ("ed@example.com", "vi@example.com", "obcy@example.com"):
        make_user(email)
    auth_client.post(f"/p/{p.id}/czlonkowie", data={"email": "ED@example.com", "role": "editor"})
    auth_client.post(f"/p/{p.id}/czlonkowie", data={"email": "vi@example.com", "role": "viewer"})
    return {
        "project": p,
        "owner": auth_client,
        "editor": client_for(app, "ed@example.com"),
        "viewer": client_for(app, "vi@example.com"),
        "outsider": client_for(app, "obcy@example.com"),
    }


def test_members_added_and_listed(team):
    p = team["project"]
    assert sorted(m.role for m in Project.query.get(p.id).members) == ["editor", "viewer"]
    html = team["editor"].get("/projekty").get_data(as_text=True)
    assert "Udostępnione dla mnie" in html and "edytor" in html and p.name in html
    assert {"member_added"} <= {e.action for e in AuditEvent.query}


def test_permission_matrix(team):
    p = team["project"]
    key = p.nodes[0].key
    view_urls = [f"/p/{p.id}", f"/p/{p.id}/graph.json", f"/p/{p.id}/panel", f"/p/{p.id}/symulacja",
                 f"/p/{p.id}/eksport", f"/p/{p.id}/eksport/spec.md", f"/p/{p.id}/wersje", f"/p/{p.id}/guard"]
    for who in ("editor", "viewer"):
        for url in view_urls:
            assert team[who].get(url).status_code == 200, (who, url)
    for url in view_urls:
        assert team["outsider"].get(url).status_code == 404, url

    edit_posts = [f"/p/{p.id}/undo", f"/p/{p.id}/layout", f"/p/{p.id}/node/{key}/edit"]
    for url in edit_posts:
        assert team["viewer"].post(url).status_code == 403, url
        assert team["outsider"].post(url).status_code == 404, url
    assert team["editor"].post(f"/p/{p.id}/layout").status_code == 204

    owner_only = [f"/p/{p.id}/udostepnianie", f"/p/{p.id}/usun", f"/p/{p.id}/czlonkowie"]
    assert team["editor"].get(owner_only[0]).status_code == 403
    assert team["editor"].post(owner_only[1]).status_code == 403
    assert team["editor"].post(owner_only[2], data={"email": "obcy@example.com", "role": "editor"}).status_code == 403
    assert Project.query.get(p.id) is not None


def test_editor_answers_questions(team):
    p = team["project"]
    team["editor"].get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id, answer="").first()
    r = team["editor"].post(f"/p/{p.id}/answer", data={"log_id": log.id, "option": 0})
    assert r.status_code == 200 and len(Project.query.get(p.id).nodes) > 1


def test_viewer_gets_read_only_workspace(team):
    p = team["project"]
    html = team["viewer"].get(f"/p/{p.id}").get_data(as_text=True)
    assert "tylko podgląd" in html and 'data-readonly="1"' in html and "btn-undo" not in html
    panel = team["viewer"].get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert "tylko podgląd" in panel and "tile" not in panel
    assert QuestionLog.query.filter_by(project_id=p.id).count() == 0  # viewer never triggers questions


def test_copy_belongs_to_whoever_copies(team, db):
    p = team["project"]
    team["viewer"].post(f"/p/{p.id}/kopia")
    copy = Project.query.order_by(Project.id.desc()).first()
    assert copy.id != p.id and copy.owner.email == "vi@example.com"


def test_role_change_and_removal(team):
    p = team["project"]
    vi = ProjectMember.query.join(ProjectMember.user).filter_by(email="vi@example.com").one()
    team["owner"].post(f"/p/{p.id}/czlonkowie/{vi.id}/rola", data={"role": "editor"})
    assert team["viewer"].post(f"/p/{p.id}/layout").status_code == 204
    team["owner"].post(f"/p/{p.id}/czlonkowie/{vi.id}/usun")
    assert team["viewer"].get(f"/p/{p.id}").status_code == 404


def test_add_member_validation(team):
    p = team["project"]
    owner = team["owner"]
    r = owner.post(f"/p/{p.id}/czlonkowie", data={"email": "nikt@example.com", "role": "editor"}, follow_redirects=True)
    assert "musi najpierw się zarejestrować" in r.get_data(as_text=True)
    r = owner.post(f"/p/{p.id}/czlonkowie", data={"email": "ed@example.com", "role": "viewer"}, follow_redirects=True)
    assert "ma już dostęp" in r.get_data(as_text=True)
    assert owner.post(f"/p/{p.id}/czlonkowie", data={"email": "obcy@example.com", "role": "admin"}).status_code == 400
    assert len(Project.query.get(p.id).members) == 2
