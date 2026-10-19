from app.flow.guard import report
from app.models import Comment, Project
from tests.test_collaborators import team  # noqa: F401  (fixture)


def add(client, p, key, body="Czy tu nie brakuje SMS?"):
    return client.post(f"/p/{p.id}/node/{key}/komentarze", data={"body": body})


def test_viewer_comments_and_map_shows_count(team):  # noqa: F811
    p = team["project"]
    key = p.nodes[0].key
    r = add(team["viewer"], p, key, "Uwaga <b>pogrubiona</b>")
    assert r.status_code == 200 and "mapChanged" in r.headers["HX-Trigger"]
    html = r.get_data(as_text=True)
    assert "&lt;b&gt;pogrubiona&lt;/b&gt;" in html and "1 otwarte" in html
    data = team["owner"].get(f"/p/{p.id}/graph.json").json
    node = next(n for n in data["nodes"] if n["key"] == key)
    assert node["comments"] == 1 and any(i["code"] == "open_comment" for i in data["issues"])


def test_resolve_rules(team):  # noqa: F811
    p = team["project"]
    key = p.nodes[0].key
    add(team["editor"], p, key)
    c = Comment.query.one()
    assert team["viewer"].post(f"/p/{p.id}/komentarze/{c.id}/rozwiaz").status_code == 403  # not the author
    team["owner"].post(f"/p/{p.id}/komentarze/{c.id}/rozwiaz")
    assert Comment.query.one().resolved
    data = team["owner"].get(f"/p/{p.id}/graph.json").json
    assert not any(i["code"] == "open_comment" for i in data["issues"])


def test_delete_rules(team):  # noqa: F811
    p = team["project"]
    key = p.nodes[0].key
    add(team["viewer"], p, key)
    c = Comment.query.one()
    r = team["editor"].post(f"/p/{p.id}/komentarze/{c.id}/usun")
    assert r.status_code == 403 and "tylko właściciel" in r.get_data(as_text=True)
    team["viewer"].post(f"/p/{p.id}/komentarze/{c.id}/usun")
    assert Comment.query.count() == 0
    add(team["editor"], p, key)
    team["owner"].post(f"/p/{p.id}/komentarze/{Comment.query.one().id}/usun")  # owner moderates
    assert Comment.query.count() == 0


def test_access_and_validation(team):  # noqa: F811
    p = team["project"]
    key = p.nodes[0].key
    assert add(team["outsider"], p, key).status_code == 404
    assert "nie może być pusty" in add(team["owner"], p, key, "  ").get_data(as_text=True)
    assert add(team["owner"], p, "nieznany").status_code == 404
    assert Comment.query.count() == 0


def test_guard_ignores_comments_of_deleted_steps():
    graph = {"nodes": [{"key": "a", "type": "start", "title": "A", "actor": "", "data": {}}], "edges": []}
    rep = report(graph, {"a": 2, "gone": 1})
    assert [i["code"] for i in rep["issues"] if i["code"] == "open_comment"] == ["open_comment"]


def test_project_delete_removes_comments(team):  # noqa: F811
    p = team["project"]
    add(team["owner"], p, p.nodes[0].key)
    team["owner"].post(f"/p/{p.id}/usun")
    assert Project.query.get(p.id) is None and Comment.query.count() == 0
