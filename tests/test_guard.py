from app.ai.templates import TEMPLATES, full_graph
from app.flow.guard import check, report, score


def node(key, type="user_action", title=None, actor="Klient", **data):
    return {"key": key, "type": type, "title": title or key, "actor": actor, "inputs": [], "outputs": [],
            "description": "", "data": data}


def edge(a, b, label="", condition=""):
    return {"source": a, "target": b, "label": label, "condition": condition}


def codes(graph):
    return sorted(i["code"] for i in check(graph))


def test_complete_linear_process_scores_100():
    g = {"nodes": [node("s", "start"), node("a"), node("e", "end")], "edges": [edge("s", "a"), edge("a", "e")]}
    assert check(g) == [] and report(g)["score"] == 100


def test_missing_end_and_dead_end():
    g = {"nodes": [node("s", "start"), node("a")], "edges": [edge("s", "a")]}
    assert codes(g) == ["dead_end", "no_end"]
    assert [i["node_key"] for i in check(g) if i["code"] == "dead_end"] == ["a"]


def test_missing_start():
    g = {"nodes": [node("a"), node("e", "end")], "edges": [edge("a", "e")]}
    assert "no_start" in codes(g)


def test_decision_needs_two_exits_and_open_branch_reported():
    g = {"nodes": [node("s", "start"), node("d", "decision", branches=["tak", "nie"]), node("e", "end")],
         "edges": [edge("s", "d"), edge("d", "e", "tak")]}
    assert codes(g) == ["decision_exits", "open_branch"]


def test_missing_actor():
    g = {"nodes": [node("s", "start", actor=""), node("a", actor=""), node("e", "end", actor="")],
         "edges": [edge("s", "a"), edge("a", "e")]}
    assert codes(g) == ["missing_actor"]


def test_payment_and_integration_need_error_path():
    g = {"nodes": [node("s", "start"), node("p", "user_action", "Płatność kartą"), node("i", "integration", "SMS"),
                   node("e", "end")],
         "edges": [edge("s", "p"), edge("p", "i"), edge("i", "e")]}
    assert codes(g) == ["missing_error_path", "missing_error_path"]
    g["edges"].append(edge("p", "e", "brak płatności", "error"))
    g["edges"].append(edge("i", "e", "błąd"))
    assert codes(g) == []


def test_error_screen_does_not_need_its_own_error_path():
    g = {"nodes": [node("s", "start"), node("x", "screen", "Płatność nieudana"), node("e", "end")],
         "edges": [edge("s", "x"), edge("x", "e")]}
    assert codes(g) == []


def test_unreachable_node():
    g = {"nodes": [node("s", "start"), node("e", "end"), node("lost"), node("e2", "end")],
         "edges": [edge("s", "e"), edge("lost", "e2")]}
    assert codes(g) == ["unreachable", "unreachable"]


def test_score_is_clamped_and_weighted():
    assert score([]) == 100
    assert score([{"code": "no_end"}] * 10) == 0
    assert score([{"code": "missing_actor"}]) == 97


def test_all_builtin_templates_are_complete():
    for key in TEMPLATES:
        assert report(full_graph(key))["score"] == 100, key
