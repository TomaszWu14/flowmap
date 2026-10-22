from app.ai.rules import _merge_option, next_question
from app.flow.guard import check
from app.models import Project, QuestionLog
from tests.test_projects import new_project


def n(key, type="user_action", branches=None):
    return {"key": key, "type": type, "title": key, "actor": "Magazyn", "inputs": [], "outputs": [], "description": "",
            "data": {"branches": branches} if branches else {}}


def e(a, b, label=""):
    return {"source": a, "target": b, "label": label, "condition": ""}


def split_graph(joined=False):
    nodes = [n("s", "start"), n("and", "parallel", ["pakowanie", "faktura"]), n("pak"), n("fak")]
    edges = [e("s", "and"), e("and", "pak", "pakowanie"), e("and", "fak", "faktura")]
    if joined:
        nodes += [n("join", "parallel"), n("end", "end")]
        edges += [e("pak", "join"), e("fak", "join"), e("join", "end")]
    return {"nodes": nodes, "edges": edges}


def codes(g):
    return {i["code"] for i in check(g)}


def test_guard_wants_parallel_paths_to_meet():
    assert "parallel_unjoined" in codes(split_graph())
    assert "parallel_unjoined" not in codes(split_graph(joined=True))
    lonely = {"nodes": [n("s", "start"), n("and", "parallel", ["a", "b"]), n("x"), n("end", "end")],
              "edges": [e("s", "and"), e("and", "x", "a"), e("x", "end")]}
    assert {"decision_exits", "open_branch"} <= codes(lonely)


def test_merge_tile_creates_a_join_then_offers_to_meet_there():
    g = split_graph()
    first = _merge_option(g, g["nodes"][2])
    assert first.steps[0].type == "parallel" and not first.steps[0].branches
    g["nodes"].append(n("join", "parallel"))
    g["edges"].append(e("pak", "join"))
    second = _merge_option(g, g["nodes"][3])
    assert second.kind == "connect" and second.connect_to == "join"
    assert _merge_option(g, g["nodes"][1]) is None  # not offered on the split itself
    q = next_question(g, g["nodes"][3], None, "quick", None)
    assert q.options[0].label.startswith("Zbiegnij ścieżki")


def test_and_gateway_from_other_opens_every_path(auth_client):
    p = new_project(auth_client, template="none")
    auth_client.get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id, answer="", kind="next").first()
    auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "other": "1", "type": "parallel",
                                                "text": "Równolegle: magazyn i księgowość",
                                                "branches": "pakowanie, faktura"})
    gate = next(x for x in Project.query.get(p.id).nodes if x.type == "parallel")
    assert gate.data["branches"] == ["pakowanie", "faktura"]
    html = auth_client.get(f"/p/{p.id}/guard").get_data(as_text=True)
    assert "pakowanie" in html and "faktura" in html  # both paths are open questions


def test_export_pages_handle_parallel_gateway(auth_client):
    # Regression: to_mermaid had no shape for "parallel", so export, report and spec ZIP crashed with 500.
    from app.extensions import db
    from app.flow import graph as g

    p = new_project(auth_client)
    g.load_graph(p, split_graph(joined=True))
    db.session.commit()
    for url in (f"/p/{p.id}/eksport", f"/p/{p.id}/raport", f"/p/{p.id}/eksport/diagram.mmd"):
        r = auth_client.get(url)
        assert r.status_code == 200, url
    assert "{{" in auth_client.get(f"/p/{p.id}/eksport/diagram.mmd").get_data(as_text=True)  # hexagon = AND gateway
