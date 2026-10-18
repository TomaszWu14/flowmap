import pytest
from pydantic import ValidationError

from app.spec.schema import FIELD_TYPES, Entity, Field, Spec, load_spec


def test_empty_spec_roundtrip():
    spec = Spec()
    data = spec.model_dump(mode="json")
    assert load_spec(data) == spec
    assert load_spec(None) == Spec()
    assert set(data) >= {"entities", "screens", "roles", "states", "notifications", "integrations", "nfr",
                         "stack", "proposals"}


def test_field_type_is_closed_list():
    assert "money" in FIELD_TYPES and len(FIELD_TYPES) == 13
    with pytest.raises(ValidationError):
        Field(key="f1", name="x", type="varchar")


def test_entity_defaults_and_source():
    e = Entity(key="entity:rezerwacja", name="Rezerwacja")
    assert e.source == "rules" and e.stale is False and e.fields == [] and e.relations == []


def test_load_spec_rejects_garbage():
    with pytest.raises(ValidationError):
        load_spec({"entities": [{"name": "bez klucza"}]})
