from app.ai.rules import next_question


def n(key, type, title, actor="System"):
    return {"key": key, "type": type, "title": title, "actor": actor, "inputs": [], "outputs": [], "data": {}}


def titles(q):
    return [s.title for o in q.options for s in o.steps]


def test_no_tile_repeats_the_current_step_or_its_path():
    graph = {"nodes": [n("s", "start", "Klient zgłasza", "Klient"), n("c", "screen", "Ekran potwierdzenia", "Klient"),
                       n("a", "automation", "Wysłanie powiadomienia e-mail")],
             "edges": [{"source": "s", "target": "c"}, {"source": "c", "target": "a"}]}
    q = next_question(graph, graph["nodes"][2], None, "quick", None)
    assert "Wysłanie powiadomienia e-mail" not in titles(q)
    assert "Ekran potwierdzenia" not in titles(q)  # stripped from the "Domknij proces" closer
    assert q.options[-1].label == "Koniec procesu"
