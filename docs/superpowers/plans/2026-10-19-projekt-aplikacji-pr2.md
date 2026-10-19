# Projekt aplikacji z mapy — PR 2: przypadki użycia i UML.md Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przypadki użycia wyliczane z torów i bramek mapy (scenariusz główny, alternatywne, «include»), edytowalne w specyfikacji, z diagramem na karcie „Projekt aplikacji”, strażnikiem i plikiem `UML.md` w paczce ZIP.

**Architecture:** Nowa sekcja `use_cases` w `Spec` (dopisana do `SECTIONS` → scalanie, gotowość, edycja działają bez nowego kodu). Wyliczanie w `app/design/derive.py` (wołane z `app/spec/derive.py`), diagram i `UML.md` w `app/design/uml.py`, reguły w `app/design/lint.py`. `ensure_spec` uzupełnia brakujące sekcje w projektach zapisanych przed zmianą.

**Tech Stack:** Flask, Jinja, HTMX, Pydantic, Mermaid 11 (flowchart), pytest, ruff, Playwright.

Projekt: `docs/superpowers/specs/2026-10-19-projekt-aplikacji-z-mapy-design.md`. Poprzedni PR: `2026-10-19-projekt-aplikacji-pr1.md`.

## Global Constraints

- Gałąź `feat/design-use-cases`; PR → zielone CI (`ruff check .`, `pytest -q -p no:warnings`) → merge → wdrożenie Coolify (POST `/api/v1/deploy`, uuid `zxxygxuuxtyvkypz8al9dupo`) → sprawdzenie na produkcji po czymś, co daje tylko nowa wersja.
- Edycje plików przez Write/Edit lub skrypt `.py` z `newline=""`; bez heredoców z `\n` w bashu.
- Playwright: jasny i ciemny motyw, 1440 i 390 px, 0 błędów JS, `<svg>` bez „Syntax error”; CSP blokuje `wait_for_function` — czekać pętlą `page.evaluate`.
- Zmiana reguły strażnika względem projektu: zamiast `gateway_without_alternative` jest `use_case_without_alternative` (przypadek z aktorem bez żadnego wariantu) — prostsze, działa też dla ręcznych przypadków; projekt zaktualizować w Task 5.

## Struktura plików

- Modify `app/spec/schema.py` — `Alternative`, `UseCase`, `Spec.use_cases`, `SECTIONS`.
- Create `app/design/derive.py` — `main_path(graph) -> list[str]`, `use_cases(graph, meta) -> list[UseCase]`.
- Modify `app/spec/derive.py` — `Spec(..., use_cases=...)`.
- Modify `app/flow/graph.py` — `ensure_spec(project)`; użycie w `app/spec/routes.py` (`view`, `package`) i `app/design/routes.py`.
- Modify `app/spec/forms.py`, `app/spec/routes.py` (`SECTION_LABELS`, `FORM_FIELDS`), `app/templates/spec/_section.html`.
- Modify `app/design/uml.py` — `use_case_diagram(spec, title)`, `uml_md(meta, spec)`.
- Modify `app/design/lint.py` — 3 reguły + `SECTION_OF` (kod → sekcja karty).
- Modify `app/design/routes.py`, `app/templates/design/view.html`.
- Modify `app/spec/package.py` — `UML.md`, odwołanie w `CLAUDE.md`.
- Tests: `tests/test_design_use_cases.py` (nowy), `tests/test_design_routes.py`, `tests/test_spec_edit.py`, `tests/test_spec_package.py`.

---

### Task 1: Schemat i wyliczanie przypadków użycia

**Files:**
- Modify: `app/spec/schema.py`, `app/spec/derive.py`
- Create: `app/design/derive.py`
- Test: `tests/test_design_use_cases.py`

**Interfaces:**
- Produces: `Alternative(condition: str, steps: list[str])`, `UseCase(Item)` z polami `name, actor (klucz roli, "" = system), goal, main, alternatives, includes`; `Spec.use_cases`; `"use_cases"` na końcu `SECTIONS`; `main_path(graph) -> list[str]` (klucze węzłów); `use_cases(graph, meta) -> list[UseCase]` (klucze `uc:<slug aktora>`, `uc:system`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_use_cases.py
from app.ai.templates import TEMPLATES, full_graph
from app.design.derive import main_path, use_cases
from app.design.lint import lint
from app.spec.derive import derive

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
```

(Ostatni test przejdzie dopiero po Task 3 — do tego czasu uruchamiaj tylko pierwsze trzy.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_design_use_cases.py -q -p no:warnings -k "not every_template"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.design.derive'`

- [ ] **Step 3: Implementation**

W `app/spec/schema.py` przed `class Proposal`:

```python
class Alternative(BaseModel):
    condition: str = PField(min_length=1, max_length=300)
    steps: list[str] = []


class UseCase(Item):
    name: str = PField(min_length=1, max_length=200)
    actor: str = ""  # role key; empty = included use case run by the system
    goal: str = PField(default="", max_length=300)
    main: list[str] = []
    alternatives: list[Alternative] = []
    includes: list[str] = []  # keys of other use cases
```

`SECTIONS = ("entities", "screens", "roles", "states", "notifications", "integrations", "nfr", "use_cases")`, a w `Spec` po `nfr: list[Nfr] = []`: `use_cases: list[UseCase] = []`.

```python
# app/design/derive.py
"""Use cases from the map: one per human lane, alternatives from gateways and error paths, «include» to System."""

from ..ai.rules import NEGATIVE_LABEL
from ..flow.lanes import assign
from ..spec.derive import slug
from ..spec.schema import Alternative, UseCase

FLOW = ("start", "end", "decision", "parallel", "wait")
SYSTEM = "System"
MAX_ALT_STEPS = 6


def _out(graph: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in graph["edges"]:
        out.setdefault(e["source"], []).append(e)
    return out


def main_path(graph: dict) -> list[str]:
    """Happy path: normal edges, positive gateway answers, no error paths, no loops."""
    out = _out(graph)
    key = next((n["key"] for n in graph["nodes"] if n["type"] == "start"), None)
    path: list[str] = []
    while key and key not in path:
        path.append(key)
        edges = [e for e in out.get(key, []) if e.get("condition") != "error" and e["target"] not in path]
        positive = [e for e in edges if not NEGATIVE_LABEL.match(e.get("label") or "")]
        nxt = (positive or edges or [None])[0]
        key = nxt["target"] if nxt else None
    return path


def _branch(by_key, out, target, main, origin) -> list[str]:
    """Titles along a side branch until it rejoins the main path ('wraca do' / 'dalej') or ends."""
    steps, seen, key = [], set(), target
    while key and key not in seen and len(steps) < MAX_ALT_STEPS:
        seen.add(key)
        if key in main:
            word = "wraca do" if main.index(key) <= origin else "dalej"
            return steps + [f"{word}: {by_key[key]['title']}"]
        steps.append(by_key[key]["title"])
        nxt = [e["target"] for e in out.get(key, []) if e.get("condition") != "error"]
        key = nxt[0] if nxt else None
    return steps


def use_cases(graph: dict, meta: dict) -> list[UseCase]:
    by_key = {n["key"]: n for n in graph["nodes"]}
    lanes = {k: v or "" for k, v in assign(graph).items()}
    out = _out(graph)
    main = main_path(graph)
    acting = [k for k in main if by_key[k]["type"] not in FLOW]
    is_system = lambda lane: slug(lane) == slug(SYSTEM)  # noqa: E731

    alts: dict[str, list[Alternative]] = {}
    prev = ""
    for i, k in enumerate(main):
        n = by_key[k]
        if n["type"] not in FLOW:
            prev = lanes[k]
            for e in out.get(k, []):
                if e.get("condition") == "error":
                    alts.setdefault(slug(lanes[k]), []).append(Alternative(
                        condition=f"{n['title']} — {e.get('label') or 'błąd'}"[:300],
                        steps=_branch(by_key, out, e["target"], main, i)))
        elif n["type"] == "decision":
            owner = lanes[k] if lanes[k] and not is_system(lanes[k]) else prev
            nxt = main[i + 1] if i + 1 < len(main) else None
            for e in out.get(k, []):
                if e["target"] != nxt and e["target"] in by_key:
                    alts.setdefault(slug(owner), []).append(Alternative(
                        condition=f"{n['title']} — {e.get('label') or 'inaczej'}"[:300],
                        steps=_branch(by_key, out, e["target"], main, i)))

    system_steps = [by_key[k]["title"] for k in acting if is_system(lanes[k])]
    hand_to_system = {slug(lanes[a]) for a, b in zip(acting, acting[1:]) if is_system(lanes[b])}
    end_key = main[-1] if main and by_key[main[-1]]["type"] == "end" else None
    initiator = lanes.get(main[0], "") if main else ""

    actors: dict[str, str] = {}
    for n in graph["nodes"]:
        lane = lanes[n["key"]]
        if lane and not is_system(lane):
            actors.setdefault(slug(lane), lane)
    result = []
    for s, actor in actors.items():
        steps = [by_key[k]["title"] for k in acting if slug(lanes[k]) == s] or [
            n["title"] for n in graph["nodes"] if n["type"] not in FLOW and slug(lanes[n["key"]]) == s]
        end_title = by_key[end_key]["title"] if end_key else ""
        goal = end_title if end_key and slug(lanes[end_key]) == s else (steps[-1] if steps else end_title)
        if s == slug(initiator) and meta.get("start_sentence"):
            name = meta["start_sentence"]
        else:
            name = f"{actor}: {steps[0]}" if steps else actor
        result.append(UseCase(key=f"uc:{s}", name=name[:200], actor=f"role:{s}", goal=goal[:300], main=steps,
                              alternatives=alts.get(s, []),
                              includes=["uc:system"] if system_steps and s in hand_to_system else []))
    if system_steps:
        result.append(UseCase(key="uc:system", name="System: kroki automatyczne",
                              goal="Wykonać kroki procesu bez udziału człowieka", main=system_steps,
                              alternatives=alts.get(slug(SYSTEM), [])))
    return result
```

W `app/spec/derive.py` w `derive()` tuż przed `return Spec(...)`:

```python
    from ..design.derive import use_cases as derive_use_cases  # local: design.derive imports this module
```

i dopisz do `return Spec(...)` argument `use_cases=derive_use_cases(graph, meta)`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_design_use_cases.py -q -p no:warnings -k "not every_template"`
Expected: 3 passed. Jeśli `main_path` daje inną kolejność, wypisz `full_graph("booking")["edges"]` i popraw regułę, nie test.

- [ ] **Step 5: Commit**

```bash
git add app/spec/schema.py app/spec/derive.py app/design/derive.py tests/test_design_use_cases.py
git commit -m "Projekt aplikacji: przypadki użycia wyliczane z torów, bramek i ścieżek błędu"
```

---

### Task 2: Edycja przypadków użycia w specyfikacji i uzupełnianie starych projektów

**Files:**
- Modify: `app/spec/forms.py`, `app/spec/routes.py`, `app/templates/spec/_section.html`, `app/flow/graph.py`
- Test: `tests/test_spec_edit.py`, `tests/test_design_routes.py`

**Interfaces:**
- Consumes: `UseCase`, `Alternative` (Task 1).
- Produces: `g.ensure_spec(project) -> None` (wyprowadza i zapisuje specyfikację, gdy jej brak albo gdy poprawnej brakuje którejś sekcji z `SECTIONS`; uszkodzonej nie rusza).

- [ ] **Step 1: Write the failing tests**

W `tests/test_spec_edit.py` dopisz do `SAMPLE_FORM`:

```python
    "use_cases": {"name": "U", "actor": "role:x", "goal": "g", "main": "a\nb",
                  "alternatives": "brak danych | popraw; wróć", "includes": "uc:system"},
```

W `tests/test_design_routes.py` dopisz:

```python
from app.models import Project
from tests.test_flow import play_to_end


def test_old_spec_without_use_cases_is_completed(auth_client, db):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    stored = dict(p.spec)
    stored.pop("use_cases", None)
    p.spec = stored
    db.session.commit()
    html = auth_client.get(f"/p/{p.id}/specyfikacja?sekcja=use_cases").get_data(as_text=True)
    assert "Przypadki użycia" in html
    assert "use_cases" in Project.query.get(p.id).spec
```

(Importy `Project` i `play_to_end` dopisz na górze pliku, obok istniejących.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spec_edit.py tests/test_design_routes.py -q -p no:warnings`
Expected: FAIL — `KeyError: 'use_cases'` w `PREFIX`/formularzu oraz brak sekcji w zapisanym JSON.

- [ ] **Step 3: Implementation**

`app/spec/forms.py`: dopisz `Alternative` i `UseCase` do importu ze `.schema`; `PREFIX` dostaje `"use_cases": "uc"`; w `item_from_form` przed `except ValidationError`:

```python
        if section == "use_cases":
            alts = [Alternative(condition=_col(r, 0), steps=[s.strip() for s in _col(r, 1).split(";") if s.strip()])
                    for r in _rows(f("alternatives"))]
            return UseCase(**base, name=f("name"), actor=f("actor"), goal=f("goal"),
                           main=[r[0] for r in _rows(f("main"))], alternatives=alts,
                           includes=[k.strip() for k in f("includes").split(",") if k.strip()])
```

w `form_text` przed `return item.model_dump()`:

```python
    if section == "use_cases":
        return {"name": item.name, "actor": item.actor, "goal": item.goal, "main": "\n".join(item.main),
                "alternatives": "\n".join(f"{a.condition} | {'; '.join(a.steps)}" for a in item.alternatives),
                "includes": ", ".join(item.includes)}
```

`app/spec/routes.py`: `SECTION_LABELS[...]` dostaje na końcu `"use_cases": "Przypadki użycia"`; `FORM_FIELDS` dostaje:

```python
    "use_cases": [("name", "Nazwa", "input"), ("actor", "Aktor (klucz roli; puste = system)", "input"),
                  ("goal", "Cel (kiedy scenariusz się udał)", "input"),
                  ("main", "Scenariusz główny (krok w linii)", "textarea"),
                  ("alternatives", "Scenariusze alternatywne: warunek | krok; krok", "textarea"),
                  ("includes", "«include» — klucze przypadków użycia po przecinku", "input")],
```

W `view` i `package` zamień blok `if project.spec is None: g.refresh_spec(project); db.session.commit()` (w `package` dodaj przed `_spec_or_abort`) na `g.ensure_spec(project)`.

`app/flow/graph.py` (pod `refresh_spec`; dopisz `SECTIONS` do importu ze `..spec.schema` albo zaimportuj lokalnie):

```python
def ensure_spec(project: Project) -> None:
    """Derive the spec for projects saved before it (or before a newer section) existed. Broken specs stay."""
    if project.spec is None or (project_spec(project) is not None
                                and any(s not in project.spec for s in SECTIONS)):
        refresh_spec(project)
        db.session.commit()
```

`app/templates/spec/_section.html` — przed `{% elif section == 'nfr' %}`:

```html
  {% elif section == 'use_cases' %}
    <p class="muted">Aktor: {{ names.get(item.actor, item.actor) if item.actor else 'System' }} · Cel: {{ item.goal or '—' }}</p>
    <ol>{% for s in item.main %}<li>{{ s }}</li>{% endfor %}</ol>
    {% for a in item.alternatives %}<p><span class="badge" title="Scenariusz alternatywny — w UML «extend»">wariant</span> {{ a.condition }}: {{ a.steps|join(' → ') or '—' }}</p>{% endfor %}
    {% if item.includes %}<p class="muted" title="«include» — ten przypadek zawsze wywołuje wskazany">«include»: {% for k in item.includes %}{{ names.get(k, k) }}{{ ', ' if not loop.last }}{% endfor %}</p>{% endif %}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_spec_edit.py tests/test_design_routes.py tests/test_spec_routes.py -q -p no:warnings`
Expected: wszystkie przechodzą (w tym `test_broken_spec_offers_rebuild` — uszkodzona specyfikacja nie jest nadpisywana).

- [ ] **Step 5: Commit**

```bash
git add app/spec/forms.py app/spec/routes.py app/templates/spec/_section.html app/flow/graph.py tests/test_spec_edit.py tests/test_design_routes.py
git commit -m "Specyfikacja: edycja przypadków użycia, uzupełnianie sekcji w starych projektach"
```

---

### Task 3: Strażnik przypadków użycia

**Files:**
- Modify: `app/design/lint.py`
- Test: `tests/test_design_use_cases.py`

**Interfaces:**
- Produces: kody `role_without_use_case` (3), `use_case_without_goal` (3), `use_case_without_alternative` (2) w `WEIGHTS`; `SECTION_OF: dict[str, str]` — kod uwagi → sekcja karty (`"classes"`, `"use_cases"`).

- [ ] **Step 1: Write the failing test** (dopisz do `tests/test_design_use_cases.py`)

```python
from app.spec.schema import Role, Spec, UseCase


def test_use_case_guard():
    spec = Spec(roles=[Role(key="role:k", name="Kierownik"), Role(key="role:administrator", name="Administrator")],
                use_cases=[UseCase(key="uc:a", name="A", actor="role:x"), UseCase(key="uc:s", name="S", goal="g")])
    codes = {(i["code"], i["target_key"]) for i in lint(spec)}
    assert ("role_without_use_case", "role:k") in codes
    assert ("role_without_use_case", "role:administrator") not in codes
    assert ("use_case_without_goal", "uc:a") in codes and ("use_case_without_alternative", "uc:a") in codes
    assert ("use_case_without_alternative", "uc:s") not in codes  # included (system) use case
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_design_use_cases.py -q -p no:warnings -k guard`
Expected: FAIL — brak kodów w wyniku.

- [ ] **Step 3: Implementation** — w `app/design/lint.py`:

```python
WEIGHTS = {"nn_without_join": 5, "island_entity": 3, "reference_without_relation": 3,
           "role_without_use_case": 3, "use_case_without_goal": 3, "use_case_without_alternative": 2}
SECTION_OF = {"nn_without_join": "classes", "island_entity": "classes", "reference_without_relation": "classes",
              "role_without_use_case": "use_cases", "use_case_without_goal": "use_cases",
              "use_case_without_alternative": "use_cases"}
```

i przed `return issues`:

```python
    acting = {u.actor for u in spec.use_cases}
    for r in spec.roles:
        if r.key not in acting and r.name.strip().lower() != "administrator":
            issues.append(_i("role_without_use_case", f"Rola „{r.name}” nie ma przypadku użycia.", r.key,
                             "Każdy aktor korzysta z systemu po coś — rola bez przypadku użycia to zwykle "
                             "zbędna rola albo pominięta funkcja."))
    for u in spec.use_cases:
        if not u.goal.strip():
            issues.append(_i("use_case_without_goal", f"Przypadek użycia „{u.name}” nie ma celu.", u.key,
                             "Cel mówi, kiedy scenariusz się udał (wartość dla aktora) — bez niego nie da się "
                             "napisać testu akceptacyjnego."))
        if u.actor and not u.alternatives:
            issues.append(_i("use_case_without_alternative", f"Przypadek użycia „{u.name}” nie ma scenariusza "
                             "alternatywnego.", u.key,
                             "W prawdziwych procesach coś idzie inaczej (brak danych, odmowa, błąd systemu) — "
                             "opisz co najmniej jeden wyjątek."))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_design_use_cases.py tests/test_design_lint.py tests/test_spec_readiness.py -q -p no:warnings`
Expected: wszystkie przechodzą, w tym `test_every_template_gets_use_cases_without_role_or_goal_warnings`. Jeśli szablon ma aktora bez celu — popraw regułę `goal` w `derive.py` (np. aktor tylko z węzłem startu), nie wyłączaj testu.

- [ ] **Step 5: Commit**

```bash
git add app/design/lint.py tests/test_design_use_cases.py
git commit -m "Strażnik UML: rola bez przypadku użycia, przypadek bez celu i bez wariantu"
```

---

### Task 4: Diagram przypadków użycia, karta i UML.md

**Files:**
- Modify: `app/design/uml.py`, `app/design/routes.py`, `app/templates/design/view.html`, `app/spec/package.py`, `app/export/builders.py` (`to_markdown`)
- Test: `tests/test_design_use_cases.py`, `tests/test_design_routes.py`, `tests/test_spec_package.py`

**Interfaces:**
- Consumes: `lint`, `SECTION_OF` (Task 3), `g.ensure_spec` (Task 2).
- Produces: `use_case_diagram(spec: Spec, title: str = "System") -> str` (zaczyna się od `flowchart LR\n`), `uml_md(meta: dict, spec: Spec) -> str`; plik `UML.md` w `build_files`.

- [ ] **Step 1: Write the failing tests**

Do `tests/test_design_use_cases.py`:

```python
from app.design.uml import uml_md, use_case_diagram


def test_use_case_diagram():
    spec = derive(full_graph("booking"), META)
    out = use_case_diagram(spec, "Salon")
    assert out.startswith("flowchart LR\n") and 'subgraph SYS["Salon"]' in out
    assert '["👤 Klient"]' in out and '(["Klient chce umówić wizytę"])' in out
    assert '-.->|"«include»"|' in out and '-.->|"«extend»"|' in out
    assert "Brak przypadków użycia" in use_case_diagram(Spec(), "X")


def test_markdown_export_lists_use_cases():
    from app.export.builders import to_markdown
    md = to_markdown(META, full_graph("booking"))
    assert "### Przypadki użycia" in md and "**Klient chce umówić wizytę** — cel: Wizyta odbyta" in md


def test_uml_md():
    md = uml_md(META, derive(full_graph("booking"), META))
    assert "## Przypadki użycia" in md and "1. Wybór usługi" in md and "## Diagram klas" in md
    assert "Płatność online — brak płatności" in md and "## Uwagi strażnika UML" in md
```

Do `tests/test_design_routes.py`:

```python
def test_use_cases_section_on_design_tab(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=use_cases").get_data(as_text=True)
    assert "flowchart LR" in html and "Przypadki użycia" in html and "sekcja=use_cases" in html
```

W `tests/test_spec_package.py`: `FILES` dostaje `"UML.md"`, a w `test_all_files_and_sections` dopisz
`assert "UML.md" in f["CLAUDE.md"] and "flowchart LR" in f["UML.md"]`.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_design_use_cases.py tests/test_design_routes.py tests/test_spec_package.py -q -p no:warnings`
Expected: FAIL — `ImportError: cannot import name 'uml_md'`.

- [ ] **Step 3: Implementation**

`app/design/uml.py` — import `_md` obok `_mm` (`from ..export.builders import _md, _mm`) i `from .lint import lint`; dopisz:

```python
def use_case_diagram(spec: Spec, title: str = "System") -> str:
    """UML use case diagram as a Mermaid flowchart (Mermaid has no native one): actors, system boundary,
    «include» to shared use cases and «extend» for alternative scenarios."""
    roles = {r.key: r.name for r in spec.roles}
    ids = {u.key: f"U{i}" for i, u in enumerate(spec.use_cases)}
    actors = {k: f"A{i}" for i, k in enumerate(dict.fromkeys(u.actor for u in spec.use_cases if u.actor in roles))}
    out = ["flowchart LR"] + [f'    {a}["👤 {_mm(roles[k])}"]' for k, a in actors.items()]
    out.append(f'    subgraph SYS["{_mm(title)}"]')
    extends = []
    for u in spec.use_cases:
        out.append(f'        {ids[u.key]}(["{_mm(u.name)}"])')
        for j, alt in enumerate(u.alternatives):
            out.append(f'        {ids[u.key]}X{j}(["{_mm(alt.condition)}"])')
            extends.append(f'    {ids[u.key]}X{j} -.->|"«extend»"| {ids[u.key]}')
    if not spec.use_cases:
        out.append('        EMPTY["Brak przypadków użycia"]')
    out.append("    end")
    out += [f"    {actors[u.actor]} --- {ids[u.key]}" for u in spec.use_cases if u.actor in actors]
    out += [f'    {ids[u.key]} -.->|"«include»"| {ids[k]}' for u in spec.use_cases for k in u.includes if k in ids]
    return "\n".join(out + extends) + "\n"


def uml_md(meta: dict, spec: Spec) -> str:
    roles = {r.key: r.name for r in spec.roles}
    names = {u.key: u.name for u in spec.use_cases}
    out = [f"# Projekt aplikacji (UML): {_md(meta['name'])}", "",
           "Diagramy wygenerowane z mapy procesu. Uwagi strażnika UML są na końcu i w `OPEN_QUESTIONS.md`.", "",
           "## Przypadki użycia", "", "```mermaid", use_case_diagram(spec, meta["name"]).rstrip(), "```", ""]
    for u in spec.use_cases:
        out += [f"### {_md(u.name)}", "", f"- Aktor: {_md(roles.get(u.actor, 'System'))}",
                f"- Cel: {_md(u.goal) or '—'}"]
        if u.includes:
            out.append("- Zawiera (include): " + ", ".join(_md(names.get(k, k)) for k in u.includes))
        out += ["", "Scenariusz główny:", ""]
        out += [f"{i}. {_md(s)}" for i, s in enumerate(u.main, 1)] or ["—"]
        if u.alternatives:
            out += ["", "Scenariusze alternatywne:", ""]
            out += [f"- {_md(a.condition)}: {_md(' → '.join(a.steps)) or '—'}" for a in u.alternatives]
        out.append("")
    out += ["## Diagram klas", "", "```mermaid", class_diagram(spec).rstrip(), "```", "", "## Uwagi strażnika UML", ""]
    out += [f"- {_md(i['message'])} — {_md(i['why'])}" for i in lint(spec)] or ["- brak"]
    return "\n".join(out) + "\n"
```

`app/design/routes.py` — zastąp `DESIGN_SECTIONS`, `DIAGRAMS`, `HELP` i środek `view`:

```python
from .lint import SECTION_OF, lint
from .uml import class_diagram, use_case_diagram

DESIGN_SECTIONS = {"classes": "Klasy", "use_cases": "Przypadki użycia"}
EDIT_SECTION = {"classes": "entities", "use_cases": "use_cases"}
HELP = {"classes": "Diagram klas UML: encje (klasy) z polami i relacjami. Krotność „1 → *” czytaj: "
                   "jeden rekord po lewej ma wiele po prawej.",
        "use_cases": "Diagram przypadków użycia UML: kto (aktor) korzysta z systemu i po co. «include» — przypadek "
                     "zawsze wywołuje inny; «extend» — wariant lub wyjątek rozszerzający scenariusz."}


def _diagram(section, spec, project) -> str:
    return use_case_diagram(spec, project.name) if section == "use_cases" else class_diagram(spec)
```

```python
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
    section = request.args.get("sekcja", "classes")
    if section not in DESIGN_SECTIONS:
        abort(400)
    spec = g.project_spec(project)
    ctx = {"project": project, "spec": spec, "section": section, "sections": DESIGN_SECTIONS,
           "help": HELP[section], "edit_section": EDIT_SECTION[section], "diagram": "", "issues": []}
    if spec is not None:
        ctx.update(diagram=_diagram(section, spec, project),
                   issues=[i for i in lint(spec) if SECTION_OF[i["code"]] == section])
    return render_template("design/view.html", **ctx)
```

(Import `db` przestaje być potrzebny — usuń go.)

`app/templates/design/view.html` — zamień blok `{% if section == 'classes' %}…{% endif %}` na:

```html
        <p><a href="{{ url_for('spec.view', project_id=project.id, sekcja=edit_section) }}">Edytuj w specyfikacji</a></p>
```

`app/spec/package.py` — `from ..design.uml import uml_md`; w `build_files` dodaj `"UML.md": uml_md(meta, spec),`; w `claude_md` zmień pierwsze zdanie opisu plików na:

```python
           f"Proces: „{_md(meta['start_sentence'])}”. Specyfikacja: `SPEC.md`, model danych: `DATA_MODEL.md`, "
           "przypadki użycia i diagramy UML: `UML.md`, testy akceptacyjne: `ACCEPTANCE.md`, "
           "wątpliwości: `OPEN_QUESTIONS.md`.", "",
```

oraz punkt 3 „Kolejności budowy” na:
`"3. Ekrany w kolejności procesu z `SPEC.md` (pola, akcje, walidacja); kto co robi i co przy wyjątkach — przypadki użycia z `UML.md`.",`

`app/export/builders.py` — w `to_markdown` po linii
`out.append("- Każdy użytkownik widzi tylko własne dane; role inne niż System wymagają logowania.")` dopisz
(podsekcja, żeby nie przenumerowywać rozdziałów):

```python
    if spec.use_cases:
        out += ["", "### Przypadki użycia", ""]
        out += [f"- **{_md(u.name)}** — cel: {_md(u.goal) or '—'}"
                + (f"; warianty: {_md('; '.join(a.condition for a in u.alternatives))}" if u.alternatives else "")
                for u in spec.use_cases]
```

- [ ] **Step 4: Run tests**

Run: `ruff check . && python -m pytest -q -p no:warnings`
Expected: wszystko zielone.

- [ ] **Step 5: Commit**

```bash
git add app/design/uml.py app/design/routes.py app/templates/design/view.html app/spec/package.py tests/
git commit -m "Projekt aplikacji: diagram przypadków użycia, UML.md w paczce dla Claude Code"
```

---

### Task 5: Weryfikacja, projekt, dowóz

- [ ] **Step 1:** W `docs/superpowers/specs/2026-10-19-projekt-aplikacji-z-mapy-design.md` zamień wiersz `gateway_without_alternative` na `use_case_without_alternative` („przypadek z aktorem bez żadnego scenariusza alternatywnego”).
- [ ] **Step 2: Playwright** — skrypt `qa_design.py` ze scratchpadu rozszerzony o pętlę po sekcjach `classes` i `use_cases`: `pre.mermaid svg`, brak „Syntax error”, przełączenie motywu, bez poziomego przewijania, 0 błędów JS; dodatkowo `/p/<id>/specyfikacja?sekcja=use_cases` pokazuje kartę z „wariant”, a „Edytuj” otwiera formularz (HTMX) i „Zapisz” zachowuje zmianę (sprawdź w bazie `source == "manual"`). Zrzuty ekranu obejrzeć.
- [ ] **Step 3:** PR „Projekt aplikacji (2/6): przypadki użycia i UML.md” → CI → merge → wdrożenie.
- [ ] **Step 4: Produkcja:** przed wdrożeniem `curl -s https://flowmap.twapp.pl/przyklad | grep -c "Przypadki użycia"` daje 0; po wdrożeniu (powtarzaj co ~15 s, maks. 10 min) ≥ 1 — publiczny dowód nowej wersji.
