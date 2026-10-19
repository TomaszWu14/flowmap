from app.ai.templates import TEMPLATES, full_graph
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.schema import Spec, StateMachine, Status, Transition

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def test_transitions_carry_gateway_conditions_and_no_self_loops():
    sm = derive(full_graph("booking"), META).states[0]
    conds = {(t.from_status, t.to_status): t.condition for t in sm.transitions}
    assert conds[("nowy", "zatwierdzony")] == "Czy termin jest wolny? — tak"
    assert all(t.from_status != t.to_status for t in sm.transitions)
    # "termin zajęty" goes back to choosing a slot and "bez przedpłaty" skips a step — neither rejects the booking
    assert "odrzucony" not in {s.name for s in sm.statuses}


def test_negative_answer_that_leaves_the_happy_path_rejects():
    sm = derive(full_graph("service"), {"name": "Serwis", "start_sentence": "S"}).states[0]
    conds = {t.condition: (t.from_status, t.to_status) for t in sm.transitions}
    assert conds["Czy klient akceptuje wycenę? — nie"][1] == "odrzucony"
    assert "Czy naprawa gwarancyjna? — nie" not in conds  # goes through a quote and back to the repair
    assert next(s for s in sm.statuses if s.name == "odrzucony").final


def test_state_guard():
    sm = StateMachine(key="st", entity="e", statuses=[Status(name="a", initial=True), Status(name="b"),
                                                      Status(name="c", final=True), Status(name="d")],
                      transitions=[Transition(from_status="a", to_status="b")])
    codes = {(i["code"], i["message"].split("„")[1].split("”")[0]) for i in lint(Spec(states=[sm]))}
    assert ("dead_end_status", "b") in codes  # reachable, not final, no exit
    assert ("unreachable_status", "c") in codes and ("unreachable_status", "d") in codes
    assert not any(c == ("unreachable_status", "a") for c in codes)


def test_templates_have_no_state_warnings():
    for key in TEMPLATES:
        spec = derive(full_graph(key), {"name": key, "start_sentence": "S"})
        bad = [i for i in lint(spec) if i["code"] in ("unreachable_status", "dead_end_status")]
        assert not bad, (key, bad)


def test_rules_from_gateways():
    from app.design.derive import rules
    r = {x.key: x for x in rules(full_graph("booking"))}["rule:free"]
    assert r.name == "Czy termin jest wolny?" and r.node_key == "free"
    assert [(w.condition, w.result) for w in r.rows] == [("tak", "Klient podaje dane kontaktowe"),
                                                         ("nie", "Wybór terminu i specjalisty")]


def test_rule_guard_gap_and_overlap():
    from app.spec.schema import Rule, RuleRow

    def codes(rows):
        rule = Rule(key="r", name="R", rows=[RuleRow(condition=c, result="x") for c in rows])
        return {i["code"] for i in lint(Spec(rules=[rule]))}
    assert codes(["tak", "nie"]) == set()
    assert codes(["kwota > 1000", "inaczej"]) == set()
    assert "rule_gap" in codes(["kwota > 1000", "kwota < 100"])
    assert "rule_overlap" in codes(["VIP", "vip ", "inaczej"])


def test_state_diagram_and_documents():
    from app.design.uml import state_diagram, uml_md
    from app.export.builders import to_markdown
    from app.spec.package import data_model_md
    spec = derive(full_graph("booking"), META)
    out = state_diagram(spec.states[0], spec)
    assert out.startswith("stateDiagram-v2\n") and "S0 --> S1 : Czy termin jest wolny? — tak" in out
    assert "S0 --> S1 : Czy termin jest wolny? — tak" in data_model_md(spec)
    md = uml_md(META, spec)
    assert "## Stany" in md and "## Reguły biznesowe" in md and "| tak | Klient podaje dane kontaktowe |" in md
    assert "### Reguły decyzyjne" in to_markdown(META, full_graph("booking"))
