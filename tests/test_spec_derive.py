from app.ai.templates import full_graph
from app.spec.derive import derive, guess_field_type, slug

META = {"name": "Rezerwacja wizyty", "start_sentence": "Klient chce umówić wizytę w salonie"}


def test_guess_field_type():
    assert guess_field_type("E-mail") == "email"
    assert guess_field_type("Telefon") == "phone"
    assert guess_field_type("Data") == "date"
    assert guess_field_type("Godzina") == "datetime"
    assert guess_field_type("Kwota") == "money"
    assert guess_field_type("Ilość") == "integer"
    assert guess_field_type("Zgoda RODO") == "boolean"
    assert guess_field_type("Zdjęcia") == "file"
    assert guess_field_type("Opis problemu") == "long_text"
    assert guess_field_type("Imię i nazwisko") == "text"


def test_slug():
    assert slug("Zgoda RODO") == "zgoda-rodo" and slug("Ąę Śż") == "ae-sz"


def test_derive_booking():
    spec = derive(full_graph("booking"), META)
    names = [e.name for e in spec.entities]
    assert names[0] == "Rezerwacja" and "Klient" in names
    main = spec.entities[0]
    assert main.key == "entity:rezerwacja"
    assert any(f.is_identifier for f in main.fields)
    klient = next(e for e in spec.entities if e.name == "Klient")
    assert {f.name: f.type for f in klient.fields}["E-mail"] == "email"
    assert any(r.to_entity == "entity:rezerwacja" and r.kind == "1-n" for r in klient.relations)
    assert {s.key for s in spec.screens} == {"screen:service", "screen:slot", "screen:pay_retry"}
    roles = {r.name: r for r in spec.roles}
    assert set(roles) == {"Klient", "Administrator"}
    assert roles["Klient"].permissions["entity:rezerwacja"] == {"read": "own", "create": "own", "update": "own",
                                                                "delete": "none"}
    sm = spec.states[0]
    assert sm.entity == "entity:rezerwacja" and sm.statuses[0].initial and sm.statuses[-1].final
    assert [i.key for i in spec.integrations] == ["integration:payment"]
    assert {n.key for n in spec.notifications} >= {"notification:confirm", "notification:remind"}
    assert any(n.category == "privacy" for n in spec.nfr)
    assert all(item.source == "rules" for item in spec.entities + spec.screens)


def test_derive_is_deterministic():
    g = full_graph("order")
    assert derive(g, META).model_dump() == derive(g, META).model_dump()


def test_derive_service_staff_role_permissions():
    spec = derive(full_graph("service"), {"name": "Serwis", "start_sentence": "Klient zgłasza usterkę"})
    roles = {r.name: r for r in spec.roles}
    main = spec.entities[0].key
    assert roles["Serwisant"].permissions[main] == {"read": "all", "create": "none", "update": "all",
                                                    "delete": "none"}
    assert roles["Administrator"].permissions[main]["delete"] == "all"
