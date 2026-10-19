from app.models import Project, QuestionLog
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def pending_log(client, p):
    client.get(f"/p/{p.id}/panel")
    return QuestionLog.query.filter_by(project_id=p.id, answer="", kind="next").order_by(QuestionLog.id.desc()).first()


def titles(p):
    return [n.title for n in Project.query.get(p.id).nodes]


def test_other_with_several_lines_adds_a_chain(auth_client):
    p = new_project(auth_client, template="none")
    log = pending_log(auth_client, p)
    auth_client.post(f"/p/{p.id}/answer", data={
        "log_id": log.id, "other": "1", "type": "user_action",
        "text": "Klient wypełnia formularz\nCzy dane są poprawne?\nSystem zapisuje wizytę\nKoniec"})
    project = Project.query.get(p.id)
    by_title = {n.title: n for n in project.nodes}
    assert {"Klient wypełnia formularz", "Czy dane są poprawne?", "System zapisuje wizytę", "Koniec"} <= set(by_title)
    decision = by_title["Czy dane są poprawne?"]
    assert decision.type == "decision" and by_title["Koniec"].type == "end"
    out = [(e.label, e.target.title) for e in project.edges if e.source_id == decision.id]
    assert out == [("tak", "System zapisuje wizytę")]  # "nie" stays an open question


def test_single_line_other_is_one_step(auth_client):
    p = new_project(auth_client, template="none")
    log = pending_log(auth_client, p)
    before = len(titles(p))
    auth_client.post(f"/p/{p.id}/answer", data={"log_id": log.id, "other": "1", "type": "screen",
                                                "text": "Klient płaci. System wysyła potwierdzenie."})
    assert len(titles(p)) == before + 1


def test_insert_step_between_and_undo(auth_client):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    project = Project.query.get(p.id)
    edge = project.edges[0]
    src, dst, label = edge.source.title, edge.target.title, edge.label
    r = auth_client.post(f"/p/{p.id}/edge/{edge.id}/insert", data={"title": "Weryfikacja danych", "type": "automation"})
    assert r.status_code == 200
    project = Project.query.get(p.id)
    new = next(n for n in project.nodes if n.title == "Weryfikacja danych")
    pairs = {(e.source.title, e.target.title, e.label) for e in project.edges}
    assert (src, new.title, label) in pairs and (new.title, dst, "") in pairs and (src, dst, label) not in pairs
    auth_client.post(f"/p/{p.id}/undo")
    assert "Weryfikacja danych" not in titles(p)
    assert auth_client.post(f"/p/{p.id}/edge/999999/insert", data={"title": "X"}).status_code == 404


def test_guard_panel_lists_open_questions(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/guard").get_data(as_text=True)
    assert "Otwarte pytania (1)" in html and "co dalej" in html and "Odpowiedz" in html


def test_flow_player_is_loaded_on_every_map(auth_client, client):
    p = new_project(auth_client)
    assert "player.js" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)
    auth_client.post(f"/p/{p.id}/udostepnianie/link")
    token = Project.query.get(p.id).share_token
    assert "player.js" in auth_client.get(f"/s/{token}").get_data(as_text=True)
    assert "player.js" in auth_client.get("/przyklad").get_data(as_text=True)
