"""Spec → Mermaid text for the 'Projekt aplikacji' tab and UML.md. Pure functions, no database."""

import re

from ..export.builders import _md, _mm
from ..spec.schema import Spec
from .lint import lint

ARROWS = {"call": "->>", "reply": "-->>", "async": "-)", "error": "--x"}
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


def _seq_text(text: str) -> str:
    """Mermaid sequence text: ';' and '#' break the line parser."""
    return _mm(text).replace(";", ",").replace("#", "").strip() or "—"


def sequence_diagram(seq, spec: Spec) -> str:
    """UML sequence diagram; error messages right after a call/reply become the 'else' branches of an alt block."""
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
            out += [f"    alt {_seq_text(m.text)}", f"        {line}"]
            for e in errors:
                out += [f"    else {_seq_text(e.text)}",
                        f"        {ids[e.source]}{ARROWS['error']}{ids[e.target]}: {_seq_text(e.text)}"]
            out.append("    end")
        else:
            out.append(f"    {line}")
        i += 1 + len(errors)
    return "\n".join(out) + "\n"


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
    out += ["## Sekwencje", ""]
    for s in spec.sequences:
        out += [f"### {_md(s.name)}", "", "```mermaid", sequence_diagram(s, spec).rstrip(), "```", ""]
    if not spec.sequences:
        out += ["- brak", ""]
    out += ["## Diagram klas", "", "```mermaid", class_diagram(spec).rstrip(), "```", "", "## Uwagi strażnika UML", ""]
    out += [f"- {_md(i['message'])} — {_md(i['why'])}" for i in lint(spec)] or ["- brak"]
    return "\n".join(out) + "\n"
