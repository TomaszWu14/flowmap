# Projekt aplikacji z mapy — PR 5: C4 kontekst i macierz śledzenia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagram kontekstu C4 (osoby = role, system, systemy zewnętrzne = integracje i kanały powiadomień) oraz macierz śledzenia wymagań (krok → realizacja → przypadek użycia → scenariusze testów) ze strażnikiem, na karcie, w `UML.md`, `ACCEPTANCE.md` i eksporcie Markdown.

**Architecture:** Oba widoki liczone na bieżąco (nic nie zapisujemy — nie ma czego ręcznie poprawiać): `c4_context(spec, title)` w `app/design/uml.py`, nowy `app/design/trace.py` (`trace_rows(graph, spec)`, `trace_issues(graph, spec)`). Uwagi śledzenia potrzebują mapy, więc nie wchodzą do `lint(spec)` ani wyniku gotowości — karta i `OPEN_QUESTIONS.md` dokładają je osobno (bez cyklicznych importów).

**Tech Stack:** Flask, Jinja, Mermaid 11 (`C4Context`), pytest, ruff, Playwright.

## Global Constraints

- Gałąź `feat/design-c4-trace`; PR → CI (kolejka GitHuba bywa długa) → merge → wdrożenie → `curl -s https://flowmap.twapp.pl/przyklad | grep -c "Macierz śledzenia"` z 0 na ≥ 1.
- Edycje: Write/Edit lub skrypt `.py` w scratchpadzie; bez heredoców z `\n`.
- Playwright: sekcje `classes, use_cases, sequences, states, rules, c4, trace`; dla `rules` i `trace` czekaj na tabelę (`.decision-table`, `.trace-table`), dla reszty na SVG; oba motywy, 1440/390, 0 błędów JS.
- Tekst w C4 Mermaid: cudzysłowy zamieniane na `'` (C4 nie zna encji `#quot;`).

---

### Task 1: Macierz śledzenia (`trace.py`)

**Interfaces:** `trace_rows(graph, spec) -> list[dict]` — wiersz na krok czynności (typy poza `start, end, decision, parallel, wait`) w kolejności `_ordered`: `{"node_key", "step", "actor", "realized_by" (lista tekstów), "use_case" (nazwa lub ""), "tests" (numery scenariuszy z `_test_paths`, od 1)}`; `trace_issues(graph, spec) -> list[dict]` w formacie strażnika (`code, message, target_key, why`): `step_without_screen` (czynność użytkownika/ekran bez ekranu w specyfikacji — ekran pasuje po `node_key` albo po nazwie równej tytułowi kroku), `step_without_test` (krok spoza wszystkich scenariuszy).

- [ ] **Step 1: Failing test** — `tests/test_design_c4_trace.py`:

```python
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
```

- [ ] **Step 2:** FAIL (`ModuleNotFoundError: app.design.trace`).
- [ ] **Step 3: Implementation** — `app/design/trace.py`:

```python
"""Requirements traceability: map step → what realizes it in the spec → use case → test scenarios."""

from ..export.builders import _ordered, _test_paths
from ..flow.lanes import assign
from ..spec.schema import Spec

FLOW = ("start", "end", "decision", "parallel", "wait")
NEEDS_SCREEN = ("screen", "user_action")


def _realized(node: dict, spec: Spec) -> list[str]:
    key, title = node["key"], node["title"].strip().lower()
    out = [f"Ekran: {s.name}" for s in spec.screens if s.node_key == key or s.name.strip().lower() == title]
    out += [f"Integracja: {i.name}" for i in spec.integrations if i.node_key == key]
    out += [f"Powiadomienie: {n.trigger}" for n in spec.notifications if n.node_key == key]
    return out


def trace_rows(graph: dict, spec: Spec) -> list[dict]:
    lanes = assign(graph)
    paths = _test_paths(graph)
    by_actor = {u.actor: u.name for u in spec.use_cases}
    roles = {r.name.strip().lower(): r.key for r in spec.roles}
    system_uc = next((u.name for u in spec.use_cases if not u.actor), "")
    rows = []
    for n in _ordered(graph):
        if n["type"] in FLOW:
            continue
        actor = lanes.get(n["key"]) or "System"
        role = roles.get(actor.strip().lower(), "")
        rows.append({"node_key": n["key"], "step": n["title"], "actor": actor, "realized_by": _realized(n, spec),
                     "use_case": by_actor.get(role, "") if role else system_uc,
                     "tests": [i for i, p in enumerate(paths, 1) if n["key"] in p], "type": n["type"]})
    return rows


def _i(code, message, key, why):
    return {"code": code, "message": message, "target_key": key, "why": why}


def trace_issues(graph: dict, spec: Spec) -> list[dict]:
    issues = []
    for r in trace_rows(graph, spec):
        if r["type"] in NEEDS_SCREEN and not any(x.startswith("Ekran:") for x in r["realized_by"]):
            issues.append(_i("step_without_screen", f"Krok „{r['step']}” nie ma ekranu w specyfikacji.", r["node_key"],
                             "Użytkownik musi gdzieś wykonać tę czynność. Dodaj ekran o tej nazwie w specyfikacji "
                             "albo zmień typ kroku na mapie na „Ekran”."))
        if not r["tests"]:
            issues.append(_i("step_without_test", f"Krok „{r['step']}” nie występuje w żadnym scenariuszu testu.",
                             r["node_key"], "Krok poza scenariuszami nie zostanie sprawdzony — zwykle jest "
                             "nieosiągalny ze startu. Połącz go z procesem albo usuń."))
    return issues
```

- [ ] **Step 4:** test → 2 passed (jeśli kolejność `_ordered` albo numery scenariuszy różnią się od testu, wypisz je i popraw test zgodnie z rzeczywistym `_test_paths`, nie kod).
- [ ] **Step 5:** commit „Projekt aplikacji: macierz śledzenia wymagań i jej strażnik”.

---

### Task 2: Kontekst C4

**Interfaces:** `c4_context(spec, title) -> str` (zaczyna się od `C4Context\n`): `Person(p<i>)` dla ról, `System(sys)`, `System_Ext(x<i>)` dla integracji (`Rel` w kierunku z `direction`, `BiRel` dla `both`) i `System_Ext(ch_<kanał>)` dla kanałów powiadomień `email/sms/push`.

- [ ] **Step 1: Failing test** (do `tests/test_design_c4_trace.py`):

```python
def test_c4_context():
    from app.design.uml import c4_context
    _g, spec = booking()
    out = c4_context(spec, 'Salon "Ala"')
    assert out.startswith("C4Context\n") and 'System(sys, "Salon \'Ala\'"' in out
    assert 'Person(p0, "Klient"' in out and 'Rel(p0, sys, "Klient chce umówić wizytę")' in out
    assert 'System_Ext(x0, "Płatność online"' in out and 'Rel(sys, x0, "Kwota, Metoda płatności, Status płatności")' in out
    assert 'System_Ext(ch_email, "Serwer poczty (e-mail)"' in out and 'Rel(sys, ch_email, "Powiadomienia")' in out
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** w `app/design/uml.py`:

```python
CHANNEL_SYSTEMS = {"email": "Serwer poczty (e-mail)", "sms": "Bramka SMS", "push": "Usługa push"}


def _c4(text: str) -> str:
    return (text or "").replace('"', "'").replace("\n", " ").strip()


def c4_context(spec: Spec, title: str = "System") -> str:
    """C4 level 1: people (roles), the system, external systems (integrations, notification channels)."""
    uc = {u.actor: u.name for u in spec.use_cases}
    out = ["C4Context", f"    title Kontekst systemu: {_c4(title)}"]
    out += [f'    Person(p{i}, "{_c4(r.name)}", "{_c4(r.description)}")' for i, r in enumerate(spec.roles)]
    out.append(f'    System(sys, "{_c4(title)}", "Aplikacja zaprojektowana z mapy procesu")')
    for i, x in enumerate(spec.integrations):
        out.append(f'    System_Ext(x{i}, "{_c4(x.name)}", "System zewnętrzny")')
    channels = list(dict.fromkeys(n.channel for n in spec.notifications if n.channel in CHANNEL_SYSTEMS))
    out += [f'    System_Ext(ch_{c}, "{CHANNEL_SYSTEMS[c]}", "Kanał powiadomień")' for c in channels]
    out += [f'    Rel(p{i}, sys, "{_c4(uc.get(r.key, "Korzysta"))}")' for i, r in enumerate(spec.roles)]
    for i, x in enumerate(spec.integrations):
        data = _c4(", ".join(x.data)) or "Wymiana danych"
        if x.direction == "both":
            out.append(f'    BiRel(sys, x{i}, "{data}")')
        elif x.direction == "in":
            out.append(f'    Rel(x{i}, sys, "{data}")')
        else:
            out.append(f'    Rel(sys, x{i}, "{data}")')
    out += [f'    Rel(sys, ch_{c}, "Powiadomienia")' for c in channels]
    return "\n".join(out) + "\n"
```

W `app/static/design.js` do `initialize` dodaj `c4: natural` (czytelny rozmiar jak pozostałe).

- [ ] **Step 4:** test → zielony.
- [ ] **Step 5:** commit „Projekt aplikacji: diagram kontekstu C4”.

---

### Task 3: Karta, UML.md, ACCEPTANCE.md, OPEN_QUESTIONS.md, eksport Markdown

- [ ] **Step 1: Failing tests**:

```python
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
```

(w `tests/test_design_routes.py`):

```python
def test_c4_and_trace_sections(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    assert "C4Context" in auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=c4").get_data(as_text=True)
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=trace").get_data(as_text=True)
    assert "trace-table" in html and "Śledzenie" in html
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementation**

`app/design/uml.py` — `uml_md(meta, spec)` przed `## Przypadki użycia` dopisuje:

```python
           "## Kontekst systemu (C4)", "", "```mermaid", c4_context(spec, meta["name"]).rstrip(), "```", "",
```

(w liście startowej `out`, zaraz po zdaniu wstępnym).

`app/spec/package.py`:

```python
from ..design.trace import trace_issues, trace_rows
```

w `acceptance_md` przed `return`:

```python
    out += ["## Macierz śledzenia", "", "| Krok | Aktor | Realizacja | Przypadek użycia | Scenariusze |",
            "|---|---|---|---|---|"]
    out += [f"| {_md(r['step'])} | {_md(r['actor'])} | {_md('; '.join(r['realized_by'])) or '—'} | "
            f"{_md(r['use_case']) or '—'} | {', '.join(map(str, r['tests'])) or '—'} |" for r in trace_rows(graph, spec)]
    out.append("")
```

w `open_questions_md` po `items = ...`: `items += [i["message"] for i in trace_issues(graph, spec)]`.

`app/export/builders.py` — w `to_markdown` po pętli „Test błędu” (przed `## 8. Otwarte pytania`):

```python
    from ..design.trace import trace_rows  # local: design imports this module

    out += ["", "### Macierz śledzenia", ""]
    out += [f"- {_md(r['step'])} — {_md('; '.join(r['realized_by'])) or 'brak realizacji'} — scenariusze: "
            f"{', '.join(map(str, r['tests'])) or 'brak'}" for r in trace_rows(graph, spec)]
```

`app/design/routes.py` — `DESIGN_SECTIONS` + `"c4": "Kontekst (C4)", "trace": "Śledzenie"`; `EDIT_SECTION` + `"c4": "integrations", "trace": "screens"`; `HELP["c4"] = "Diagram kontekstu C4 (poziom 1): kto korzysta z systemu (osoby = role) i z jakimi systemami zewnętrznymi się komunikuje (integracje, kanały powiadomień)."`, `HELP["trace"] = "Macierz śledzenia wymagań: każdy krok mapy → co go realizuje w specyfikacji → przypadek użycia → scenariusze testów. Luka w wierszu to brakujący ekran albo test."`; w `_diagrams`: `if section == "trace": return []`, `if section == "c4": return [c4_context(spec, project.name)]`; w `view`: `graph = project.graph()`, `ctx["trace"] = trace_rows(graph, spec) if section == "trace" else []`, a uwagi: `issues = [i for i in lint(spec) if SECTION_OF[i["code"]] == section] + (trace_issues(graph, spec) if section == "trace" else [])`.

`app/templates/design/view.html` — po bloku `rules`:

```html
      {% if section == 'trace' %}
        <div class="card table-wrap"><table class="versions trace-table">
          <tr><th>Krok</th><th>Aktor</th><th>Realizacja</th><th title="Przypadek użycia (use case)">Przypadek użycia</th><th>Scenariusze</th></tr>
          {% for r in trace %}<tr><td>{{ r.step }}</td><td>{{ r.actor }}</td>
            <td>{{ r.realized_by|join('; ') if r.realized_by else '—' }}</td><td>{{ r.use_case or '—' }}</td>
            <td>{{ r.tests|join(', ') if r.tests else '—' }}</td></tr>{% endfor %}
        </table></div>
      {% endif %}
```

- [ ] **Step 4:** `ruff check . && pytest -q -p no:warnings` → zielone.
- [ ] **Step 5:** commit „Projekt aplikacji: C4 i macierz śledzenia na karcie i w dokumentach”.

---

### Task 4: Weryfikacja i dowóz

- [ ] Playwright (`qa_uc.py` z 7 sekcjami; `c4` → SVG, `trace` → `.trace-table`); obejrzeć zrzuty C4 (eksperymentalny renderer Mermaid — sprawdź czytelność w ciemnym motywie).
- [ ] PR „Projekt aplikacji (5/6): C4 kontekst i macierz śledzenia” → CI → merge → wdrożenie → `/przyklad` zawiera „Macierz śledzenia”.
- [ ] Notatka w vaulcie.
