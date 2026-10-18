from app.models import Project
from app.spec.forms import item_from_form
from app.spec.schema import load_spec
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


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
