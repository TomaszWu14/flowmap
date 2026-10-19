from app.extensions import db
from app.flow import graph as g
from app.flow.guard import check, similar_pairs
from app.models import Project
from tests.test_projects import new_project


def node(key, type="user_action", title=None):
    return {"key": key, "type": type, "title": title or key, "actor": "Klient", "data": {}}


def test_similar_steps_found_by_stem_not_for_ends():
    nodes = [node("a", "automation", "Powiadomienie e-mail"), node("b", "automation", "Wysłanie powiadomienia e-mail"),
             node("c", "screen", "Ekran płatności"), node("e1", "end", "Koniec"), node("e2", "end", "Koniec")]
    pairs = [(a["key"], b["key"]) for a, b in similar_pairs(nodes, [])]
    assert pairs == [("a", "b")]
    assert similar_pairs(nodes, [{"source": "a", "target": "b"}]) == []  # consecutive -> duplicate_step instead


def build(auth_client):
    p = new_project(auth_client, template="none")
    project = Project.query.get(p.id)
    start = project.nodes[0]
    return p, project, start


def codes(project):
    return {i["code"] for i in check(project.graph())}


def fix(client, p, **data):
    return client.post(f"/p/{p.id}/guard/fix", data=data)


def test_end_here_and_close_branch_and_add_exit(auth_client):
    p, project, start = build(auth_client)
    step = g.add_node(project, "user_action", "Wypełnia formularz", "Klient")
    g.add_edge(project, start, step)
    dec = g.add_node(project, "decision", "Czy dane są poprawne?", "System", data={"branches": ["tak"]})
    g.add_edge(project, step, dec)
    g.save_version(project, "test setup")
    db.session.commit()
    assert fix(auth_client, p, code="decision_exits", node_key=dec.key).status_code == 200
    project = Project.query.get(p.id)
    dec = project.node_by_key(dec.key)
    assert {e.label for e in project.edges if e.source_id == dec.id} == {"tak", "nie"}
    assert "decision_exits" not in codes(project)
    other = g.add_node(project, "decision", "Czy płaci kartą?", "System", data={"branches": ["tak", "nie"]})
    g.add_edge(project, step, other)
    g.add_edge(project, other, g.add_node(project, "end", "Koniec", "System"), "tak")
    g.save_version(project, "test")
    db.session.commit()
    r = fix(auth_client, p, code="open_branch", node_key=other.key, label="nie")
    assert "Strażnik" in r.get_data(as_text=True) and "mapChanged" in r.headers["HX-Trigger"]
    project = Project.query.get(p.id)
    assert {e.label for e in project.edges if e.source.key == other.key} == {"tak", "nie"}
    assert "dead_end" not in codes(project) and "open_branch" not in codes(project)


def test_quick_error_path_and_dead_end(auth_client):
    p, project, start = build(auth_client)
    pay = g.add_node(project, "integration", "Płatność online", "System")
    g.add_edge(project, start, pay)
    g.save_version(project, "test setup")
    db.session.commit()
    fix(auth_client, p, code="missing_error_path", node_key=pay.key)
    fix(auth_client, p, code="dead_end", node_key=pay.key)
    project = Project.query.get(p.id)
    assert "missing_error_path" not in codes(project) and "dead_end" not in codes(project)
    assert any(e.condition == "error" and e.label == "błąd" for e in project.edges)


def test_merge_similar_and_duplicate_and_undo(auth_client):
    p, project, start = build(auth_client)
    a = g.add_node(project, "automation", "Powiadomienie e-mail", "System")
    b = g.add_node(project, "automation", "Wysłanie powiadomienia e-mail", "System")
    end = g.add_node(project, "end", "Koniec", "System")
    g.add_edge(project, start, a)
    g.add_edge(project, start, b, "inaczej")
    g.add_edge(project, b, end)
    g.add_edge(project, a, end)
    g.save_version(project, "test setup")
    db.session.commit()
    assert "similar_steps" in codes(project)
    fix(auth_client, p, code="similar_steps", node_key=b.key, other=a.key)
    project = Project.query.get(p.id)
    assert project.node_by_key(b.key) is None
    assert {(e.source.title, e.target.title, e.label) for e in project.edges} >= {
        (start.title, "Powiadomienie e-mail", ""), (start.title, "Powiadomienie e-mail", "inaczej"),
        ("Powiadomienie e-mail", "Koniec", "")}
    auth_client.post(f"/p/{p.id}/undo")
    assert Project.query.get(p.id).node_by_key(b.key) is not None


def test_bad_fix_is_400(auth_client):
    p, project, start = build(auth_client)
    assert fix(auth_client, p, code="open_branch", node_key=start.key, label="x").status_code == 400
    assert fix(auth_client, p, code="nieznany", node_key=start.key).status_code == 400
