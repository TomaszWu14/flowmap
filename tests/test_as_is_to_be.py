from app.extensions import db
from app.models import Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def test_pin_as_is_and_compare_with_live_map(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/as-is-to-be").get_data(as_text=True)
    assert "Najpierw wskaż stan obecny" in html
    first = Project.query.get(p.id).versions[0]
    r = auth_client.post(f"/p/{p.id}/wersje/{first.id}/as-is")
    assert r.status_code == 302 and Project.query.get(p.id).display["as_is"] == first.id
    answer_first_tile(auth_client, p)  # TO-BE grows
    node = next(n for n in Project.query.get(p.id).nodes if n.type not in ("start", "end", "decision"))
    auth_client.post(f"/p/{p.id}/node/{node.key}/edit",
                     data={"title": node.title, "type": node.type, "actor": node.actor or "", "minutes": "30"})
    html = auth_client.get(f"/p/{p.id}/as-is-to-be").get_data(as_text=True)
    assert "AS-IS — jak jest" in html and "Nowe kroki (" in html and "Nowe kroki (0)" not in html
    assert "30 min" in html and html.count('class="mermaid"') == 2
    assert "AS-IS</span>" in auth_client.get(f"/p/{p.id}/wersje").get_data(as_text=True)


def test_missing_pinned_version_and_permissions(team):  # noqa: F811
    p = team["project"]
    p.display = {"as_is": 999999}
    db.session.commit()
    assert "Najpierw wskaż stan obecny" in team["viewer"].get(f"/p/{p.id}/as-is-to-be").get_data(as_text=True)
    vid = Project.query.get(p.id).versions[0].id
    assert team["viewer"].post(f"/p/{p.id}/wersje/{vid}/as-is").status_code == 403
    assert team["outsider"].get(f"/p/{p.id}/as-is-to-be").status_code == 404
