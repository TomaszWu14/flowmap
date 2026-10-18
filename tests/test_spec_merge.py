from app.spec.merge import merge
from app.spec.schema import Entity, Nfr, Proposal, Screen, Spec


def s(**kw):
    return Spec(**kw)


def test_first_merge_takes_derived():
    d = s(screens=[Screen(key="screen:a", name="A")])
    assert merge(None, d) == d


def test_rules_items_follow_map_and_disappearing_become_stale():
    cur = s(screens=[Screen(key="screen:a", name="Stary"), Screen(key="screen:b", name="B")])
    der = s(screens=[Screen(key="screen:a", name="Nowy"), Screen(key="screen:c", name="C")])
    out = merge(cur, der)
    by = {x.key: x for x in out.screens}
    assert by["screen:a"].name == "Nowy" and by["screen:b"].stale and by["screen:c"].name == "C"


def test_manual_and_ai_items_are_never_touched():
    cur = s(entities=[Entity(key="entity:r", name="Moja nazwa", source="manual")],
            nfr=[Nfr(key="nfr:x", text="od AI", source="ai")], stack="Flask",
            proposals=[Proposal(id="p1", kind="other_note", summary="x")])
    der = s(entities=[Entity(key="entity:r", name="Z mapy")])
    out = merge(cur, der)
    assert out.entities[0].name == "Moja nazwa" and out.entities[0].source == "manual"
    assert out.nfr[0].text == "od AI" and not out.nfr[0].stale
    assert out.stack == "Flask" and out.proposals[0].id == "p1"


def test_stale_comes_back_when_map_restores_it():
    cur = s(screens=[Screen(key="screen:b", name="B", stale=True)])
    out = merge(cur, s(screens=[Screen(key="screen:b", name="B")]))
    assert out.screens[0].stale is False


def test_merge_is_idempotent():
    der = s(screens=[Screen(key="screen:a", name="A")])
    once = merge(None, der)
    assert merge(once, der) == once
