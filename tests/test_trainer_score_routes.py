from app.models import Evaluation
from tests.test_collaborators import team  # noqa: F401
from tests.test_projects import new_project


def test_evaluate_saves_history_and_shows_trend(auth_client):
    p = new_project(auth_client)
    assert "Oceń teraz" in auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
    assert auth_client.post(f"/p/{p.id}/ocena").status_code == 302
    auth_client.post(f"/p/{p.id}/ocena")
    assert Evaluation.query.filter_by(project_id=p.id).count() == 4
    html = auth_client.get(f"/p/{p.id}/ocena").get_data(as_text=True)
    assert "Mapa procesu" in html and "Projekt aplikacji" in html and "Strażnik mapy" in html
    assert html.count('class="history-row"') == 2
    assert f"/p/{p.id}/ocena" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    assert f"/p/{p.id}/ocena" in auth_client.get(f"/p/{p.id}/projekt-aplikacji").get_data(as_text=True)


def test_viewer_can_evaluate_outsider_cannot(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].post(f"/p/{p.id}/ocena").status_code == 302
    assert team["outsider"].get(f"/p/{p.id}/ocena").status_code == 404
