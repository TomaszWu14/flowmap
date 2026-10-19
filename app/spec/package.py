"""Deterministic Claude Code package: Markdown files for docs/flowmap/ in the target repo."""

import io
import json
import zipfile

from ..design.uml import state_diagram, uml_md
from ..export.builders import FORMAT, _md, _mm, _test_paths, to_mermaid
from ..flow.guard import report
from .readiness import readiness
from .schema import CHANNEL_LABELS, DIRECTION_LABELS, FIELD_TYPE_LABELS, NFR_LABELS, PERM_LABELS, Spec

ZIP_DATE = (2026, 1, 1, 0, 0, 0)
PASTE_PROMPT = ("Rozpakowałem specyfikację do docs/flowmap/. Przeczytaj docs/flowmap/CLAUDE.md i realizuj kroki z "
                "sekcji „Kolejność budowy” po kolei. Po każdym kroku uruchom testy odpowiadające scenariuszom z "
                "docs/flowmap/ACCEPTANCE.md. Niejasności rozstrzygaj najprostszym założeniem i dopisuj je do "
                "docs/flowmap/OPEN_QUESTIONS.md.")
STACK_TYPES = {"text": "VARCHAR(255)", "long_text": "TEXT", "integer": "INTEGER", "decimal": "NUMERIC(12,4)",
               "money": "NUMERIC(12,2) + waluta", "boolean": "BOOLEAN", "date": "DATE", "datetime": "TIMESTAMP",
               "email": "VARCHAR(255) + walidacja e-mail", "phone": "VARCHAR(32) + walidacja", "enum": "ENUM / CHECK",
               "file": "ścieżka do pliku + metadane", "reference": "klucz obcy"}
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def image_path(att) -> str:
    return f"images/{att.id}.{EXT.get(att.mime, 'bin')}"


def _img(att) -> str:
    return f"![{_md(att.caption or att.filename)}]({image_path(att)})"


def _name(spec: Spec, key: str) -> str:
    _sec, item = spec.find(key)
    return getattr(item, "name", key) if item else key


def claude_md(meta, spec: Spec) -> str:
    out = [f"# {_md(meta['name'])} — instrukcja dla Claude Code", "",
           f"Proces: „{_md(meta['start_sentence'])}”. Specyfikacja: `SPEC.md`, model danych: `DATA_MODEL.md`, "
           "przypadki użycia i diagramy UML: `UML.md`, testy akceptacyjne: `ACCEPTANCE.md`, "
           "wątpliwości: `OPEN_QUESTIONS.md`.", "",
           f"Stos: {_md(spec.stack) if spec.stack else 'dobierz prosty, popularny stos i uzasadnij w README'}.", "",
           "## Kolejność budowy", "",
           "1. Model danych i migracje z `DATA_MODEL.md` (typy, wymagalność, walidacje, relacje).",
           "2. Logowanie i role z macierzą uprawnień z `SPEC.md` — sprawdzaj uprawnienia na serwerze.",
           "3. Ekrany w kolejności procesu z `SPEC.md` (pola, akcje, walidacja); kto co robi i co przy "
           "wyjątkach — przypadki użycia z `UML.md`.",
           "4. Statusy i przejścia (maszyny stanów z `DATA_MODEL.md`) — odrzucaj niedozwolone przejścia.",
           "5. Powiadomienia i integracje za interfejsem z atrapą w testach.",
           "6. Testy z `ACCEPTANCE.md` (każdy scenariusz = co najmniej jeden test).", "",
           "## Definition of Done", "",
           "- Wszystkie scenariusze z `ACCEPTANCE.md` mają testy i przechodzą.",
           "- Uprawnienia zgodne z macierzą; brak dostępu = 403/404.",
           "- Nie wymyślaj funkcji spoza specyfikacji. Niejasne rzeczy rozstrzygnij najprostszym założeniem "
           "i dopisz do `OPEN_QUESTIONS.md`."]
    if spec.stack:
        out += ["", "## Odwzorowanie typów", "", "| Typ | Proponowany typ w bazie |", "|---|---|"]
        out += [f"| {FIELD_TYPE_LABELS[t]} | {v} |" for t, v in STACK_TYPES.items()]
    return "\n".join(out) + "\n"


def images_md(graph, images: list) -> list[str]:
    if not images:
        return []
    titles = {n["key"]: n["title"] for n in graph["nodes"]}
    out = ["", "## Grafiki", "", "Zrzuty ekranów, zdjęcia stanowisk i skany dołączone do mapy (pliki w `images/`).", ""]
    groups = [("", "Materiały projektu")] + [(k, f"Krok: {titles[k]}") for k in titles]
    for key, label in groups:
        atts = [a for a in images if a.node_key == key]
        if atts:
            out += [f"### {_md(label)}", ""] + [f"- {_img(a)}" for a in atts] + [""]
    return out


def spec_md(meta, graph, spec: Spec, images: list = ()) -> str:
    out = [f"# Specyfikacja: {_md(meta['name'])}", "", "## Proces", "", "```mermaid", to_mermaid(graph).rstrip(),
           "```", "", "## Role i uprawnienia", "", "| Rola | Encja | Odczyt | Tworzenie | Edycja | Usuwanie |",
           "|---|---|---|---|---|---|"]
    for r in spec.roles:
        for ent, p in sorted(r.permissions.items()):
            out.append(f"| {_md(r.name)} | {_md(_name(spec, ent))} | " +
                       " | ".join(PERM_LABELS[p[k]] for k in ("read", "create", "update", "delete")) + " |")
    out += ["", "## Ekrany", ""]
    for s in spec.screens:
        out += [f"### {_md(s.name)}", f"- Rola: {_md(_name(spec, s.role)) if s.role else '—'}"]
        out += [f"- Pole: {_md(f.name)} ({FIELD_TYPE_LABELS[f.type]})" for f in s.fields]
        out += [f"- Akcja: {_md(a)}" for a in s.actions]
        out += [f"- Grafika: {_img(a)}" for a in images if s.node_key and a.node_key == s.node_key] + [""]
    out += ["## Powiadomienia", ""] + [
        f"- {_md(n.trigger)} → {CHANNEL_LABELS[n.channel]}, do: {_md(_name(spec, n.recipient_role))}"
        for n in spec.notifications] + [""]
    out += ["## Integracje", ""] + [
        f"- {_md(i.name)} ({DIRECTION_LABELS[i.direction]}); dane: {_md(', '.join(i.data)) or '—'}; "
        f"przy błędzie: {_md(i.on_error) or '—'}" for i in spec.integrations] + [""]
    out += ["## Wymagania niefunkcjonalne", ""] + [f"- [{NFR_LABELS[n.category]}] {_md(n.text)}" for n in spec.nfr]
    out += images_md(graph, images)
    return "\n".join(out) + "\n"


def data_model_md(spec: Spec) -> str:
    out = ["# Model danych", ""]
    for e in spec.entities:
        out += [f"## {_md(e.name)}", "", "| Pole | Typ | Wymagane | Walidacja |", "|---|---|---|---|"]
        for f in e.fields:
            typ = FIELD_TYPE_LABELS[f.type] + (f" ({_md(', '.join(f.enum_values))})" if f.enum_values else "")
            typ += f" → {_md(_name(spec, f.ref_entity))}" if f.ref_entity else ""
            out.append(f"| {_md(f.name)}{' (id)' if f.is_identifier else ''} | {typ} | "
                       f"{'tak' if f.required else ''} | {_md(f.validation)} |")
        out.append("")
    out += ["## Diagram ER", "", "```mermaid", "erDiagram"]
    ids = {e.key: f"E{i}" for i, e in enumerate(spec.entities)}
    for e in spec.entities:
        out.append(f'    {ids[e.key]}["{_mm(e.name)}"] {{')
        out += [f"        {f.type} f{j}" for j, f in enumerate(e.fields)] + ["    }"]
        for r in e.relations:
            if r.to_entity in ids:
                card = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}[r.kind]
                out.append(f'    {ids[e.key]} {card} {ids[r.to_entity]} : "{_mm(r.label or r.kind)}"')
    out += ["```", ""]
    for sm in spec.states:
        out += [f"## Statusy: {_md(_name(spec, sm.entity))}", "", "```mermaid", state_diagram(sm, spec).rstrip(),
                "```", ""]
    return "\n".join(out) + "\n"


def acceptance_md(graph, spec: Spec) -> str:
    by_key = {n["key"]: n for n in graph["nodes"]}
    out = ["# Testy akceptacyjne", "", "## Ekrany", ""]
    for s in spec.screens:
        out.append(f"### {_md(s.name)}")
        out += [f"- [ ] Pole „{_md(f.name)}” ({FIELD_TYPE_LABELS[f.type]}) jest walidowane" for f in s.fields]
        out.append(f"- [ ] Dostęp ma tylko rola: {_md(_name(spec, s.role)) if s.role else 'do ustalenia'}")
        out.append("")
    out += ["## Scenariusze", ""]
    for i, path in enumerate(_test_paths(graph), 1):
        steps = [by_key[k] for k in path]
        out += [f"### Scenariusz {i}", f"- **Zakładając**, że {_md(steps[0]['title'])}",
                *[f"- **Gdy** {_md(n['title'])}" for n in steps[1:-1]],
                f"- **Wtedy** {_md(steps[-1]['title'])}", ""]
    return "\n".join(out) + "\n"


def open_questions_md(graph, spec: Spec, open_comments: list[str]) -> str:
    items = [i["message"] for i in report(graph)["issues"]] + [i["message"] for i in readiness(spec)["issues"]]
    items += [f"Komentarz: {c}" for c in open_comments]
    return "# Otwarte pytania\n\n" + ("\n".join(f"- {_md(x)}" for x in items) or "- brak") + "\n"


def build_files(meta: dict, graph: dict, spec: Spec, open_comments: list[str],
                images: list = ()) -> dict[str, str | bytes]:
    """images: Attachment rows of the project; each is packed as images/<id>.<ext> and linked from SPEC.md."""
    data = {"format": FORMAT, "project": meta, "nodes": graph["nodes"], "edges": graph["edges"],
            "spec": spec.model_dump(mode="json")}
    return {"CLAUDE.md": claude_md(meta, spec), "SPEC.md": spec_md(meta, graph, spec, images),
            "DATA_MODEL.md": data_model_md(spec), "UML.md": uml_md(meta, spec),
            "ACCEPTANCE.md": acceptance_md(graph, spec),
            "OPEN_QUESTIONS.md": open_questions_md(graph, spec, open_comments),
            "flowmap.json": json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            **{image_path(a): a.data for a in images}}


def build_zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(f"docs/flowmap/{name}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            body = files[name]
            zf.writestr(info, body.encode("utf-8") if isinstance(body, str) else body)
    return buf.getvalue()
