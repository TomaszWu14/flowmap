# Projekt aplikacji z mapy — PR 3: diagramy sekwencji Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagram sekwencji ścieżki głównej wyliczany z mapy (tory = uczestnicy, integracje = wywołanie + odpowiedź + błąd w bloku `alt`, powiadomienia = komunikaty asynchroniczne), edytowalny w specyfikacji, ze strażnikiem, w `UML.md` i w eksporcie Markdown.

**Architecture:** Jak PR 2: sekcja `sequences` w `Spec` (`Sequence`, `Message`), wyliczanie w `app/design/derive.py`, Mermaid w `app/design/uml.py`, reguły w `app/design/lint.py`, karta pokazuje listę diagramów (jedna sekwencja = jeden diagram).

**Tech Stack:** Flask, Jinja, HTMX, Pydantic, Mermaid 11 (`sequenceDiagram`), pytest, ruff, Playwright.

Projekt: `docs/superpowers/specs/2026-10-19-projekt-aplikacji-z-mapy-design.md`. Poprzednie: `…-pr1.md`, `…-pr2.md`.

## Global Constraints

- Gałąź `feat/design-sequences`; PR → zielone CI → merge → wdrożenie Coolify → produkcja: `curl -s https://flowmap.twapp.pl/przyklad | grep -c "Sekwencja (ścieżka główna)"` z 0 na ≥ 1.
- Edycje: Write/Edit lub skrypt `.py` w scratchpadzie (`newline=""`); bez heredoców z `\n`.
- Playwright: oba motywy, 1440 i 390 px, sekcje `classes`, `use_cases`, `sequences`, `<svg>` bez „Syntax error”, 0 błędów JS; pełna mapa przez `g.load_graph(p, full_graph("booking"))`; czekanie pętlą `page.evaluate` (CSP).

## Struktura plików

- Modify `app/spec/schema.py` — `Message`, `Sequence`, `MESSAGE_KINDS`, `Spec.sequences`, `SECTIONS`.
- Modify `app/design/derive.py` — `sequences(graph, meta) -> list[Sequence]`; `app/spec/derive.py` — `Spec(..., sequences=...)`.
- Modify `app/spec/forms.py`, `app/spec/routes.py`, `app/templates/spec/_section.html` — edycja.
- Modify `app/design/uml.py` — `sequence_diagram(seq, spec)`, sekcja w `uml_md`.
- Modify `app/design/lint.py` — `integration_without_error_message`, `idle_participant`.
- Modify `app/design/routes.py`, `app/templates/design/view.html` — lista diagramów.
- Modify `app/export/builders.py` — podsekcja „Sekwencja (ścieżka główna)” w `to_markdown`.
- Tests: `tests/test_design_sequences.py` (nowy), `tests/test_spec_edit.py`, `tests/test_design_routes.py`.

---

### Task 1: Schemat i wyliczanie sekwencji

**Interfaces:**
- Produces: `Message(source: str, target: str, text: str, kind: Literal["call","reply","async","error"] = "call")`; `Sequence(Item)` z `name, participants: list[str], messages: list[Message]`; `MESSAGE_KINDS` (etykiety PL); `"sequences"` na końcu `SECTIONS`; `sequences(graph, meta) -> list[Sequence]` (klucz `seq:main`).

- [ ] **Step 1: Failing test** — `tests/test_design_sequences.py`:

```python
from app.ai.templates import TEMPLATES, full_graph
from app.design.derive import sequences
from app.spec.derive import derive

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def seq():
    return sequences(full_graph("booking"), META)[0]


def test_main_sequence_participants_and_messages():
    s = seq()
    assert s.key == "seq:main" and s.name == "Ścieżka główna: Klient chce umówić wizytę"
    assert s.participants == ["Klient", "Płatność online", "System"]
    msgs = [(m.source, m.target, m.kind, m.text) for m in s.messages]
    assert ("Klient", "Klient", "call", "Wybór usługi") in msgs
    assert ("Klient", "Płatność online", "call", "Kwota, Metoda płatności") in msgs
    assert ("Płatność online", "Klient", "reply", "Status płatności") in msgs
    assert ("Płatność online", "Klient", "error", "brak płatności") in msgs
    assert ("System", "Klient", "async", "Wysłanie potwierdzenia rezerwacji") in msgs
    kinds = [m.kind for m in s.messages]
    assert kinds.index("reply") + 1 == kinds.index("error")  # error right after the reply → alt block


def test_every_template_has_a_sequence_without_idle_participants():
    for key in TEMPLATES:
        spec = derive(full_graph(key), {"name": key, "start_sentence": "Start"})
        assert spec.sequences, key
        used = {p for m in spec.sequences[0].messages for p in (m.source, m.target)}
        assert set(spec.sequences[0].participants) == used, key
```

- [ ] **Step 2:** `python -m pytest tests/test_design_sequences.py -q -p no:warnings` → FAIL (`ImportError: cannot import name 'sequences'`).

- [ ] **Step 3: Implementation**

`app/spec/schema.py` (przed `class Proposal`; `SECTIONS` + `"sequences"` na końcu; w `Spec` po `use_cases`: `sequences: list[Sequence] = []`):

```python
MESSAGE_KINDS = {"call": "wywołanie", "reply": "odpowiedź", "async": "asynchronicznie", "error": "błąd"}


class Message(BaseModel):
    source: str = PField(min_length=1, max_length=100)
    target: str = PField(min_length=1, max_length=100)
    text: str = PField(min_length=1, max_length=300)
    kind: Literal["call", "reply", "async", "error"] = "call"


class Sequence(Item):
    name: str = PField(min_length=1, max_length=200)
    participants: list[str] = []
    messages: list[Message] = []
```

`app/design/derive.py` — import `from ..spec.derive import NOTIFY, slug` i `Message, Sequence` ze schematu; dopisz:

```python
def sequences(graph: dict, meta: dict) -> list[Sequence]:
    """Main path as one sequence: hand-offs between lanes, integration call/reply/error, async notifications."""
    by_key = {n["key"]: n for n in graph["nodes"]}
    lanes = {k: v or "" for k, v in assign(graph).items()}
    main = main_path(graph)
    if not main:
        return []
    who = lambda k: lanes[k] or SYSTEM  # noqa: E731
    human = lambda lane: lane and slug(lane) != slug(SYSTEM)  # noqa: E731
    parts: list[str] = []
    msgs: list[Message] = []

    def add(src, dst, text, kind="call"):
        src, dst = src[:100], dst[:100]
        parts.extend(p for p in (src, dst) if p not in parts)
        msgs.append(Message(source=src, target=dst, text=(text or "—")[:300], kind=kind))

    prev = who(main[0])
    last_human = prev if human(prev) else ""
    for k in main:
        n = by_key[k]
        if n["type"] in FLOW:
            continue
        me = who(k)
        if n["type"] == "integration":
            ext = n["title"]
            add(me, ext, ", ".join(n.get("inputs", [])) or "żądanie")
            add(ext, me, ", ".join(n.get("outputs", [])) or "wynik", "reply")
            for e in graph["edges"]:
                if e["source"] == k and e.get("condition") == "error":
                    add(ext, me, e.get("label") or "błąd", "error")
        elif n["type"] == "automation" and NOTIFY.search(n["title"]):
            add(SYSTEM, last_human or me, n["title"], "async")
        else:
            add(prev, me, n["title"])
        prev = me
        if human(me):
            last_human = me
    return [Sequence(key="seq:main", name=f"Ścieżka główna: {meta.get('start_sentence') or meta.get('name', '')}"[:200],
                     participants=parts, messages=msgs)]
```

`app/spec/derive.py`: lokalny import rozszerz do `from ..design.derive import sequences as derive_sequences, use_cases as derive_use_cases` (dwie linie, ruff I001) i dopisz `sequences=derive_sequences(graph, meta)` do `Spec(...)`.

- [ ] **Step 4:** test → 2 passed; pełny `pytest` może pokazać tylko `test_form_round_trip_every_section` (formularz w Task 2).
- [ ] **Step 5:** commit „Projekt aplikacji: sekwencja ścieżki głównej wyliczana z mapy”.

---

### Task 2: Edycja w specyfikacji

**Interfaces:** formularz sekcji `sequences`: `name`, `participants` (uczestnik w linii), `messages` (`od | do | tekst | call/reply/async/error`).

- [ ] **Step 1: Failing test** — w `tests/test_spec_edit.py` do `SAMPLE_FORM` (edytuj narzędziem Edit, nie heredokiem):

```python
    "sequences": {"name": "S", "participants": "A\nB",
                  "messages": "A | B | zamów | call\nB | A | ok | reply\nB | A | brak | error"},
```

- [ ] **Step 2:** `pytest tests/test_spec_edit.py` → FAIL (`KeyError: 'sequences'`).
- [ ] **Step 3: Implementation** — `app/spec/forms.py`: import `Message, Sequence, MESSAGE_KINDS`; `PREFIX["sequences"] = "seq"`; w `item_from_form`:

```python
        if section == "sequences":
            for r in _rows(f("messages")):
                if _col(r, 3, "call") not in MESSAGE_KINDS:
                    raise ValueError(f"nieznany rodzaj komunikatu „{_col(r, 3)}”. Dozwolone: {', '.join(MESSAGE_KINDS)}.")
            return Sequence(**base, name=f("name"), participants=[r[0] for r in _rows(f("participants"))],
                            messages=[Message(source=_col(r, 0), target=_col(r, 1), text=_col(r, 2),
                                              kind=_col(r, 3, "call")) for r in _rows(f("messages"))])
```

w `form_text`:

```python
    if section == "sequences":
        return {"name": item.name, "participants": "\n".join(item.participants),
                "messages": "\n".join(f"{m.source} | {m.target} | {m.text} | {m.kind}" for m in item.messages)}
```

`app/spec/routes.py`: `SECTION_LABELS["sequences"] = "Sekwencje"`; `FORM_FIELDS["sequences"] = [("name", "Nazwa", "input"), ("participants", "Uczestnicy (po jednym w linii)", "textarea"), ("messages", "Komunikaty: od | do | tekst | call/reply/async/error (wywołanie, odpowiedź, asynchronicznie, błąd)", "textarea")]`; do `_context` dodaj `"message_kinds": MESSAGE_KINDS` (import ze `.schema`).

`app/templates/spec/_section.html` przed `{% elif section == 'nfr' %}`:

```html
  {% elif section == 'sequences' %}
    <p>{% for p in item.participants %}<span class="badge">{{ p }}</span> {% endfor %}</p>
    <ol>{% for m in item.messages %}<li>{{ m.source }} → {{ m.target }}: {{ m.text }} <span class="muted">({{ message_kinds[m.kind] }})</span></li>{% endfor %}</ol>
```

- [ ] **Step 4:** `pytest tests/test_spec_edit.py tests/test_spec_routes.py` → zielone.
- [ ] **Step 5:** commit „Specyfikacja: edycja sekwencji”.

---

### Task 3: Strażnik sekwencji

**Interfaces:** kody `integration_without_error_message` (4), `idle_participant` (2) w `WEIGHTS`, oba w `SECTION_OF` jako `"sequences"`.

- [ ] **Step 1: Failing test** (do `tests/test_design_sequences.py`):

```python
from app.design.lint import lint
from app.spec.schema import Integration, Message, Sequence, Spec


def test_sequence_guard():
    spec = Spec(integrations=[Integration(key="i", name="Bank")],
                sequences=[Sequence(key="s", name="S", participants=["A", "Bank", "Nikt"],
                                    messages=[Message(source="A", target="Bank", text="przelew")])])
    codes = {(i["code"], i["target_key"]) for i in lint(spec)}
    assert ("integration_without_error_message", "s") in codes and ("idle_participant", "s") in codes
    spec.sequences[0].messages.append(Message(source="Bank", target="A", text="odmowa", kind="error"))
    spec.sequences[0].participants.remove("Nikt")
    assert not [c for c in lint(spec) if c["target_key"] == "s"]
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** w `lint.py` dopisz wagi i `SECTION_OF`, a przed `return issues`:

```python
    integrations = {i.name for i in spec.integrations}
    for s in spec.sequences:
        used = {p for m in s.messages for p in (m.source, m.target)}
        for p in s.participants:
            if p not in used:
                issues.append(_i("idle_participant", f"Uczestnik „{p}” w sekwencji „{s.name}” nie ma komunikatów.",
                                 s.key, "Uczestnik bez komunikatów nic nie wnosi do scenariusza — usuń go albo "
                                 "dopisz, z kim się komunikuje."))
        for p in s.participants:
            called = any(m.target == p and m.kind == "call" for m in s.messages)
            failed = any(m.source == p and m.kind == "error" for m in s.messages)
            if p in integrations and called and not failed:
                issues.append(_i("integration_without_error_message", f"Wywołanie „{p}” w sekwencji „{s.name}” "
                                 "nie ma ścieżki błędu.", s.key,
                                 "System zewnętrzny może nie odpowiedzieć albo odmówić — pokaż w sekwencji, "
                                 "co wtedy dzieje się z procesem (blok alt)."))
```

- [ ] **Step 4:** `pytest tests/test_design_sequences.py tests/test_design_lint.py tests/test_spec_readiness.py` → zielone.
- [ ] **Step 5:** commit „Strażnik UML: integracja bez ścieżki błędu, bezczynny uczestnik”.

---

### Task 4: Diagram, karta, UML.md, eksport Markdown

**Interfaces:** `sequence_diagram(seq: Sequence, spec: Spec) -> str` (zaczyna się od `sequenceDiagram\n`); karta dostaje w kontekście `diagrams: list[str]` zamiast `diagram`.

- [ ] **Step 1: Failing tests** — do `tests/test_design_sequences.py`:

```python
from app.design.uml import sequence_diagram, uml_md


def test_sequence_diagram_mermaid():
    spec = derive(full_graph("booking"), META)
    out = sequence_diagram(spec.sequences[0], spec)
    assert out.startswith("sequenceDiagram\n")
    assert "actor P0 as Klient" in out and "participant P1 as Płatność online" in out
    assert "P0->>P1: Kwota, Metoda płatności" in out and "P1-->>P0: Status płatności" in out
    assert "alt" in out and "else brak płatności" in out and "P1--xP0: brak płatności" in out
    assert "P2-)P0: Wysłanie potwierdzenia rezerwacji" in out


def test_sequence_in_uml_md_and_markdown_export():
    from app.export.builders import to_markdown
    assert "## Sekwencje" in uml_md(META, derive(full_graph("booking"), META))
    md = to_markdown(META, full_graph("booking"))
    assert "### Sekwencja (ścieżka główna)" in md and "Klient → Płatność online: Kwota, Metoda płatności" in md
```

do `tests/test_design_routes.py`:

```python
def test_sequences_section_on_design_tab(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=sequences").get_data(as_text=True)
    assert "sequenceDiagram" in html and "Sekwencje" in html
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementation** — `app/design/uml.py`:

```python
ARROWS = {"call": "->>", "reply": "-->>", "async": "-)", "error": "--x"}


def _seq_text(text: str) -> str:
    """Mermaid sequence text: ';' and '#' break the line parser."""
    return _mm(text).replace(";", ",").replace("#", "").strip() or "—"


def sequence_diagram(seq, spec: Spec) -> str:
    humans = {r.name for r in spec.roles}
    ids = {p: f"P{i}" for i, p in enumerate(seq.participants)}
    out = ["sequenceDiagram"]
    out += [f"    {'actor' if p in humans else 'participant'} {ids[p]} as {_seq_text(p)}" for p in seq.participants]
    msgs = [m for m in seq.messages if m.source in ids and m.target in ids]
    i = 0
    while i < len(msgs):
        m = msgs[i]
        errors = []
        while m.kind != "error" and i + 1 + len(errors) < len(msgs) and msgs[i + 1 + len(errors)].kind == "error":
            errors.append(msgs[i + 1 + len(errors)])
        line = f"{ids[m.source]}{ARROWS[m.kind]}{ids[m.target]}: {_seq_text(m.text)}"
        if errors:
            out.append(f"    alt {_seq_text(m.text)}")
            out.append(f"        {line}")
            for e in errors:
                out += [f"    else {_seq_text(e.text)}",
                        f"        {ids[e.source]}{ARROWS['error']}{ids[e.target]}: {_seq_text(e.text)}"]
            out.append("    end")
        else:
            out.append(f"    {line}")
        i += 1 + len(errors)
    return "\n".join(out) + "\n"
```

W `uml_md` przed `## Diagram klas`:

```python
    out += ["## Sekwencje", ""]
    for s in spec.sequences:
        out += [f"### {_md(s.name)}", "", "```mermaid", sequence_diagram(s, spec).rstrip(), "```", ""]
    if not spec.sequences:
        out += ["- brak", ""]
```

`app/design/routes.py`: `DESIGN_SECTIONS["sequences"] = "Sekwencje"`, `EDIT_SECTION["sequences"] = "sequences"`, `HELP["sequences"] = "Diagram sekwencji UML: kto komu i w jakiej kolejności przekazuje sprawę. Pełna strzałka — wywołanie, przerywana — odpowiedź, otwarta — komunikat asynchroniczny, krzyżyk — błąd; blok alt pokazuje ścieżkę błędu."`; `_diagram` zamień na `_diagrams(section, spec, project) -> list[str]`:

```python
def _diagrams(section, spec, project) -> list[str]:
    if section == "sequences":
        return [sequence_diagram(s, spec) for s in spec.sequences] or ['flowchart LR\n    EMPTY["Brak sekwencji"]\n']
    if section == "use_cases":
        return [use_case_diagram(spec, project.name)]
    return [class_diagram(spec)]
```

w `view`: `"diagrams": []` w `ctx` i `ctx.update(diagrams=_diagrams(section, spec, project), …)`.

`app/templates/design/view.html` — zamiast jednego `<figure>`:

```html
      {% for d in diagrams %}
      <figure class="card design-preview" aria-label="Podgląd diagramu">
        <pre class="mermaid" data-source="{{ d }}">{{ d }}</pre>
      </figure>
      {% endfor %}
```

`app/export/builders.py` — w `to_markdown`, na końcu sekcji 5 (po `out.append("- brak")` dla `notif`):

```python
    if spec.sequences:
        out += ["", "### Sekwencja (ścieżka główna)", ""]
        out += [f"{i}. {_md(m.source)} → {_md(m.target)}: {_md(m.text)}"
                for i, m in enumerate(spec.sequences[0].messages, 1)]
```

- [ ] **Step 4:** `ruff check . && python -m pytest -q -p no:warnings` → zielone.
- [ ] **Step 5:** commit „Projekt aplikacji: diagram sekwencji z blokiem alt, UML.md i eksport Markdown”.

---

### Task 5: Weryfikacja i dowóz

- [ ] Playwright (`qa_uc.py` + sekcja `sequences`): SVG, brak „Syntax error”, oba motywy, 1440/390, 0 błędów JS; obejrzeć zrzut sekwencji (czytelność bloku `alt`).
- [ ] PR „Projekt aplikacji (3/6): diagramy sekwencji” → CI → merge → wdrożenie → `/przyklad` zawiera „Sekwencja (ścieżka główna)”.
- [ ] Notatka FlowMap w vaulcie.
