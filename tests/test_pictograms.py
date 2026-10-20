import pytest

from app.ai.templates import TEMPLATES, full_graph
from app.flow.pictograms import GROUPS, PICTOGRAMS, RULES, detect, icon_for, svg_bodies


@pytest.mark.parametrize("title,type_,expected", [
    ("Wysłanie powiadomienia e-mail", "automation", "mail"),
    ("Powiadomienie klienta o zakończeniu", "automation", "mail"),
    ("Powiadomienie SMS o odbiorze", "automation", "message-square"),
    ("Klient otrzymuje e-mail z potwierdzeniem", "user_action", "mail-open"),
    ("Pracownik wprowadza dane do systemu", "user_action", "keyboard"),
    ("Magazynier wpisuje ilość ręcznie", "user_action", "keyboard"),
    ("Skanowanie kodu kreskowego palety", "user_action", "scan-barcode"),
    ("Drukuje etykietę wysyłkową", "user_action", "printer"),
    ("Kierownik zatwierdza wniosek", "user_action", "signature"),
    ("Weryfikacja zgłoszenia", "user_action", "clipboard-check"),
    ("Klient dzwoni na infolinię", "user_action", "phone"),
    ("Płatność online", "integration", "credit-card"),
    ("Wystawienie faktury", "automation", "receipt"),
    ("Wybór terminu i specjalisty", "screen", "calendar"),
    ("Kurier odbiera przesyłkę", "user_action", "truck"),
    ("Kompletacja zamówienia w magazynie", "user_action", "package"),
    ("Oczekiwanie na odpowiedź", "wait", "timer"),
    ("Zapis zamówienia w SAP", "automation", "server"),
    ("Formularz zgłoszenia", "screen", "monitor"),
    ("Naprawa urządzenia", "user_action", "user"),
    ("Rejestracja zgłoszenia i nadanie numeru", "automation", "cog"),
])
def test_detect(title, type_, expected):
    assert detect(title, type_) == expected


def test_gateways_have_no_icon_and_events_keep_theirs():
    assert detect("Czy wysłać e-mail?", "decision") is None
    assert detect("Wysłano e-mail", "end") == "square" and detect("Klient pisze e-mail", "start") == "play"


def test_manual_choice_wins_and_unknown_is_ignored():
    node = {"type": "user_action", "title": "Wysłanie e-maila", "description": "", "data": {"icon": "phone"}}
    assert icon_for(node) == "phone"
    node["data"]["icon"] = "nie-ma-takiej"
    assert icon_for(node) == "mail"


def test_every_pictogram_has_an_svg_and_rules_point_to_known_keys():
    assert set(PICTOGRAMS) <= set(svg_bodies())
    assert {key for key, _ in RULES} <= set(PICTOGRAMS)


def test_every_pickable_pictogram_has_a_coloured_group():
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "app.css").read_text(encoding="utf-8")
    assert set(GROUPS) == set(PICTOGRAMS) - {"play", "square"}  # start/end are not in the picker
    for group in set(GROUPS.values()):
        assert f".picto-opt.g-{group} {{ --g:" in css, group


def test_builtin_templates_get_varied_icons():
    for name in TEMPLATES:
        icons = {icon_for(n) for n in full_graph(name)["nodes"]}
        assert len(icons - {None}) >= 4, (name, icons)


def test_edit_sets_and_clears_icon(auth_client):
    from app.models import Project
    from tests.test_flow import answer_first_tile
    from tests.test_projects import new_project
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    node = next(n for n in Project.query.get(p.id).nodes if n.type not in ("start", "decision"))
    form = {"title": node.title, "type": node.type, "actor": node.actor or "", "icon": "truck"}
    auth_client.post(f"/p/{p.id}/node/{node.key}/edit", data=form)
    graph = auth_client.get(f"/p/{p.id}/graph.json").get_json()
    assert next(n for n in graph["nodes"] if n["key"] == node.key)["icon"] == "truck"
    html = auth_client.get(f"/p/{p.id}/panel?node={node.key}").get_data(as_text=True)
    assert 'value="truck" checked' in html and "picto-picker" in html and "picto-opt g-log" in html
    auth_client.post(f"/p/{p.id}/node/{node.key}/edit", data=form | {"icon": ""})
    assert Project.query.get(p.id).node_by_key(node.key).data.get("icon") is None
