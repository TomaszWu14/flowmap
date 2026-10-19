from app.ai.templates import full_graph
from app.design.trace import trace_issues, trace_rows
from app.spec.derive import derive

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def booking():
    g = full_graph("booking")
    return g, derive(g, META)


def test_trace_rows():
    g, spec = booking()
    rows = {r["node_key"]: r for r in trace_rows(g, spec)}
    assert list(rows) == ["service", "slot", "contact", "payment", "confirm", "pay_retry", "remind"]
    assert rows["service"]["realized_by"] == ["Ekran: Wybór usługi"] and rows["service"]["tests"] == [1, 2, 3]
    assert rows["payment"]["realized_by"] == ["Integracja: Płatność online"] and rows["payment"]["tests"] == [1, 2]
    assert rows["confirm"]["realized_by"] == ["Powiadomienie: Wysłanie potwierdzenia rezerwacji"]
    assert rows["pay_retry"]["tests"] == [2]
    assert rows["service"]["use_case"] == "Klient chce umówić wizytę"
    assert rows["confirm"]["use_case"] == "System: kroki automatyczne"


def test_trace_issues_and_screen_matched_by_name():
    g, spec = booking()
    codes = {(i["code"], i["target_key"]) for i in trace_issues(g, spec)}
    assert codes == {("step_without_screen", "contact")}
    from app.spec.schema import Screen
    spec.screens.append(Screen(key="screen:x", name="Klient podaje dane kontaktowe"))
    assert trace_issues(g, spec) == []


def test_c4_context():
    from app.design.uml import c4_context
    _g, spec = booking()
    out = c4_context(spec, 'Salon "Ala"')
    assert out.startswith("C4Context\n") and 'System(sys, "Salon \'Ala\'"' in out
    assert 'Person(p0, "Klient"' in out and 'Rel(p0, sys, "Klient chce umówić wizytę")' in out
    assert 'System_Ext(x0, "Płatność online"' in out
    assert 'Rel(sys, x0, "Kwota, Metoda płatności, Status płatności")' in out
    assert 'System_Ext(ch_email, "Serwer poczty (e-mail)"' in out and 'Rel(sys, ch_email, "Powiadomienia")' in out


def test_documents_include_c4_and_trace():
    from app.design.uml import uml_md
    from app.export.builders import to_markdown
    from app.spec.package import acceptance_md, open_questions_md
    g, spec = booking()
    assert "## Kontekst systemu (C4)" in uml_md(META, spec) and "C4Context" in uml_md(META, spec)
    acc = acceptance_md(g, spec)
    assert "## Macierz śledzenia" in acc and "| Wybór usługi | Klient | Ekran: Wybór usługi |" in acc
    assert "Klient podaje dane kontaktowe” nie ma ekranu" in open_questions_md(g, spec, [])
    assert "### Macierz śledzenia" in to_markdown(META, g)
