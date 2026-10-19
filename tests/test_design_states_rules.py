from app.ai.templates import TEMPLATES, full_graph
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.schema import Spec, StateMachine, Status, Transition

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def test_transitions_carry_gateway_conditions_and_no_self_loops():
    sm = derive(full_graph("booking"), META).states[0]
    conds = {(t.from_status, t.to_status): t.condition for t in sm.transitions}
    assert conds[("nowy", "zatwierdzony")] == "Czy termin jest wolny? — tak"
    assert conds[("nowy", "odrzucony")] == "Czy termin jest wolny? — nie"
    assert all(t.from_status != t.to_status for t in sm.transitions)
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
