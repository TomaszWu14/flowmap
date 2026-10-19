from app.ai.templates import full_graph
from app.spec.derive import derive
from app.spec.readiness import readiness
from app.spec.schema import (
    Entity,
    Field,
    Integration,
    Notification,
    Proposal,
    Relation,
    Role,
    Screen,
    Spec,
    StateMachine,
    Status,
)


def codes(spec):
    return sorted(i["code"] for i in readiness(spec)["issues"])


def test_templates_reach_70_without_ai():
    for key, sentence in [("booking", "Klient chce umówić wizytę"), ("order", "Klient kupuje"),
                          ("service", "Klient zgłasza usterkę")]:
        assert readiness(derive(full_graph(key), {"name": key, "start_sentence": sentence}))["score"] >= 70, key


def test_each_rule():
    spec = Spec(
        entities=[Entity(key="e1", name="A", fields=[Field(key="f", name="x", type="enum")],
                         relations=[Relation(key="r", to_entity="brak")])],
        screens=[Screen(key="s1", name="S")], roles=[Role(key="ro", name="R")],
        states=[StateMachine(key="st", entity="e1", statuses=[Status(name="a")])],
        notifications=[Notification(key="n", trigger="t")], integrations=[Integration(key="i", name="I")],
        proposals=[Proposal(id="p", kind="other_note", summary="x")],
    )
    assert codes(spec) == ["bad_relation", "enum_without_values", "integration_without_error",
                           "no_identifier", "notification_without_recipient", "open_proposal",
                           "role_without_permissions", "screen_without_role", "states_without_initial_or_final"]
    assert readiness(Spec())["score"] == 100
    stale = Spec(
        entities=[Entity(
            key="e", name="A", stale=True,
            fields=[Field(key="i", name="id", is_identifier=True)]
        )]
    )
    assert codes(stale) == ["stale_item"]


def test_duplicate_items_lower_readiness():
    from app.spec.schema import Notification, Spec
    spec = Spec(notifications=[Notification(key=f"n{i}", trigger="Wysłanie e-mail", recipient_role="role:k")
                               for i in range(3)])
    dup = [i for i in readiness(spec)["issues"] if i["code"] == "duplicate_item"]
    assert [i["target_key"] for i in dup] == ["n1", "n2"]
