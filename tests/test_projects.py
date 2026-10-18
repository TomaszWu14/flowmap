from app.models import Project
from tests.conftest import make_user


def new_project(client, sentence="Klient chce umówić wizytę w salonie", mode="quick", template="auto"):
    r = client.post("/projekty/nowy", data={"name": "Salon", "start_sentence": sentence, "mode": mode,
                                            "template": template})
    assert r.status_code == 302
    return Project.query.order_by(Project.id.desc()).first()


def test_create_project_with_start_node_and_version(auth_client):
    p = new_project(auth_client)
    assert p.template == "booking"
    assert [n.type for n in p.nodes] == ["start"]
    assert p.nodes[0].title == "Klient chce umówić wizytę w salonie"
    assert len(p.versions) == 1 and p.version_cursor_id == p.versions[0].id
    assert "Salon" in auth_client.get("/projekty").get_data(as_text=True)


def test_template_autodetect(auth_client):
    assert new_project(auth_client, "Klient składa zamówienie w sklepie").template == "order"
    assert new_project(auth_client, "Klient zgłasza awarię pralki").template == "service"
    assert new_project(auth_client, "Pracownik rozlicza delegację").template is None
    assert new_project(auth_client, "Klient chce umówić wizytę", template="none").template is None


def test_foreign_project_is_404(auth_client, db):
    other = make_user("obcy@example.com")
    from app.projects.service import create_project
    foreign = create_project(other, "Cudzy", "Klient chce kupić buty", "quick")
    key = foreign.nodes[0].key
    for url in [f"/p/{foreign.id}", f"/p/{foreign.id}/graph.json", f"/p/{foreign.id}/panel",
                f"/p/{foreign.id}/symulacja", f"/p/{foreign.id}/eksport", f"/p/{foreign.id}/eksport/spec.md",
                f"/p/{foreign.id}/wersje", f"/p/{foreign.id}/guard"]:
        assert auth_client.get(url).status_code == 404, url
    for url in [f"/p/{foreign.id}/usun", f"/p/{foreign.id}/kopia", f"/p/{foreign.id}/undo",
                f"/p/{foreign.id}/node/{key}/delete", f"/p/{foreign.id}/answer", f"/p/{foreign.id}/positions"]:
        assert auth_client.post(url).status_code == 404, url
    assert db.session.get(Project, foreign.id) is not None


def test_anonymous_redirected_to_login(client, db):
    assert client.get("/projekty").status_code == 302
    assert client.get("/p/1").status_code == 302


def test_delete_and_copy(auth_client, db):
    p = new_project(auth_client)
    r = auth_client.post(f"/p/{p.id}/kopia")
    assert r.status_code == 302
    copy = Project.query.order_by(Project.id.desc()).first()
    assert copy.id != p.id and copy.name.endswith("(kopia)") and len(copy.nodes) == 1
    auth_client.post(f"/p/{p.id}/usun")
    assert db.session.get(Project, p.id) is None
