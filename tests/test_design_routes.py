from app.models import Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import play_to_end
from tests.test_projects import new_project


def test_design_tab_shows_class_diagram_and_guard(auth_client):
    p = new_project(auth_client)
    r = auth_client.get(f"/p/{p.id}/projekt-aplikacji")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'class="mermaid"' in html and "classDiagram" in html
    assert "vendor/mermaid.min.js" in html and "design.js" in html
    assert "Projekt aplikacji" in html and "Klasy" in html
    assert auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=zle").status_code == 400


def test_links_from_map_and_spec(auth_client):
    p = new_project(auth_client)
    for url in (f"/p/{p.id}", f"/p/{p.id}/specyfikacja"):
        assert f"/p/{p.id}/projekt-aplikacji" in auth_client.get(url).get_data(as_text=True)


def test_design_tab_permissions(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].get(f"/p/{p.id}/projekt-aplikacji").status_code == 200
    assert team["outsider"].get(f"/p/{p.id}/projekt-aplikacji").status_code == 404


def test_broken_spec_points_to_rebuild(auth_client, db):
    p = new_project(auth_client)
    p.spec = {"entities": [{"name": "bez klucza"}]}
    db.session.commit()
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji").get_data(as_text=True)
    assert "uszkodzona" in html and f"/p/{p.id}/specyfikacja" in html


def test_old_spec_without_use_cases_is_completed(auth_client, db):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    stored = dict(p.spec)
    stored.pop("use_cases", None)
    p.spec = stored
    db.session.commit()
    html = auth_client.get(f"/p/{p.id}/specyfikacja?sekcja=use_cases").get_data(as_text=True)
    assert "Przypadki użycia" in html
    assert "use_cases" in Project.query.get(p.id).spec
