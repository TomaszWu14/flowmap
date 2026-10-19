from app.design.lint import lint
from app.spec.readiness import readiness
from app.spec.schema import Entity, Field, Relation, Spec


def ent(key, name, relations=(), fields=()):
    return Entity(key=key, name=name, relations=list(relations),
                  fields=[Field(key="id", name="id", type="integer", is_identifier=True), *fields])


def codes(spec):
    return [(i["code"], i["target_key"]) for i in lint(spec)]


def test_nn_without_join_entity():
    spec = Spec(entities=[ent("entity:a", "A", [Relation(key="r", to_entity="entity:b", kind="n-n")]),
                          ent("entity:b", "B")])
    assert ("nn_without_join", "entity:a") in codes(spec)
    joined = Spec(entities=[*spec.entities, ent("entity:ab", "AB", [Relation(key="x", to_entity="entity:a"),
                                                                     Relation(key="y", to_entity="entity:b")])])
    assert ("nn_without_join", "entity:a") not in codes(joined)


def test_island_entity_only_when_more_than_one():
    assert codes(Spec(entities=[ent("entity:a", "A")])) == []
    spec = Spec(entities=[ent("entity:a", "A", [Relation(key="r", to_entity="entity:b")]), ent("entity:b", "B"),
                          ent("entity:c", "C")])
    assert codes(spec) == [("island_entity", "entity:c")]


def test_reference_field_without_relation():
    ref = Field(key="k", name="klient", type="reference", ref_entity="entity:b")
    spec = Spec(entities=[ent("entity:a", "A", fields=[ref]), ent("entity:b", "B")])
    assert ("reference_without_relation", "entity:a") in codes(spec)
    spec.entities[1].relations.append(Relation(key="r", to_entity="entity:a"))
    assert ("reference_without_relation", "entity:a") not in codes(spec)


def test_every_issue_explains_why_and_counts_in_readiness():
    spec = Spec(entities=[ent("entity:a", "A"), ent("entity:b", "B")])
    issues = lint(spec)
    assert issues and all(i["why"] and i["message"] for i in issues)
    ready = readiness(spec)
    assert any(i["code"] == "island_entity" for i in ready["issues"])
    assert ready["score"] == 100 - 2 * 3
