from app.ai.templates import TEMPLATES, full_graph
from app.design.derive import main_path, use_cases
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.schema import Role, Spec, UseCase

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def booking():
    return {u.key: u for u in use_cases(full_graph("booking"), META)}


def test_main_path_takes_positive_answers_and_skips_errors():
    assert main_path(full_graph("booking")) == ["start", "service", "slot", "free", "contact", "prepay", "payment",
                                                "confirm", "wait", "remind", "end"]


def test_client_use_case_with_alternatives_and_include():
    u = booking()["uc:klient"]
    assert (u.name, u.actor, u.goal) == ("Klient chce umówić wizytę", "role:klient", "Wizyta odbyta")
    assert u.main == ["Wybór usługi", "Wybór terminu i specjalisty", "Klient podaje dane kontaktowe", "Płatność online"]
    alts = {a.condition: a.steps for a in u.alternatives}
    assert alts["Czy termin jest wolny? — nie"] == ["wraca do: Wybór terminu i specjalisty"]
    assert alts["Czy usługa wymaga przedpłaty? — nie"] == ["dalej: Wysłanie potwierdzenia rezerwacji"]
    assert alts["Płatność online — brak płatności"] == ["Płatność nieudana — spróbuj ponownie",
                                                       "wraca do: Płatność online"]
    assert u.includes == ["uc:system"]


def test_system_use_case_is_included_not_acted():
    s = booking()["uc:system"]
    assert s.actor == "" and s.main == ["Wysłanie potwierdzenia rezerwacji", "Przypomnienie dzień przed wizytą"]


def test_every_template_gets_use_cases_without_role_or_goal_warnings():
    for key in TEMPLATES:
        spec = derive(full_graph(key), {"name": key, "start_sentence": "Start"})
        assert spec.use_cases, key
        bad = [i for i in lint(spec) if i["code"] in ("role_without_use_case", "use_case_without_goal")]
        assert not bad, (key, bad)


def test_use_case_guard():
    spec = Spec(roles=[Role(key="role:k", name="Kierownik"), Role(key="role:administrator", name="Administrator")],
                use_cases=[UseCase(key="uc:a", name="A", actor="role:x"), UseCase(key="uc:s", name="S", goal="g")])
    codes = {(i["code"], i["target_key"]) for i in lint(spec)}
    assert ("role_without_use_case", "role:k") in codes
    assert ("role_without_use_case", "role:administrator") not in codes
    assert ("use_case_without_goal", "uc:a") in codes and ("use_case_without_alternative", "uc:a") in codes
    assert ("use_case_without_alternative", "uc:s") not in codes  # included (system) use case
