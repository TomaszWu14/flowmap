from app.flow.timing import analyze, duration_label


def n(key, type="user_action", actor="Biuro", minutes=None, cost=None):
    data = {k: v for k, v in (("minutes", minutes), ("cost", cost)) if v is not None}
    return {"key": key, "type": type, "title": key, "actor": actor, "data": data}


def e(a, b, label=""):
    return {"source": a, "target": b, "label": label, "condition": ""}


GRAPH = {"nodes": [n("s", "start"), n("a", minutes=10, cost=5), n("w", "wait", "System", minutes=60),
                   n("d", "decision"), n("b", actor="Magazyn", minutes=30, cost=12.5), n("x", minutes=500),
                   n("k", "end")],
         "edges": [e("s", "a"), e("a", "w"), e("w", "d"), e("d", "b", "tak"), e("d", "x", "nie"), e("b", "k"),
                   e("x", "k")]}


def test_happy_path_totals_bottleneck_and_roles():
    r = analyze(GRAPH)
    assert (r["minutes"], r["cost"], r["waiting_pct"]) == (100, 17.5, 60)  # "nie" branch (500 min) is off the path
    assert [s["title"] for s in r["slowest"]] == ["w", "b", "a"] and r["slowest"][0]["pct"] == 60
    assert r["roles"] == [("System", 60), ("Magazyn", 30), ("Biuro", 10)] and r["missing"] == []


def test_nothing_timed_means_no_analysis_and_labels():
    assert analyze({"nodes": [n("s", "start"), n("a")], "edges": [e("s", "a")]}) is None
    assert duration_label(90) == "1 h 30 min" and duration_label(2880) == "2 dni" and duration_label(0) == "0 min"


def test_minutes_and_cost_from_the_step_form_to_guard_report_and_json(auth_client):
    import io

    from app.models import Project
    from tests.test_flow import answer_first_tile
    from tests.test_projects import new_project

    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    node = next(n for n in Project.query.get(p.id).nodes if n.type not in ("start", "decision", "end"))
    form = {"title": node.title, "type": node.type, "actor": node.actor or "Recepcja", "minutes": "90", "cost": "12.5"}
    auth_client.post(f"/p/{p.id}/node/{node.key}/edit", data=form)
    data = Project.query.get(p.id).node_by_key(node.key).data
    assert (data["minutes"], data["cost"]) == (90, 12.5)
    guard_html = auth_client.get(f"/p/{p.id}/guard").get_data(as_text=True)
    assert "Czas i koszt sprawy" in guard_html and "1 h 30 min" in guard_html and "12,50 zł" in guard_html
    assert "Czas i koszt sprawy" in auth_client.get(f"/p/{p.id}/raport").get_data(as_text=True)
    panel = auth_client.get(f"/p/{p.id}/panel?node={node.key}").get_data(as_text=True)
    assert 'name="minutes"' in panel and 'value="90"' in panel
    body = auth_client.get(f"/p/{p.id}/eksport/projekt.json").data
    auth_client.post("/projekty/import", data={"file": (io.BytesIO(body), "p.json")},
                     content_type="multipart/form-data")
    copy = Project.query.order_by(Project.id.desc()).first()
    assert copy.id != p.id and copy.node_by_key(node.key).data.get("minutes") == 90
    auth_client.post(f"/p/{p.id}/node/{node.key}/edit", data=form | {"minutes": "", "cost": "-3"})
    assert Project.query.get(p.id).node_by_key(node.key).data.get("minutes") is None  # cleared; negative ignored
