from app.models import Project
from app.spec.forms import form_text, item_from_form
from app.spec.schema import SECTIONS, load_spec
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project

SAMPLE_FORM = {
    "entities": {"name": "E", "description": "d", "fields": "pole | text | t | | | | t", "relations": ""},
    "screens": {"name": "S", "role": "role:x", "fields": "pole | text | ", "actions": "zrob"},
    "roles": {"name": "R", "description": "d", "permissions": "entity:x | all | own | none | none"},
    "states": {"entity": "entity:x", "statuses": "nowy | start\nkoniec | koniec",
               "transitions": "nowy | koniec"},
    "notifications": {"trigger": "t", "channel": "sms", "recipient_role": "role:x", "summary": "s"},
    "integrations": {"name": "I", "direction": "in", "data": "a, b", "on_error": "retry"},
    "nfr": {"category": "performance", "text": "t"},
    "use_cases": {"name": "U", "actor": "role:x", "goal": "g", "main": "a\nb",
                  "alternatives": "brak danych | popraw; wróć", "includes": "uc:system"},
}


def spec_of(p):
    return load_spec(Project.query.get(p.id).spec)


def test_parse_entity_form():
    e = item_from_form("entities", {"name": "Wizyta", "description": "",
                                    "fields": "id | integer | t | | | | t\nKwota | money | t | >0 | | | n",
                                    "relations": "entity:klient | 1-n | klient"}, None)
    assert e.source == "manual" and [f.type for f in e.fields] == ["integer", "money"] and e.fields[0].is_identifier
    assert e.relations[0].kind == "1-n"


def test_parse_errors_are_polish():
    import pytest
    with pytest.raises(ValueError, match="nieznany typ"):
        item_from_form("entities", {"name": "X", "fields": "a | varchar", "relations": ""}, None)


def test_edit_add_delete_and_survive_map(auth_client):
    p = new_project(auth_client)
    key = spec_of(p).entities[0].key
    r = auth_client.post(f"/p/{p.id}/specyfikacja/entities/{key}",
                         data={"name": "Wizyta", "description": "", "fields": "id | integer | t | | | | t",
                               "relations": ""})
    assert r.status_code == 200 and "Wizyta" in r.get_data(as_text=True)
    answer_first_tile(auth_client, p)
    assert spec_of(p).entities[0].name == "Wizyta" and spec_of(p).entities[0].source == "manual"
    auth_client.post(f"/p/{p.id}/specyfikacja/nfr/nowy", data={"category": "performance", "text": "< 1 s"})
    assert any(n.text == "< 1 s" and n.source == "manual" for n in spec_of(p).nfr)
    nk = next(n.key for n in spec_of(p).nfr if n.text == "< 1 s")
    auth_client.post(f"/p/{p.id}/specyfikacja/nfr/{nk}/usun")
    assert not any(n.key == nk for n in spec_of(p).nfr)
    auth_client.post(f"/p/{p.id}/undo")  # spec edits are versioned too
    assert any(n.key == nk for n in spec_of(p).nfr)


def test_stale_keep_turns_manual(auth_client, db):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    screen = spec_of(p).screens[0]
    node = Project.query.get(p.id).node_by_key(screen.node_key)
    auth_client.post(f"/p/{p.id}/node/{node.key}/delete")
    s = next(x for x in spec_of(p).screens if x.key == screen.key)
    assert s.stale
    auth_client.post(f"/p/{p.id}/specyfikacja/screens/{screen.key}/zachowaj")
    s = next(x for x in spec_of(p).screens if x.key == screen.key)
    assert not s.stale and s.source == "manual"


def test_readiness_shown_and_viewer_cannot_edit(team):  # noqa: F811
    p = team["project"]
    html = team["owner"].get(f"/p/{p.id}/specyfikacja").get_data(as_text=True)
    assert "Gotowość" in html
    key = load_spec(Project.query.get(p.id).spec).entities[0].key
    assert team["viewer"].post(f"/p/{p.id}/specyfikacja/entities/{key}", data={"name": "X"}).status_code == 403


def test_wrong_section_for_key_aborts_404(auth_client):
    p = new_project(auth_client)
    spec = spec_of(p)
    entity_key = spec.entities[0].key
    # Try to access entity key in wrong section (screens)
    r = auth_client.post(f"/p/{p.id}/specyfikacja/screens/{entity_key}",
                         data={"name": "X", "role": "test", "fields": "", "actions": ""})
    assert r.status_code == 404
    # Verify no screen was created with that key
    spec_after = spec_of(p)
    assert not any(s.key == entity_key for s in spec_after.screens)


def test_field_keys_are_unique_with_index(auth_client):
    e = item_from_form("entities", {"name": "A", "description": "",
                                    "fields": "x | text\nx | text", "relations": ""}, None)
    assert len(e.fields) == 2
    assert e.fields[0].key != e.fields[1].key
    assert e.fields[0].key == "field:x-0"
    assert e.fields[1].key == "field:x-1"


def test_form_round_trip_every_section():
    for section in SECTIONS:
        item = item_from_form(section, SAMPLE_FORM[section], None)
        again = item_from_form(section, form_text(section, item), item)
        assert again == item, section


def test_delete_rules_item_stays_deleted_after_map_refresh(auth_client):
    p = new_project(auth_client)
    entity = spec_of(p).entities[0]
    assert entity.source == "rules"
    auth_client.post(f"/p/{p.id}/specyfikacja/entities/{entity.key}/usun")
    answer_first_tile(auth_client, p)  # map change re-derives the spec
    assert not any(e.key == entity.key for e in spec_of(p).entities)
    assert entity.key in spec_of(p).dismissed


def test_delete_unknown_key_is_404(auth_client):
    p = new_project(auth_client)
    assert auth_client.post(f"/p/{p.id}/specyfikacja/nfr/nfr:brak/usun").status_code == 404


def test_role_table_shows_update_permission(auth_client):
    # p.update in Jinja resolves to dict.update, not the "update" key
    p = new_project(auth_client)
    key = spec_of(p).roles[0].key
    auth_client.post(f"/p/{p.id}/specyfikacja/roles/{key}",
                     data={"name": "R", "description": "", "permissions": "entity:x | none | none | own | none"})
    html = auth_client.get(f"/p/{p.id}/specyfikacja?sekcja=roles").get_data(as_text=True)
    assert "tylko swoje" in html
