from app.flow.lanes import assign, lane_icon, lanes_info, update
from app.models import Project
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def n(key, type="user_action", actor=""):
    return {"key": key, "type": type, "title": key, "actor": actor, "data": {}}


def e(a, b):
    return {"source": a, "target": b, "label": "", "condition": ""}


GRAPH = {"nodes": [n("s", "start", "Klient"), n("a", actor="Klient"), n("d", "decision"), n("b", actor="Magazynier"),
                   n("x"), n("end", "end")],
         "edges": [e("s", "a"), e("a", "d"), e("d", "b"), e("b", "end"), e("d", "x")]}


def test_roleless_events_and_gateways_inherit_a_neighbours_lane_steps_do_not():
    lanes = assign(GRAPH)
    assert lanes["d"] == "Klient" and lanes["end"] == "Magazynier" and lanes["x"] == ""


def test_order_icons_handoffs_and_unassigned_last():
    info = lanes_info(GRAPH)
    assert info["order"] == ["Klient", "Magazynier", ""]
    assert info["icons"] == {"Klient": "user", "Magazynier": "warehouse", "": "user"}
    assert info["handoffs"] == 2  # d -> b (Klient -> Magazynier), d -> x (-> no role)


def test_saved_order_and_icon_win():
    display = update(None, "Magazynier", move=-1, order=["Klient", "Magazynier", ""])
    display = update(display, "Klient", icon="briefcase", order=["Magazynier", "Klient", ""])
    info = lanes_info(GRAPH, display)
    assert info["order"][:2] == ["Magazynier", "Klient"] and info["icons"]["Klient"] == "briefcase"


def test_lane_icon_rules():
    assert [lane_icon(r) for r in ("System", "SAP", "Kierowca", "Kontroler magazynu", "Księgowa")] == \
        ["server", "server", "truck", "warehouse", "briefcase"]


def test_graph_json_has_lanes_and_lane_route_saves(auth_client):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    data = auth_client.get(f"/p/{p.id}/graph.json").get_json()
    assert data["lanes"]["order"] and all("lane" in node for node in data["nodes"])
    role = data["lanes"]["order"][0]
    assert auth_client.post(f"/p/{p.id}/lanes", json={"role": role, "icon": "truck"}).status_code == 200
    assert Project.query.get(p.id).display["lanes"]["icons"][role] == "truck"
    assert auth_client.post(f"/p/{p.id}/lanes", json={"role": role, "icon": "zła"}).status_code == 400
    assert auth_client.post(f"/p/{p.id}/lanes", json={"role": "Nie ma", "move": 1}).status_code == 400
