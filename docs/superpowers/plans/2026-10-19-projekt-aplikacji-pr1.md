# Projekt aplikacji z mapy — PR 1: karta, Mermaid, diagram klas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Karta „Projekt aplikacji” z diagramem klas (Mermaid) wyliczonym z encji specyfikacji i strażnikiem klas, który tłumaczy błędy.

**Architecture:** Nowy pakiet `app/design/` (blueprint `design`, `uml.py` = Spec → tekst Mermaid, `lint.py` = strażnik UML w formacie `readiness()`). Uwagi strażnika wchodzą do `readiness()` (wynik gotowości, `OPEN_QUESTIONS.md`). Mermaid z `app/static/vendor/`, rysowany przez `app/static/design.js` po stronie przeglądarki.

**Tech Stack:** Flask, Jinja, HTMX, Pydantic (`app/spec/schema.py`), Mermaid 11.17.2 (UMD), pytest, ruff, Playwright.

Projekt: `docs/superpowers/specs/2026-10-19-projekt-aplikacji-z-mapy-design.md`.

## Global Constraints

- Gałąź `feat/design-classes`; PR → zielone CI (`ruff check .`, `pytest -q -p no:warnings`) → merge → wdrożenie Coolify (POST `/api/v1/deploy`, uuid `zxxygxuuxtyvkypz8al9dupo`) → sprawdzenie na produkcji po nowej trasie (`/p/<id>/projekt-aplikacji` przestaje dawać 404 i przekierowuje do logowania).
- CSP bez zmian: `script-src 'self'` — Mermaid wyłącznie z `app/static/vendor/mermaid.min.js`, bez CDN w czasie działania.
- Interfejs po polsku; słownictwo UML z objaśnieniem (`title`).
- Edycje plików przez Write/Edit (LF, bez CRLF); bez heredoców z `\n` w bashu.
- Playwright: jasny i ciemny motyw, 1440 i 390 px, 0 błędów JS, `<svg>` w podglądzie i brak tekstu „Syntax error”; lokalny serwer na porcie 5058.
- Przy `[hidden]` i klasie z `display: grid/flex` dopisz `.klasa[hidden] { display: none }`.

## Plan całości (6 PR-ów)

| PR | Zakres | Plan |
|---|---|---|
| 1 | Mermaid w `vendor/`, karta „Projekt aplikacji”, diagram klas, strażnik klas | ten dokument |
| 2 | Przypadki użycia (schemat, wyliczanie, formularz, diagram, strażnik) + `UML.md` w ZIP | osobny plan po PR 1 |
| 3 | Sekwencje + strażnik | osobny plan |
| 4 | Stany z warunkami + tabele decyzyjne + strażnik | osobny plan |
| 5 | C4 kontekst + macierz śledzenia (`ACCEPTANCE.md`) + strażnik | osobny plan |
| 6 | Wizja i MVP + „Uzupełnij z AI” + `VISION.md` | osobny plan |

Każdy kolejny plan powstaje na starcie swojego PR (zależy od kształtu karty i `lint.py` z PR 1).

## Struktura plików (PR 1)

- Create `app/design/__init__.py` — pusty.
- Create `app/design/uml.py` — `class_diagram(spec: Spec) -> str`.
- Create `app/design/lint.py` — `lint(spec: Spec) -> list[dict]`, `WEIGHTS: dict[str, int]`.
- Create `app/design/routes.py` — blueprint `design`, `GET /p/<id>/projekt-aplikacji`.
- Create `app/templates/design/view.html`.
- Create `app/static/design.js`; Create `app/static/vendor/mermaid.min.js` (pobrany).
- Modify `app/__init__.py` (rejestracja blueprintu), `app/spec/readiness.py` (uwagi strażnika), `app/templates/spec/view.html` i `app/templates/flow/view.html` (link do karty), `app/static/app.css` (układ karty).
- Tests: `tests/test_design_uml.py`, `tests/test_design_lint.py`, `tests/test_design_routes.py`, `tests/test_static_js.py`.

---

### Task 1: Diagram klas (`uml.py`)

**Files:**
- Create: `app/design/__init__.py`, `app/design/uml.py`
- Test: `tests/test_design_uml.py`

**Interfaces:**
- Consumes: `Spec`, `Entity`, `Field`, `Relation` z `app/spec/schema.py`; `_mm` z `app/export/builders.py`.
- Produces: `class_diagram(spec: Spec) -> str` — tekst zaczynający się od `classDiagram\n`; encja `i` ma identyfikator `E{i}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_uml.py
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
    assert '"' not in out.split('class E0[')[1].split("]")[0].strip('"')  # cudzysłów w nazwie zneutralizowany
    assert "(" not in out and "{x}" not in out  # nawiasy robiłyby z pola metodę / psuły blok


def test_empty_spec():
    assert class_diagram(Spec()) == "classDiagram\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_design_uml.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.design'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/design/__init__.py
```

```python
# app/design/uml.py
"""Spec → Mermaid text for the 'Projekt aplikacji' tab and UML.md. Pure functions, no database."""

import re

from ..export.builders import _mm
from ..spec.schema import Spec

CARDINALITY = {"1-1": '"1" -- "1"', "1-n": '"1" --> "*"', "n-n": '"*" -- "*"'}


def _member(text: str) -> str:
    """Class member text: parentheses would turn it into a method, braces would close the block."""
    return re.sub(r"[(){}]", "", _mm(text)).strip()


def class_diagram(spec: Spec) -> str:
    ids = {e.key: f"E{i}" for i, e in enumerate(spec.entities)}
    out = ["classDiagram"]
    for e in spec.entities:
        out.append(f'    class {ids[e.key]}["{_member(e.name)}"] {{')
        out += [f"        +{f.type} {_member(f.name)}" for f in e.fields]
        out.append("    }")
    for e in spec.entities:
        for r in e.relations:
            if r.to_entity in ids:
                out.append(f"    {ids[e.key]} {CARDINALITY[r.kind]} {ids[r.to_entity]} : {_member(r.label or r.kind)}")
    return "\n".join(out) + "\n"
```

Uwaga: dla pustej specyfikacji `"\n".join(["classDiagram"]) + "\n"` daje `"classDiagram\n"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_design_uml.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/design/__init__.py app/design/uml.py tests/test_design_uml.py
git commit -m "Projekt aplikacji: diagram klas Mermaid z encji specyfikacji"
```

---

### Task 2: Strażnik klas (`lint.py`) i wpięcie w gotowość

**Files:**
- Create: `app/design/lint.py`
- Modify: `app/spec/readiness.py`
- Test: `tests/test_design_lint.py`

**Interfaces:**
- Consumes: `Spec` (Task 1 nie jest potrzebny).
- Produces: `lint(spec: Spec) -> list[dict]` — elementy `{"code", "message", "target_key", "why"}`; `WEIGHTS = {"nn_without_join": 5, "island_entity": 3, "reference_without_relation": 3}`. `readiness(spec)["issues"]` zawiera te uwagi (z polem `why`), a wynik uwzględnia ich wagi.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_lint.py
from app.design.lint import lint
from app.spec.readiness import readiness
from app.spec.schema import Entity, Field, Relation, Spec


def ent(key, name, relations=(), fields=()):
    return Entity(key=key, name=name, relations=list(relations),
                  fields=[Field(key="id", name="id", type="integer", is_identifier=True), *fields])


def codes(spec):
    return [(i["code"], i["target_key"]) for i in lint(spec)]


def test_nn_without_join_entity():
    spec = Spec(entities=[ent("entity:a", "A", [Relation(key="r", to_entity="entity:b", kind="n-n")]),
                          ent("entity:b", "B")])
    assert ("nn_without_join", "entity:a") in codes(spec)
    joined = Spec(entities=[*spec.entities, ent("entity:ab", "AB", [Relation(key="x", to_entity="entity:a"),
                                                                     Relation(key="y", to_entity="entity:b")])])
    assert ("nn_without_join", "entity:a") not in codes(joined)


def test_island_entity_only_when_more_than_one():
    assert codes(Spec(entities=[ent("entity:a", "A")])) == []
    spec = Spec(entities=[ent("entity:a", "A", [Relation(key="r", to_entity="entity:b")]), ent("entity:b", "B"),
                          ent("entity:c", "C")])
    assert codes(spec) == [("island_entity", "entity:c")]


def test_reference_field_without_relation():
    ref = Field(key="k", name="klient", type="reference", ref_entity="entity:b")
    spec = Spec(entities=[ent("entity:a", "A", fields=[ref]), ent("entity:b", "B")])
    assert ("reference_without_relation", "entity:a") in codes(spec)
    spec.entities[1].relations.append(Relation(key="r", to_entity="entity:a"))
    assert ("reference_without_relation", "entity:a") not in codes(spec)


def test_every_issue_explains_why_and_counts_in_readiness():
    spec = Spec(entities=[ent("entity:a", "A"), ent("entity:b", "B")])
    issues = lint(spec)
    assert issues and all(i["why"] and i["message"] for i in issues)
    ready = readiness(spec)
    assert any(i["code"] == "island_entity" for i in ready["issues"])
    assert ready["score"] == 100 - 2 * 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_design_lint.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.design.lint'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/design/lint.py
"""UML guard: issues in readiness() format plus 'why' — one sentence a learning analyst can act on."""

from ..spec.schema import Spec

WEIGHTS = {"nn_without_join": 5, "island_entity": 3, "reference_without_relation": 3}


def _i(code, message, key, why):
    return {"code": code, "message": message, "target_key": key, "why": why}


def _linked(spec: Spec) -> dict[str, set[str]]:
    """entity key -> keys of entities it is connected to (both directions, relations only)."""
    out = {e.key: set() for e in spec.entities}
    for e in spec.entities:
        for r in e.relations:
            if r.to_entity in out:
                out[e.key].add(r.to_entity)
                out[r.to_entity].add(e.key)
    return out


def lint(spec: Spec) -> list[dict]:
    issues = []
    linked = _linked(spec)
    names = {e.key: e.name for e in spec.entities}
    for e in spec.entities:
        for r in e.relations:
            if r.kind == "n-n" and r.to_entity in names and not any(
                    {e.key, r.to_entity} <= linked[j] for j in linked if j not in (e.key, r.to_entity)):
                issues.append(_i("nn_without_join", f"Relacja wiele-do-wielu „{e.name}” – „{names[r.to_entity]}” "
                                 "nie ma encji łączącej.", e.key,
                                 "Baza relacyjna zapisze n-n tylko przez tabelę pośrednią; nazwij ją i dodaj jej "
                                 "pola (np. data, ilość) — zwykle to ważne pojęcie biznesowe."))
        if len(spec.entities) > 1 and not linked[e.key] and not any(f.type == "reference" for f in e.fields):
            issues.append(_i("island_entity", f"Encja „{e.name}” nie jest powiązana z żadną inną.", e.key,
                             "Encja bez relacji to zwykle zapomniane powiązanie albo pojęcie spoza systemu — "
                             "dodaj relację lub usuń encję."))
        for f in e.fields:
            if f.type == "reference" and f.ref_entity in names and f.ref_entity not in linked[e.key]:
                issues.append(_i("reference_without_relation", f"Pole „{e.name}.{f.name}” wskazuje "
                                 f"„{names[f.ref_entity]}”, ale brak relacji.", e.key,
                                 "Pole-odwołanie to klucz obcy; relacja z krotnością mówi, ile rekordów może "
                                 "się wiązać — bez niej model jest niepełny."))
    return issues
```

W `app/spec/readiness.py`: dodaj import i wagi, a przed `issues += [_i("open_proposal", ...` dopisz uwagi strażnika:

```python
from ..design.lint import WEIGHTS as LINT_WEIGHTS
from ..design.lint import lint
from .schema import SECTIONS, Spec
```

```python
WEIGHTS = {"no_identifier": 10, "enum_without_values": 3, "bad_relation": 8, "screen_without_role": 5,
           "role_without_permissions": 5, "states_without_initial_or_final": 8,
           "notification_without_recipient": 3, "integration_without_error": 5, "stale_item": 2,
           "open_proposal": 1, "duplicate_item": 3, **LINT_WEIGHTS}
```

```python
    issues += lint(spec)
    issues += [_i("open_proposal", f"Propozycja AI czeka: {p.summary}", p.target_key) for p in spec.proposals]
```

- [ ] **Step 4: Run tests to verify they pass (plus regressions w gotowości i paczce)**

Run: `python -m pytest tests/test_design_lint.py tests/test_spec_readiness.py tests/test_spec_package.py -q`
Expected: wszystkie przechodzą. Jeśli test w `test_spec_readiness.py` sprawdza dokładny wynik na szablonie, a szablon ma teraz uwagę strażnika — popraw oczekiwaną wartość w teście tylko wtedy, gdy uwaga jest zasadna (sprawdź `lint(derive(...))` w REPL), w przeciwnym razie popraw regułę.

- [ ] **Step 5: Commit**

```bash
git add app/design/lint.py app/spec/readiness.py tests/test_design_lint.py
git commit -m "Projekt aplikacji: strażnik klas (n-n bez encji łączącej, wyspa, odwołanie bez relacji)"
```

---

### Task 3: Karta „Projekt aplikacji” z podglądem Mermaid

**Files:**
- Create: `app/design/routes.py`, `app/templates/design/view.html`, `app/static/design.js`, `app/static/vendor/mermaid.min.js`
- Modify: `app/__init__.py` (po `app.register_blueprint(media_bp)`), `app/templates/spec/view.html:6-7`, `app/templates/flow/view.html:16`, `app/static/app.css` (po linii z `.spec-layout` w `@media (max-width: 900px)`)
- Test: `tests/test_design_routes.py`, `tests/test_static_js.py`

**Interfaces:**
- Consumes: `class_diagram(spec)` (Task 1), `lint(spec)` (Task 2), `g.project_for(project_id, "view")`, `g.project_spec(project)`, `g.refresh_spec(project)`.
- Produces: endpoint `design.view` (`GET /p/<int:project_id>/projekt-aplikacji?sekcja=classes`); `DESIGN_SECTIONS = {"classes": "Klasy"}` w `app/design/routes.py` — PR 2–6 dopisują kolejne klucze; szablon oczekuje w kontekście `diagram` (tekst Mermaid) i `issues` (lista z `lint`).

- [ ] **Step 1: Pobierz Mermaid**

Run: `curl -sfL -o app/static/vendor/mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js && head -c 120 app/static/vendor/mermaid.min.js`
Expected: plik ~3 MB, zaczyna się od kodu JS (nie od HTML błędu). Sprawdź: `grep -c "globalThis.mermaid\|mermaid" app/static/vendor/mermaid.min.js` > 0.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_design_routes.py
from tests.test_collaborators import team  # noqa: F401
from tests.test_projects import new_project


def test_design_tab_shows_class_diagram_and_guard(auth_client):
    p = new_project(auth_client)
    r = auth_client.get(f"/p/{p.id}/projekt-aplikacji")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'class="mermaid"' in html and "classDiagram" in html
    assert "vendor/mermaid.min.js" in html and "design.js" in html
    assert "Projekt aplikacji" in html and "Klasy" in html
    assert auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=zle").status_code == 400


def test_links_from_map_and_spec(auth_client):
    p = new_project(auth_client)
    for url in (f"/p/{p.id}", f"/p/{p.id}/specyfikacja"):
        assert f"/p/{p.id}/projekt-aplikacji" in auth_client.get(url).get_data(as_text=True)


def test_design_tab_permissions(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].get(f"/p/{p.id}/projekt-aplikacji").status_code == 200
    assert team["outsider"].get(f"/p/{p.id}/projekt-aplikacji").status_code == 404


def test_broken_spec_points_to_rebuild(auth_client, db):
    p = new_project(auth_client)
    p.spec = {"entities": [{"name": "bez klucza"}]}
    db.session.commit()
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji").get_data(as_text=True)
    assert "uszkodzona" in html and f"/p/{p.id}/specyfikacja" in html
```

Do `tests/test_static_js.py` dopisz:

```python
def test_design_js_defines_its_helpers():
    src = (STATIC / "design.js").read_text(encoding="utf-8")
    for name in ("render", "theme"):
        assert re.search(rf"function {name}\(", src), name
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_design_routes.py tests/test_static_js.py -q`
Expected: FAIL — 404 na `/projekt-aplikacji`, brak `design.js`.

- [ ] **Step 4: Write the implementation**

```python
# app/design/routes.py
"""'Projekt aplikacji' tab: UML views of the spec with a Mermaid preview and the UML guard."""

from flask import Blueprint, abort, render_template, request
from flask_login import login_required

from ..extensions import db
from ..flow import graph as g
from .lint import lint
from .uml import class_diagram

bp = Blueprint("design", __name__)
DESIGN_SECTIONS = {"classes": "Klasy"}
DIAGRAMS = {"classes": class_diagram}
HELP = {"classes": "Diagram klas UML: encje (klasy) z polami i relacjami. Krotność „1 → *” czytaj: "
                   "jeden rekord po lewej ma wiele po prawej."}


@bp.get("/p/<int:project_id>/projekt-aplikacji")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    if project.spec is None:
        g.refresh_spec(project)
        db.session.commit()
    section = request.args.get("sekcja", "classes")
    if section not in DESIGN_SECTIONS:
        abort(400)
    spec = g.project_spec(project)
    ctx = {"project": project, "spec": spec, "section": section, "sections": DESIGN_SECTIONS,
           "help": HELP[section], "diagram": "", "issues": []}
    if spec is not None:
        names = {e.key: e.name for e in spec.entities}
        ctx.update(diagram=DIAGRAMS[section](spec), issues=lint(spec), names=names)
    return render_template("design/view.html", **ctx)
```

W `app/__init__.py` obok pozostałych importów blueprintów dodaj `from .design.routes import bp as design_bp`, a po `app.register_blueprint(media_bp)`:

```python
    app.register_blueprint(design_bp)
```

```html
{# app/templates/design/view.html #}
{% extends "base.html" %}
{% block title %}Projekt aplikacji — {{ project.name }}{% endblock %}
{% block content %}
<div class="page-head">
  <div><h1>{{ project.name }}</h1>
    <div class="row"><a class="btn small" href="{{ url_for('flow.view', project_id=project.id) }}">Mapa</a>
      <a class="btn small" href="{{ url_for('spec.view', project_id=project.id) }}">Specyfikacja</a>
      <span class="btn small primary" aria-current="page">Projekt aplikacji</span></div></div>
</div>
{% if spec is none %}
  <div class="alert error">Zapisana specyfikacja jest uszkodzona —
    <a href="{{ url_for('spec.view', project_id=project.id) }}">odbuduj ją w zakładce Specyfikacja</a>.</div>
{% else %}
<div class="spec-layout">
  <nav class="spec-nav" aria-label="Sekcje projektu aplikacji">
    {% for key, label in sections.items() %}
      <a href="{{ url_for('design.view', project_id=project.id, sekcja=key) }}" class="{{ 'active' if key == section }}">{{ label }}</a>
    {% endfor %}
  </nav>
  <section class="design-section">
    <p class="muted">{{ help }}</p>
    <div class="design-grid">
      <div>
        {% for i in issues %}
          <details class="alert design-issue"><summary>{{ i.message }}</summary><p>Dlaczego: {{ i.why }}</p></details>
        {% else %}
          <p class="muted">Strażnik UML nie ma uwag.</p>
        {% endfor %}
        {% if section == 'classes' %}
          <p><a href="{{ url_for('spec.view', project_id=project.id, sekcja='entities') }}">Edytuj encje w specyfikacji</a></p>
        {% endif %}
      </div>
      <figure class="card design-preview" aria-label="Podgląd diagramu">
        <pre class="mermaid" data-source="{{ diagram }}">{{ diagram }}</pre>
      </figure>
    </div>
  </section>
</div>
{% endif %}
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='vendor/mermaid.min.js') }}"></script>
<script src="{{ url_for('static', filename='design.js') }}"></script>
{% endblock %}
```

```javascript
// app/static/design.js
// Mermaid preview on the 'Projekt aplikacji' tab: render on load, after HTMX swaps and on theme change.
(function () {
  if (!window.mermaid) return;

  function theme() {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "default";
  }

  function render() {
    window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: theme() });
    document.querySelectorAll("pre.mermaid").forEach((el) => {
      el.removeAttribute("data-processed");
      el.textContent = el.dataset.source;
    });
    window.mermaid.run({ querySelector: "pre.mermaid" }).catch((err) => console.warn("mermaid", err));
  }

  document.addEventListener("DOMContentLoaded", render);
  document.addEventListener("htmx:afterSwap", render);
  document.addEventListener("themeChanged", render);
})();
```

Uwaga: `console.warn`, nie `console.error` — błąd składni diagramu nie może wyglądać w Playwright jak błąd JS aplikacji; Playwright sprawdza go osobno (tekst „Syntax error” w podglądzie).

W `app/templates/spec/view.html` po linku „Mapa” (linia 6) dodaj w tym samym `div.row`:

```html
      <a class="btn small" href="{{ url_for('design.view', project_id=project.id) }}">Projekt aplikacji</a>
```

W `app/templates/flow/view.html` po linku „Specyfikacja” (linia 16):

```html
        <a class="btn small" href="{{ url_for('design.view', project_id=project.id) }}">Projekt aplikacji</a>
```

W `app/static/app.css` pod regułami `.spec-nav` (przed `@media (max-width: 900px)`):

```css
.design-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: 1rem; align-items: start; }
.design-preview { margin: 0; overflow-x: auto; }
.design-preview svg { max-width: 100%; height: auto; }
.design-issue summary { cursor: pointer; }
.design-issue p { margin: .4rem 0 0; }
```

i wewnątrz istniejącego `@media (max-width: 900px) { ... }` dopisz `.design-grid { grid-template-columns: minmax(0, 1fr); }`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_design_routes.py tests/test_static_js.py -q`
Expected: wszystkie przechodzą.

- [ ] **Step 6: Commit**

```bash
git add app/design/routes.py app/templates/design/view.html app/static/design.js app/static/vendor/mermaid.min.js app/__init__.py app/templates/spec/view.html app/templates/flow/view.html app/static/app.css tests/test_design_routes.py tests/test_static_js.py
git commit -m "Projekt aplikacji: karta z podglądem Mermaid (diagram klas) i uwagami strażnika"
```

---

### Task 4: Weryfikacja i dowóz

**Files:** brak zmian w kodzie (chyba że weryfikacja coś wykaże).

- [ ] **Step 1: Pełny zestaw testów i ruff**

Run: `ruff check . && python -m pytest -q -p no:warnings`
Expected: `All checks passed!` i wszystkie testy zielone (253 + nowe).

- [ ] **Step 2: Playwright**

Skrypt w scratchpadzie (wzór: `qa_zip.py` z sesji — konfiguracja `QA(TestConfig)` z plikową bazą SQLite, serwer `make_server("127.0.0.1", 5058, app)`, logowanie formularzem). Dla `theme in ("light", "dark")` × `width in (1440, 390)`:
- `page.goto(f"{base}/p/{pid}/projekt-aplikacji")`;
- `page.wait_for_selector("pre.mermaid svg", timeout=10000)`;
- `assert "Syntax error" not in page.inner_text(".design-preview")`;
- brak poziomego przewijania (`document.documentElement.scrollWidth <= innerWidth`);
- przełączenie motywu przyciskiem `[data-theme-toggle]` i ponowne `wait_for_selector("pre.mermaid svg")`;
- zbieraj `pageerror` i `console` typu `error` → na końcu lista ma być pusta;
- zrzut ekranu do scratchpadu.
Dodatkowo kliknij link „Projekt aplikacji” na mapie (`/p/<id>`) i sprawdź, że klikanie kroku na mapie nadal otwiera panel (grabie: `openNode`).

- [ ] **Step 3: PR, CI, merge, wdrożenie**

```bash
git push -u origin feat/design-classes
gh pr create --title "Projekt aplikacji (1/6): karta, Mermaid, diagram klas i strażnik" --body "<opis + wyniki testów i Playwright + stopka>"
gh pr checks <nr> --watch --interval 10
gh pr merge <nr> --merge --delete-branch
curl -X POST -H "Authorization: Bearer $COOLIFY_TOKEN" -H "Content-Type: application/json" -d '{"uuid":"zxxygxuuxtyvkypz8al9dupo"}' https://coolify.twapp.pl/api/v1/deploy
```

- [ ] **Step 4: Sprawdzenie na produkcji**

Run (powtarzaj co ~20 s, maks. 10 min): `curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://flowmap.twapp.pl/p/1/projekt-aplikacji`
Expected: przed wdrożeniem `404`, po wdrożeniu `302` z przekierowaniem na `/login` — dowód, że działa nowa wersja.
