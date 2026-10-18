from app.models import Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_projects import new_project


def test_spec_view_sections(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/specyfikacja").get_data(as_text=True)
    assert "Rezerwacja" in html and "Encje" in html and "Role" in html
    html = auth_client.get(f"/p/{p.id}/specyfikacja?sekcja=roles").get_data(as_text=True)
    assert "Administrator" in html
    assert auth_client.get(f"/p/{p.id}/specyfikacja?sekcja=zle").status_code == 400


def test_broken_spec_offers_rebuild(auth_client, db):
    p = new_project(auth_client)
    p.spec = {"entities": [{"name": "bez klucza"}]}
    db.session.commit()
    html = auth_client.get(f"/p/{p.id}/specyfikacja").get_data(as_text=True)
    assert "Odbuduj z mapy" in html
    auth_client.post(f"/p/{p.id}/specyfikacja/odbuduj")
    assert Project.query.get(p.id).spec["entities"][0]["key"].startswith("entity:")


def test_spec_access(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].get(f"/p/{p.id}/specyfikacja").status_code == 200
    assert team["viewer"].post(f"/p/{p.id}/specyfikacja/odbuduj").status_code == 403
    assert team["outsider"].get(f"/p/{p.id}/specyfikacja").status_code == 404
