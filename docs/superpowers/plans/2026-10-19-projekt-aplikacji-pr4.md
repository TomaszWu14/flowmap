# Projekt aplikacji z mapy — PR 4: stany z warunkami i tabele decyzyjne Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagramy stanów z warunkami przejść (z bramek mapy) i tabele decyzyjne (reguły biznesowe) wyliczane z bramek, ze strażnikiem (status nieosiągalny, ślepa uliczka, luka i nakładanie reguł), w `UML.md`, `DATA_MODEL.md` i eksporcie Markdown.

**Architecture:** `Transition.condition` (nowe pole) + `stateDiagram-v2` z etykietami w `app/design/uml.py` (używany też przez `DATA_MODEL.md` — jedno źródło). Nowa sekcja `rules` (`Rule`, `RuleRow`) wyliczana w `app/design/derive.py`; na karcie tabela HTML zamiast Mermaid (tabela decyzyjna to tabela, nie diagram).

**Tech Stack:** Flask, Jinja, HTMX, Pydantic, Mermaid 11 (`stateDiagram-v2`), pytest, ruff, Playwright.

## Global Constraints

- Gałąź `feat/design-states-rules`; PR → CI (kolejka GitHuba bywa długa — przeczekać) → merge → wdrożenie → `curl -s https://flowmap.twapp.pl/przyklad | grep -c "Reguły decyzyjne"` z 0 na ≥ 1.
- Edycje: Write/Edit lub skrypt `.py` w scratchpadzie; bez heredoców z `\n`.
- Playwright: sekcje `classes, use_cases, sequences, states, rules`, oba motywy, 1440/390, 0 błędów JS, SVG bez „Syntax error” (dla `rules` — tabela `.decision-table`).
- Poprawki wyliczania stanów (`app/spec/derive.py`): „odrzucony” jest stanem końcowym; brak przejść ze stanu do niego samego. Szablony po zmianie: 0 uwag strażnika stanów.

---

### Task 1: Warunki przejść, poprawki wyliczania, strażnik stanów

**Interfaces:** `Transition.condition: str = PField(default="", max_length=300)`; kody `unreachable_status` (4), `dead_end_status` (3) → `SECTION_OF = "states"`.

- [ ] **Step 1: Failing tests** — `tests/test_design_states_rules.py`:

```python
from app.ai.templates import TEMPLATES, full_graph
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.schema import Spec, StateMachine, Status, Transition

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def test_transitions_carry_gateway_conditions_and_no_self_loops():
    sm = derive(full_graph("booking"), META).states[0]
    conds = {(t.from_status, t.to_status): t.condition for t in sm.transitions}
    assert conds[("nowy", "zatwierdzony")] == "Czy termin jest wolny? — tak"
    assert conds[("nowy", "odrzucony")] == "Czy termin jest wolny? — nie"
    assert all(t.from_status != t.to_status for t in sm.transitions)
    assert next(s for s in sm.statuses if s.name == "odrzucony").final


def test_state_guard():
    sm = StateMachine(key="st", entity="e", statuses=[Status(name="a", initial=True), Status(name="b"),
                                                      Status(name="c", final=True), Status(name="d")],
                      transitions=[Transition(from_status="a", to_status="b")])
    codes = {(i["code"], i["message"].split("„")[1].split("”")[0]) for i in lint(Spec(states=[sm]))}
    assert ("dead_end_status", "b") in codes  # reachable, not final, no exit
    assert ("unreachable_status", "c") in codes and ("unreachable_status", "d") in codes
    assert not any(c == ("unreachable_status", "a") for c in codes)


def test_templates_have_no_state_warnings():
    for key in TEMPLATES:
        spec = derive(full_graph(key), {"name": key, "start_sentence": "S"})
        bad = [i for i in lint(spec) if i["code"] in ("unreachable_status", "dead_end_status")]
        assert not bad, (key, bad)
```

- [ ] **Step 2:** FAIL (brak `condition`, brak kodów).
- [ ] **Step 3: Implementation**

`app/spec/schema.py` — w `Transition` po `to_status`: `condition: str = PField(default="", max_length=300)`.

`app/spec/derive.py` — w pętli stanów: dla gałęzi negatywnej `_add_status(statuses, name, final=True)`, a obie gałęzie dodają przejście tylko gdy `before != name`, z `condition=f"{n['title']} — {e['label']}"[:300]`:

```python
                if e["source"] == n["key"] and e.get("label"):
                    negative = bool(NEGATIVE_LABEL.match(e["label"]))
                    name = "odrzucony" if negative else "zatwierdzony"
                    _add_status(statuses, name, final=negative)
                    if before != name:
                        transitions.append(Transition(from_status=before, to_status=name, node_key=n["key"],
                                                      condition=f"{n['title']} — {e['label']}"[:300]))
                    if not negative:
                        current = name
```

`app/design/lint.py` — wagi `"unreachable_status": 4, "dead_end_status": 3`, `SECTION_OF` obu = `"states"`, przed `return issues`:

```python
    for sm in spec.states:
        nxt: dict[str, set[str]] = {}
        for t in sm.transitions:
            nxt.setdefault(t.from_status, set()).add(t.to_status)
        reach = {s.name for s in sm.statuses if s.initial}
        todo = list(reach)
        while todo:
            for b in nxt.get(todo.pop(), ()):
                if b not in reach:
                    reach.add(b)
                    todo.append(b)
        for s in sm.statuses:
            if reach and s.name not in reach:
                issues.append(_i("unreachable_status", f"Status „{s.name}” jest nieosiągalny ze stanu początkowego.",
                                 sm.key, "Do statusu nie prowadzi żadne przejście — rekord nigdy go nie osiągnie. "
                                 "Dodaj przejście albo usuń status."))
            elif not s.final and not nxt.get(s.name):
                issues.append(_i("dead_end_status", f"Status „{s.name}” nie ma wyjścia, a nie jest końcowy.", sm.key,
                                 "Rekord utknie w tym statusie na zawsze. Oznacz go jako końcowy albo dodaj "
                                 "przejście dalej."))
```

`app/spec/forms.py` — stany: `Transition(from_status=_col(r, 0), to_status=_col(r, 1), condition=_col(r, 2))`; `form_text`: `f"{t.from_status} | {t.to_status} | {t.condition}"`. `app/spec/routes.py` — etykieta pola: `"Przejścia: z | do | warunek"`.

- [ ] **Step 4:** `pytest tests/test_design_states_rules.py tests/test_spec_derive.py tests/test_spec_edit.py tests/test_spec_readiness.py` → zielone (jeśli `test_spec_derive` zakłada stary kształt stanów, popraw oczekiwanie tylko zgodnie z poprawkami wyżej).
- [ ] **Step 5:** commit „Stany: warunki przejść z bramek, odrzucony końcowy, strażnik statusów”.

---

### Task 2: Tabele decyzyjne (sekcja `rules`)

**Interfaces:** `RuleRow(condition: str, result: str)`, `Rule(Item)` z `name, inputs: list[str], rows: list[RuleRow]`; `"rules"` na końcu `SECTIONS`; `Spec.rules`; `rules(graph) -> list[Rule]` w `app/design/derive.py` (klucz `rule:<node_key>`); kody `rule_gap` (4), `rule_overlap` (4) → `SECTION_OF = "rules"`; formularz `name`, `inputs` (po przecinku), `rows` (`warunek | wynik`).

- [ ] **Step 1: Failing tests** (dopisz do `tests/test_design_states_rules.py`; `SAMPLE_FORM` w `tests/test_spec_edit.py` — narzędziem Edit):

```python
from app.design.derive import rules
from app.spec.schema import Rule, RuleRow


def test_rules_from_gateways():
    r = {x.key: x for x in rules(full_graph("booking"))}["rule:free"]
    assert r.name == "Czy termin jest wolny?" and r.node_key == "free"
    assert [(w.condition, w.result) for w in r.rows] == [("tak", "Klient podaje dane kontaktowe"),
                                                         ("nie", "Wybór terminu i specjalisty")]


def test_rule_guard_gap_and_overlap():
    def codes(rows):
        return {i["code"] for i in lint(Spec(rules=[Rule(key="r", name="R", rows=[RuleRow(condition=c, result="x")
                                                                                   for c in rows])]))}
    assert codes(["tak", "nie"]) == set()
    assert codes(["kwota > 1000", "inaczej"]) == set()
    assert "rule_gap" in codes(["kwota > 1000", "kwota < 100"])
    assert "rule_overlap" in codes(["VIP", "vip ", "inaczej"])
```

```python
    "rules": {"name": "R", "inputs": "kwota, klient", "rows": "kwota > 1000 | akceptacja kierownika\ninaczej | auto"},
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementation**

`app/spec/schema.py` (przed `class Proposal`; `SECTIONS` + `"rules"`; `Spec.rules: list[Rule] = []`):

```python
class RuleRow(BaseModel):
    condition: str = PField(min_length=1, max_length=200)
    result: str = PField(min_length=1, max_length=200)


class Rule(Item):
    name: str = PField(min_length=1, max_length=200)
    inputs: list[str] = []
    rows: list[RuleRow] = []
```

`app/design/derive.py`:

```python
def rules(graph: dict) -> list[Rule]:
    """One decision table per exclusive gateway: answer (edge label) → next step."""
    by_key = {n["key"]: n for n in graph["nodes"]}
    out = _out(graph)
    return [Rule(key=f"rule:{n['key']}", node_key=n["key"], name=n["title"][:200],
                 inputs=list(n.get("inputs", [])),
                 rows=[RuleRow(condition=(e.get("label") or "inaczej")[:200], result=by_key[e["target"]]["title"][:200])
                       for e in out.get(n["key"], []) if e["target"] in by_key])
            for n in graph["nodes"] if n["type"] == "decision"]
```

`app/spec/derive.py` — lokalny import `rules as derive_rules`, `Spec(..., rules=derive_rules(graph))`.

`app/design/lint.py`:

```python
ELSE = re.compile(r"^(inaczej|w przeciwnym (razie|wypadku)|pozostałe|else|default)\b", re.I)
```

(+ `import re`), wagi i `SECTION_OF`, przed `return issues`:

```python
    for r in spec.rules:
        conds = [w.condition.strip().lower() for w in r.rows]
        complete = any(ELSE.match(c) for c in conds) or {"tak", "nie"} <= set(conds)
        if not complete:
            issues.append(_i("rule_gap", f"Tabela „{r.name}” nie obejmuje wszystkich przypadków.", r.key,
                             "Gdy żaden warunek nie pasuje, system nie wie, co zrobić. Dodaj wiersz „inaczej” "
                             "albo uzupełnij warunki tak, by pokrywały wszystkie przypadki."))
        if len(set(conds)) < len(conds):
            issues.append(_i("rule_overlap", f"Tabela „{r.name}” ma powtórzony warunek.", r.key,
                             "Dwa wiersze z tym samym warunkiem mogą dać różne wyniki — reguła staje się "
                             "niejednoznaczna. Scal je albo doprecyzuj warunki."))
```

`app/spec/forms.py` — `PREFIX["rules"] = "rule"`; `item_from_form`:

```python
        if section == "rules":
            return Rule(**base, name=f("name"), inputs=[x.strip() for x in f("inputs").split(",") if x.strip()],
                        rows=[RuleRow(condition=_col(r, 0), result=_col(r, 1)) for r in _rows(f("rows"))])
```

`form_text`: `{"name": item.name, "inputs": ", ".join(item.inputs), "rows": "\n".join(f"{w.condition} | {w.result}" for w in item.rows)}`.

`app/spec/routes.py` — `SECTION_LABELS["rules"] = "Reguły"`, `FORM_FIELDS["rules"] = [("name", "Decyzja", "input"), ("inputs", "Dane wejściowe (po przecinku)", "input"), ("rows", "Wiersze: warunek | wynik (dodaj „inaczej | …” dla pozostałych przypadków)", "textarea")]`.

`app/templates/spec/_section.html` przed `nfr`:

```html
  {% elif section == 'rules' %}
    {% if item.inputs %}<p class="muted">Dane: {{ item.inputs|join(', ') }}</p>{% endif %}
    <div class="table-wrap"><table class="versions"><tr><th>Warunek</th><th>Wynik</th></tr>
      {% for w in item.rows %}<tr><td>{{ w.condition }}</td><td>{{ w.result }}</td></tr>{% endfor %}</table></div>
```

- [ ] **Step 4:** testy → zielone.
- [ ] **Step 5:** commit „Reguły biznesowe: tabele decyzyjne z bramek i strażnik luk/nakładania”.

---

### Task 3: Karta, UML.md, DATA_MODEL.md, eksport Markdown

**Interfaces:** `state_diagram(sm, spec) -> str` w `app/design/uml.py` (etykiety warunków); karta: sekcje `states` („Stany”), `rules` („Reguły”); dla `rules` zamiast Mermaid tabela `.decision-table`.

- [ ] **Step 1: Failing tests**:

```python
def test_state_diagram_and_documents():
    from app.design.uml import state_diagram, uml_md
    from app.export.builders import to_markdown
    from app.spec.package import data_model_md
    spec = derive(full_graph("booking"), META)
    out = state_diagram(spec.states[0], spec)
    assert out.startswith("stateDiagram-v2\n") and "S0 --> S1 : Czy termin jest wolny? — tak" in out
    assert "S0 --> S1 : Czy termin jest wolny? — tak" in data_model_md(spec)
    md = uml_md(META, spec)
    assert "## Stany" in md and "## Reguły biznesowe" in md and "| tak | Klient podaje dane kontaktowe |" in md
    assert "### Reguły decyzyjne" in to_markdown(META, full_graph("booking"))
```

(w `tests/test_design_routes.py`):

```python
def test_states_and_rules_sections(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    assert "stateDiagram-v2" in auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=states").get_data(as_text=True)
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=rules").get_data(as_text=True)
    assert "Reguły" in html and ("decision-table" in html or "Brak tabel decyzyjnych" in html)
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementation** — `app/design/uml.py`:

```python
def state_diagram(sm, spec: Spec) -> str:
    """UML state machine; transition labels are the gateway answers that cause them."""
    ids = {s.name: f"S{i}" for i, s in enumerate(sm.statuses)}
    out = ["stateDiagram-v2"] + [f"    {ids[s.name]} : {_seq_text(s.name)}" for s in sm.statuses]
    out += [f"    [*] --> {ids[s.name]}" for s in sm.statuses if s.initial]
    for t in sm.transitions:
        if t.from_status in ids and t.to_status in ids:
            label = f" : {_seq_text(t.condition)}" if t.condition else ""
            out.append(f"    {ids[t.from_status]} --> {ids[t.to_status]}{label}")
    out += [f"    {ids[s.name]} --> [*]" for s in sm.statuses if s.final]
    return "\n".join(out) + "\n"
```

`uml_md` — przed `## Diagram klas`:

```python
    names = {e.key: e.name for e in spec.entities}
    out += ["## Stany", ""]
    for sm in spec.states:
        out += [f"### {_md(names.get(sm.entity, sm.entity))}", "", "```mermaid", state_diagram(sm, spec).rstrip(),
                "```", ""]
    out += ["## Reguły biznesowe (tabele decyzyjne)", ""]
    for r in spec.rules:
        out += [f"### {_md(r.name)}", ""] + ([f"Dane: {_md(', '.join(r.inputs))}", ""] if r.inputs else [])
        out += ["| Warunek | Wynik |", "|---|---|"] + [f"| {_md(w.condition)} | {_md(w.result)} |" for w in r.rows]
        out.append("")
    if not spec.rules:
        out += ["- brak", ""]
```

(`names` już jest zdefiniowane w `uml_md` dla przypadków użycia — nazwij zmienną `entity_names`.)

`app/spec/package.py` — w `data_model_md` blok `for sm in spec.states:` zamień na użycie `state_diagram`:

```python
    for sm in spec.states:
        out += [f"## Statusy: {_md(_name(spec, sm.entity))}", "", "```mermaid", state_diagram(sm, spec).rstrip(),
                "```", ""]
```

(import `state_diagram` obok `uml_md`).

`app/design/routes.py` — `DESIGN_SECTIONS` + `"states": "Stany", "rules": "Reguły"`; `EDIT_SECTION` + `"states": "states", "rules": "rules"`; `HELP["states"] = "Diagram stanów UML: przez jakie statusy przechodzi rekord. Etykieta przejścia to warunek z bramki na mapie; [*] — początek i koniec."`, `HELP["rules"] = "Tabele decyzyjne (reguły biznesowe): dla każdej decyzji — warunek i wynik. Pełna tabela obejmuje wszystkie przypadki (np. wiersz „inaczej”)."`; w `_diagrams`: `if section == "states": return [state_diagram(sm, spec) for sm in spec.states] or [EMPTY "Brak statusów"]`, `if section == "rules": return []`.

`app/templates/design/view.html` — po pętli diagramów:

```html
      {% if section == 'rules' %}
        {% for r in spec.rules %}
        <div class="card table-wrap"><h3>{{ r.name }}</h3>
          {% if r.inputs %}<p class="muted">Dane: {{ r.inputs|join(', ') }}</p>{% endif %}
          <table class="versions decision-table"><tr><th>Warunek</th><th>Wynik</th></tr>
          {% for w in r.rows %}<tr><td>{{ w.condition }}</td><td>{{ w.result }}</td></tr>{% endfor %}</table></div>
        {% else %}<p class="muted">Brak tabel decyzyjnych — dodaj bramkę na mapie albo regułę w specyfikacji.</p>{% endfor %}
      {% endif %}
```

`app/export/builders.py` — w `to_markdown` po liście kroków sekcji 1 (przed `## 2. Role i uprawnienia`):

```python
    if spec.rules:
        out += ["", "### Reguły decyzyjne", ""]
        out += [f"- {_md(r.name)}: " + "; ".join(f"{_md(w.condition)} → {_md(w.result)}" for w in r.rows)
                for r in spec.rules]
```

- [ ] **Step 4:** `ruff check . && pytest -q -p no:warnings` → zielone.
- [ ] **Step 5:** commit „Projekt aplikacji: diagramy stanów z warunkami, tabele decyzyjne na karcie i w dokumentach”.

---

### Task 4: Weryfikacja i dowóz

- [ ] Playwright (`qa_uc.py` z sekcjami `states`, `rules`; dla `rules` czekaj na `.decision-table`, nie na SVG); zrzuty obejrzeć.
- [ ] PR „Projekt aplikacji (4/6): stany i reguły” → CI → merge → wdrożenie → `/przyklad` zawiera „Reguły decyzyjne”.
- [ ] Notatka w vaulcie.
