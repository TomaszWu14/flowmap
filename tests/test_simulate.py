from app.ai.templates import full_graph
from app.flow.simulate import simulation_state
from tests.test_flow import play_to_end
from tests.test_projects import new_project


def test_walk_booking_happy_path():
    g = full_graph("booking")
    s = simulation_state(g, "Klient", [])
    assert s["node"]["key"] == "start" and not s["finished"]
    path = ["start", "service", "slot", "free", "contact", "prepay", "confirm", "wait", "remind", "end"]
    s = simulation_state(g, "Klient", path)
    assert s["finished"] and not s["dead_end"]
    assert s["summary"] == {"steps": 10, "role_steps": 5, "screens": 2, "dead_ends": [], "reached_end": True}


def test_decision_offers_labelled_choices():
    s = simulation_state(full_graph("booking"), "Klient", ["start", "service", "slot", "free"])
    assert sorted(c["label"] for c in s["choices"]) == ["nie", "tak"]


def test_invalid_hops_are_cut():
    s = simulation_state(full_graph("booking"), "Klient", ["start", "end"])
    assert s["path"] == ["start"]


def test_dead_end_detected():
    g = full_graph("booking")
    g["edges"] = [e for e in g["edges"] if e["source"] != "remind"]
    s = simulation_state(g, "Klient", ["start", "service", "slot", "free", "contact", "prepay", "confirm",
                                       "wait", "remind"])
    assert s["finished"] and s["dead_end"]
    assert [n["key"] for n in s["summary"]["dead_ends"]] == ["remind"]


def test_simulation_pages(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/symulacja").get_data(as_text=True)
    assert "Z czyjej perspektywy" in html and "Klient" in html
    html = auth_client.get(f"/p/{p.id}/symulacja?role=Klient").get_data(as_text=True)
    assert p.start_sentence in html
    # follow the first choice until the end
    path = [p.nodes[0].key]
    for _ in range(40):
        from app.flow.simulate import simulation_state as sim
        state = sim(p.graph(), "Klient", path)
        if state["finished"]:
            break
        path.append(state["choices"][0]["target"])
    html = auth_client.get(f"/p/{p.id}/symulacja?role=Klient&path={','.join(path)}").get_data(as_text=True)
    assert "Podsumowanie" in html and "ekranów" in html
