from app.ai.templates import TEMPLATES, full_graph
from app.design.derive import sequences
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.schema import Integration, Message, Sequence, Spec

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


def test_sequence_guard():
    spec = Spec(integrations=[Integration(key="i", name="Bank")],
                sequences=[Sequence(key="s", name="S", participants=["A", "Bank", "Nikt"],
                                    messages=[Message(source="A", target="Bank", text="przelew")])])
    codes = {(i["code"], i["target_key"]) for i in lint(spec)}
    assert ("integration_without_error_message", "s") in codes and ("idle_participant", "s") in codes
    spec.sequences[0].messages.append(Message(source="Bank", target="A", text="odmowa", kind="error"))
    spec.sequences[0].participants.remove("Nikt")
    assert not [c for c in lint(spec) if c["target_key"] == "s"]


def test_sequence_diagram_mermaid():
    from app.design.uml import sequence_diagram
    spec = derive(full_graph("booking"), META)
    out = sequence_diagram(spec.sequences[0], spec)
    assert out.startswith("sequenceDiagram\n")
    assert "actor P0 as Klient" in out and "participant P1 as Płatność online" in out
    assert "P0->>P1: Kwota, Metoda płatności" in out and "P1-->>P0: Status płatności" in out
    assert "alt powodzenie" in out and "else brak płatności" in out and "P1--xP0: brak płatności" in out
    assert "P2-)P0: Wysłanie potwierdzenia rezerwacji" in out


def test_sequence_in_uml_md_and_markdown_export():
    from app.design.uml import uml_md
    from app.export.builders import to_markdown
    assert "## Sekwencje" in uml_md(META, derive(full_graph("booking"), META))
    md = to_markdown(META, full_graph("booking"))
    assert "### Sekwencja (ścieżka główna)" in md and "Klient → Płatność online: Kwota, Metoda płatności" in md
