from app.ai.templates import full_graph
from app.design.uml import class_diagram
from app.spec.derive import derive
from app.spec.schema import Entity, Field, Relation, Spec

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def test_class_diagram_from_derived_spec():
    spec = derive(full_graph("booking"), META)
    out = class_diagram(spec)
    assert out.startswith("classDiagram\n")
    assert f'class E0["{spec.entities[0].name}"]' in out
    assert "+integer id" in out


def test_relation_multiplicities_and_escaping():
    spec = Spec(entities=[
        Entity(key="entity:a", name='A "x"', fields=[Field(key="f", name="nazwa (pełna) {x}", type="text")],
               relations=[Relation(key="r1", to_entity="entity:b", kind="1-n", label="ma"),
                          Relation(key="r2", to_entity="entity:b", kind="n-n"),
                          Relation(key="r3", to_entity="entity:b", kind="1-1"),
                          Relation(key="r4", to_entity="entity:zniknęła", kind="1-n")]),
        Entity(key="entity:b", name="B")])
    out = class_diagram(spec)
    assert 'E0 "1" --> "*" E1 : ma' in out
    assert 'E0 "*" -- "*" E1 : n-n' in out
    assert 'E0 "1" -- "1" E1 : 1-1' in out
    assert "zniknęła" not in out
    assert 'class E0["A #quot;x#quot;"]' in out  # cudzysłów w nazwie zneutralizowany
    assert "(" not in out and "{x}" not in out  # nawiasy robiłyby z pola metodę / psuły blok


def test_empty_spec():
    assert class_diagram(Spec()) == "classDiagram\n"
