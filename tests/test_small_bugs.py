from app.extensions import db
from app.models import Project
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def test_delete_edge_by_id_and_stale_id_is_404(auth_client):
    p = new_project(auth_client)
    for _ in range(3):
        answer_first_tile(auth_client, p)
    project = Project.query.get(p.id)
    edge = project.edges[-1]
    eid, pair = edge.id, (edge.source_id, edge.target_id)
    assert auth_client.post(f"/p/{p.id}/edge/{eid}/delete").status_code == 200
    assert pair not in {(e.source_id, e.target_id) for e in Project.query.get(p.id).edges}
    assert auth_client.post(f"/p/{p.id}/edge/{eid}/delete").status_code == 404


def test_error_pages_are_polish(auth_client):
    p = new_project(auth_client)
    r = auth_client.get(f"/p/{p.id}/undo")
    assert r.status_code == 405 and "nie jest dostępna" in r.get_data(as_text=True)
    project = Project.query.get(p.id)
    project.spec = {"entities": "zepsute"}
    db.session.commit()
    r = auth_client.get(f"/p/{p.id}/eksport/claude-code.zip")
    assert r.status_code == 409 and "uszkodzona" in r.get_data(as_text=True)


def test_guard_review_without_key_hides_ai_button(auth_client):
    p = new_project(auth_client)
    html = auth_client.post(f"/p/{p.id}/guard/review").get_data(as_text=True)
    assert "wymaga klucza" in html and "Uruchom przegląd AI" not in html


def test_project_list_counts_steps(auth_client):
    p = new_project(auth_client)
    n = len(Project.query.get(p.id).nodes)
    assert f"{n} krok" in auth_client.get("/projekty").get_data(as_text=True)


def test_ai_gate_explains_admin_switch_and_limit(auth_client, app):
    from app import settings
    from app.models import User
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    p = new_project(auth_client)
    settings.set_value("ai_enabled", False)
    db.session.commit()
    html = auth_client.post(f"/p/{p.id}/guard/review").get_data(as_text=True)
    assert "wyłączone przez administratora" in html
    settings.set_value("ai_enabled", True)
    settings.set_value("ai_daily_limit", 0)
    db.session.commit()
    html = auth_client.post(f"/p/{p.id}/guard/review").get_data(as_text=True)
    assert "limit" in html and User.query.first() is not None
