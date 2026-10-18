from app.flow.diff import diff_graphs, node_status
from app.models import Project
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def n(key, title, **kw):
    return {"key": key, "type": kw.pop("type", "user_action"), "title": title, "actor": kw.pop("actor", "Klient"),
            "description": "", "inputs": kw.pop("inputs", []), "outputs": [], "data": kw.pop("data", {})}


def test_diff_graphs_detects_every_kind_of_change():
    old = {"nodes": [n("s", "Start", type="start"), n("a", "Krok A"), n("d", "Decyzja", type="decision",
                                                                         data={"branches": ["tak", "nie"]})],
           "edges": [{"source": "s", "target": "a", "label": ""}, {"source": "a", "target": "d", "label": ""}]}
    new = {"nodes": [n("s", "Start", type="start"), n("a", "Krok A2", inputs=["E-mail"]),
                     n("d", "Decyzja", type="decision", data={"branches": ["tak", "nie", "może"]}), n("b", "Krok B")],
           "edges": [{"source": "s", "target": "a", "label": ""}, {"source": "d", "target": "b", "label": "tak"}]}
    d = diff_graphs(old, new)
    assert [x["key"] for x in d["added"]] == ["b"] and d["removed"] == []
    changed = {c["node"]["key"]: {f[0] for f in c["fields"]} for c in d["changed"]}
    assert changed == {"a": {"tytuł", "dane wejściowe"}, "d": {"gałęzie"}}
    assert d["edges_added"] == [{"source": "Decyzja", "target": "Krok B", "label": "tak"}]
    assert d["edges_removed"] == [{"source": "Krok A2", "target": "Decyzja", "label": ""}]
    assert node_status(d) == {"b": "added", "a": "changed", "d": "changed"}
    assert diff_graphs(new, new) == {"added": [], "removed": [], "changed": [], "edges_added": [], "edges_removed": []}


def test_compare_pages(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/wersje/porownaj", follow_redirects=True).get_data(as_text=True)
    assert "co najmniej dwie wersje" in html
    answer_first_tile(auth_client, p)
    p = Project.query.get(p.id)
    html = auth_client.get(f"/p/{p.id}/wersje/porownaj").get_data(as_text=True)
    assert "Dodane kroki" in html and "Wybór usługi" in html
    first, last = p.versions[0], p.versions[-1]
    data = auth_client.get(f"/p/{p.id}/wersje/{last.id}/graph.json?od={first.id}").json
    assert {x["diff"] for x in data["nodes"]} == {"", "added"}
    assert auth_client.get(f"/p/{p.id}/wersje/99999/graph.json").status_code == 404
    # swapped order is normalised (older first)
    html = auth_client.get(f"/p/{p.id}/wersje/porownaj?od={last.id}&do={first.id}").get_data(as_text=True)
    assert "Dodane kroki" in html


def test_compare_respects_access(auth_client, app):
    from tests.conftest import PASSWORD, make_user

    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    other = make_user("obcy@example.com")
    c = app.test_client()
    c.post("/login", data={"email": other.email, "password": PASSWORD})
    assert c.get(f"/p/{p.id}/wersje/porownaj").status_code == 404
    assert c.get(f"/p/{p.id}/wersje/{p.versions[-1].id}/graph.json").status_code == 404
