import re

from app.flow import graph as g
from app.flow import questions as q
from app.models import Project, QuestionLog
from tests.test_projects import new_project


def answer_first_tile(client, project, prefer=None):
    """Load the panel and click a tile (first one, or the first whose label contains `prefer`)."""
    html = client.get(f"/p/{project.id}/panel").get_data(as_text=True)
    log = QuestionLog.query.filter_by(project_id=project.id, answer="").order_by(QuestionLog.id.desc()).first()
    assert log is not None, html
    labels = [o["label"] for o in log.options["options"]]
    idx = 0
    if prefer:
        idx = next((i for i, lab in enumerate(labels) if prefer in lab), 0)
    r = client.post(f"/p/{project.id}/answer", data={"log_id": log.id, "option": idx})
    assert r.status_code == 200
    return log


def play_to_end(client, project, limit=60):
    """Answer the first tile until no question is left. Returns number of questions asked."""
    asked = 0
    while q.pending_nodes(project):
        answer_first_tile(client, project)
        asked += 1
        assert asked < limit, "process never finished"
    return asked


def test_first_question_offers_template_tiles(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert "Co dzieje się dalej" in html
    log = QuestionLog.query.filter_by(project_id=p.id).one()
    opts = log.options["options"]
    assert 3 <= len(opts) <= 5
    assert opts[0]["steps"][0]["title"] == "Wybór usługi"
    assert opts[-1]["label"] == "Koniec procesu"
    # re-rendering reuses the open question instead of logging a new one
    auth_client.get(f"/p/{p.id}/panel")
    assert QuestionLog.query.filter_by(project_id=p.id).count() == 1


def test_quick_mode_finishes_booking_in_few_questions(auth_client):
    p = new_project(auth_client, mode="quick")
    asked = play_to_end(auth_client, p)
    assert asked <= 8
    p = Project.query.get(p.id)
    types = {n.type for n in p.nodes}
    assert {"start", "screen", "decision", "end"} <= types
    assert p.status == "complete"
    assert "Mapa procesu jest gotowa" in auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    # the loop "nie" -> back to slot selection exists (no duplicated step)
    titles = [n.title for n in p.nodes]
    assert titles.count("Wybór terminu i specjalisty") == 1


def test_thorough_mode_asks_more_including_helpers(auth_client):
    p = new_project(auth_client, mode="thorough")
    asked = play_to_end(auth_client, p)
    assert 12 <= asked <= 35
    kinds = {log.kind for log in QuestionLog.query.filter_by(project_id=p.id)}
    assert {"next", "error"} <= kinds


def test_decision_branches_become_open_slots(auth_client, db):
    p = new_project(auth_client, sentence="Pracownik składa wniosek urlopowy")  # no template -> generic rules
    log = answer_first_tile(auth_client, p, prefer="Czy użytkownik ma konto")
    decision = next(n for n in p.nodes if n.type == "decision")
    assert decision.data["branches"] == ["tak", "nie"]
    assert g.open_labels(p, decision) == ["tak", "nie"]
    assert log.answer
    # next question targets the decision's first branch
    html = auth_client.get(f"/p/{p.id}/panel").get_data(as_text=True)
    assert "→ tak" in html


def test_other_answer_creates_custom_step(auth_client):
    p = new_project(auth_client, sentence="Pracownik składa wniosek urlopowy")
    auth_client.get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id).one()
    r = auth_client.post(f"/p/{p.id}/answer", data={
        "log_id": log.id, "other": "1", "text": "Kierownik <b>akceptuje</b>", "type": "decision",
        "actor": "Kierownik", "branches": "zgoda, odmowa"})
    assert r.status_code == 200
    node = next(n for n in p.nodes if n.type == "decision")
    assert node.title == "Kierownik <b>akceptuje</b>" and node.data["branches"] == ["zgoda", "odmowa"]
    html = auth_client.get(f"/p/{p.id}/panel?node={node.key}").get_data(as_text=True)
    assert "<b>akceptuje</b>" not in html and "&lt;b&gt;akceptuje&lt;/b&gt;" in html


def test_other_answer_requires_text(auth_client):
    p = new_project(auth_client)
    auth_client.get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id).one()
    r = auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "other": "1", "text": " "})
    html = r.get_data(as_text=True)
    assert "Wpisz odpowiedź" in html
    assert len(p.nodes) == 1


def test_answer_sends_map_changed_trigger(auth_client):
    p = new_project(auth_client)
    auth_client.get(f"/p/{p.id}/panel")
    log = QuestionLog.query.filter_by(project_id=p.id).one()
    r = auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "option": 0})
    assert "mapChanged" in r.headers["HX-Trigger"]
    # answering the same question twice does not duplicate steps
    count = len(p.nodes)
    auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "option": 0})
    assert len(Project.query.get(p.id).nodes) == count


def test_undo_redo(auth_client):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    after = len(p.nodes)
    assert after > 1
    assert auth_client.get(f"/p/{p.id}/graph.json").json["can_undo"] is True
    auth_client.post(f"/p/{p.id}/undo")
    p = Project.query.get(p.id)
    assert len(p.nodes) == 1
    data = auth_client.get(f"/p/{p.id}/graph.json").json
    assert data["can_undo"] is False and data["can_redo"] is True
    auth_client.post(f"/p/{p.id}/redo")
    assert len(Project.query.get(p.id).nodes) == after


def test_node_edit_delete_connect_and_end(auth_client):
    p = new_project(auth_client, sentence="Pracownik składa wniosek urlopowy")
    answer_first_tile(auth_client, p)
    start, second = p.nodes[0], p.nodes[1]
    r = auth_client.post(f"/p/{p.id}/node/{second.key}/edit", data={
        "title": "Formularz wniosku", "type": "screen", "actor": "Pracownik", "description": "",
        "inputs": "Data od, Data do", "outputs": "Saldo urlopu"})
    assert r.status_code == 200
    assert second.title == "Formularz wniosku" and second.inputs == ["Data od", "Data do"]
    auth_client.post(f"/p/{p.id}/node/{second.key}/connect", data={"target": start.key, "label": "ponów"})
    assert any(e.label == "ponów" and e.target_id == start.id for e in p.edges)
    # cannot mark as end while it has outgoing edges
    html = auth_client.post(f"/p/{p.id}/node/{second.key}/end").get_data(as_text=True)
    assert "ma kolejne kroki" in html
    auth_client.post(f"/p/{p.id}/node/{second.key}/delete")
    p = Project.query.get(p.id)
    assert [n.type for n in p.nodes] == ["start"] and not p.edges
    html = auth_client.post(f"/p/{p.id}/node/{start.key}/delete").get_data(as_text=True)
    assert "Nie można usunąć" in html


def test_add_step_after_with_branch_label(auth_client):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    node = p.nodes[1]
    html = auth_client.get(f"/p/{p.id}/panel?node={node.key}&ask=next&slot=anulowanie").get_data(as_text=True)
    assert "→ anulowanie" in html
    log = (QuestionLog.query.filter_by(project_id=p.id, node_key=node.key, answer="")
           .order_by(QuestionLog.id.desc()).first())
    auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "option": len(log.options["options"]) - 1})
    assert any(e.label == "anulowanie" for e in p.edges)


def test_positions_saved_and_layout_reset(auth_client):
    p = new_project(auth_client)
    key = p.nodes[0].key
    auth_client.post(f"/p/{p.id}/positions", json={key: [10, 20], "bogus": "x"})
    assert (p.nodes[0].pos_x, p.nodes[0].pos_y) == (10, 20)
    auth_client.post(f"/p/{p.id}/layout")
    assert p.nodes[0].pos_x is None


def test_view_page_renders(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    assert 'id="map"' in html and re.search(r'hx-headers=.*X-CSRFToken', html)
