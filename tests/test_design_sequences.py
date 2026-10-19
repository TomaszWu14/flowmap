from app.ai.templates import TEMPLATES, full_graph
from app.design.derive import sequences
from app.spec.derive import derive

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def seq():
    return sequences(full_graph("booking"), META)[0]


def test_main_sequence_participants_and_messages():
    s = seq()
    assert s.key == "seq:main" and s.name == "Ścieżka główna: Klient chce umówić wizytę"
    assert s.participants == ["Klient", "Płatność online", "System"]
    msgs = [(m.source, m.target, m.kind, m.text) for m in s.messages]
    assert ("Klient", "Klient", "call", "Wybór usługi") in msgs
    assert ("Klient", "Płatność online", "call", "Kwota, Metoda płatności") in msgs
    assert ("Płatność online", "Klient", "reply", "Status płatności") in msgs
    assert ("Płatność online", "Klient", "error", "brak płatności") in msgs
    assert ("System", "Klient", "async", "Wysłanie potwierdzenia rezerwacji") in msgs
    kinds = [m.kind for m in s.messages]
    assert kinds.index("reply") + 1 == kinds.index("error")  # error right after the reply → alt block


def test_every_template_has_a_sequence_without_idle_participants():
    for key in TEMPLATES:
        spec = derive(full_graph(key), {"name": key, "start_sentence": "Start"})
        assert spec.sequences, key
        used = {p for m in spec.sequences[0].messages for p in (m.source, m.target)}
        assert set(spec.sequences[0].participants) == used, key
