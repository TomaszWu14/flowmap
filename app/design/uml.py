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
