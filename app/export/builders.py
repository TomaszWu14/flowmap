"""Exports built from a graph dict: Markdown spec, Mermaid, BPMN 2.0, generator prompt, project JSON."""

import re
import xml.etree.ElementTree as ET
from collections import deque

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..ai.rules import needs_error_path
from ..flow.guard import report
from ..flow.simulate import dead_ends
from ..models import NODE_TYPE_LABELS, NODE_TYPES

FORMAT = "flowmap/2"
ACCEPTED_FORMATS = ("flowmap/1", "flowmap/2")


def _ordered(graph: dict) -> list[dict]:
    """Nodes in walk order from the start (unreachable ones last)."""
    by_key = {n["key"]: n for n in graph["nodes"]}
    children: dict[str, list[str]] = {}
    for e in graph["edges"]:
        children.setdefault(e["source"], []).append(e["target"])
    queue = deque(n["key"] for n in graph["nodes"] if n["type"] == "start")
    seen: list[str] = []
    while queue:
        k = queue.popleft()
        if k in seen or k not in by_key:
            continue
        seen.append(k)
        queue.extend(children.get(k, []))
    return [by_key[k] for k in seen] + [n for n in graph["nodes"] if n["key"] not in seen]


# --- Mermaid ---------------------------------------------------------------

def _mm(text: str) -> str:
    return text.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;").replace("\n", " ")


MERMAID_SHAPES = {
    "start": ('(["', '"])'), "end": ('(["', '"])'), "decision": ('{"', '"}'),
    "screen": ('["', '"]'), "user_action": ('("', '")'), "automation": ('[["', '"]]'),
    "integration": ('[/"', '"/]'), "wait": ('(("', '"))'),
}


def to_mermaid(graph: dict) -> str:
    ids = {n["key"]: f"n{i}" for i, n in enumerate(_ordered(graph))}
    lines = ["flowchart TD"]
    for n in _ordered(graph):
        left, right = MERMAID_SHAPES[n["type"]]
        actor = f"<br/>({_mm(n['actor'])})" if n.get("actor") else ""
        lines.append(f"    {ids[n['key']]}{left}{_mm(n['title'])}{actor}{right}")
    for e in graph["edges"]:
        if e["source"] in ids and e["target"] in ids:
            arrow = f'-->|"{_mm(e["label"])}"|' if e.get("label") else "-->"
            lines.append(f"    {ids[e['source']]} {arrow} {ids[e['target']]}")
    for t in NODE_TYPES:
        members = [ids[n["key"]] for n in graph["nodes"] if n["type"] == t]
        if members:
            lines.append(f"    class {','.join(members)} {t}")
    lines += [
        "    classDef start fill:#d3f9d8,stroke:#2b8a3e", "    classDef end fill:#ffe3e3,stroke:#c92a2a",
        "    classDef decision fill:#fff3bf,stroke:#e67700", "    classDef screen fill:#e7f5ff,stroke:#1971c2",
    ]
    return "\n".join(lines) + "\n"


# --- BPMN 2.0 ----------------------------------------------------------------

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
BPMN_TAGS = {
    "start": "startEvent", "end": "endEvent", "decision": "exclusiveGateway", "user_action": "userTask",
    "screen": "userTask", "automation": "serviceTask", "integration": "serviceTask",
    "wait": "intermediateCatchEvent",
}
SIZES = {"startEvent": (36, 36), "endEvent": (36, 36), "intermediateCatchEvent": (36, 36),
         "exclusiveGateway": (50, 50)}


def _levels(graph: dict) -> dict[str, tuple[int, int]]:
    """Simple BFS layering for the diagram (column = depth, row = order within depth)."""
    depth: dict[str, int] = {}
    children: dict[str, list[str]] = {}
    for e in graph["edges"]:
        children.setdefault(e["source"], []).append(e["target"])
    queue = deque((n["key"], 0) for n in graph["nodes"] if n["type"] == "start")
    while queue:
        k, d = queue.popleft()
        if k in depth:
            continue
        depth[k] = d
        queue.extend((c, d + 1) for c in children.get(k, []))
    next_col = max(depth.values(), default=-1) + 1
    for n in graph["nodes"]:
        depth.setdefault(n["key"], next_col)
    rows: dict[int, int] = {}
    pos = {}
    for n in graph["nodes"]:
        col = depth[n["key"]]
        pos[n["key"]] = (col, rows.get(col, 0))
        rows[col] = rows.get(col, 0) + 1
    return pos


def to_bpmn(graph: dict, name: str) -> str:
    ET.register_namespace("bpmn", BPMN)
    ET.register_namespace("bpmndi", BPMNDI)
    ET.register_namespace("dc", DC)
    ET.register_namespace("di", DI)
    defs = ET.Element(f"{{{BPMN}}}definitions", {"id": "Definitions_1", "targetNamespace": "https://flowmap.local/bpmn"})
    process = ET.SubElement(defs, f"{{{BPMN}}}process", {"id": "Process_1", "name": name, "isExecutable": "false"})
    ids = {n["key"]: f"Node_{n['key']}" for n in graph["nodes"]}
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    flows = []
    for i, e in enumerate(graph["edges"]):
        if e["source"] in ids and e["target"] in ids:
            fid = f"Flow_{i}"
            flows.append((fid, e))
            outgoing.setdefault(e["source"], []).append(fid)
            incoming.setdefault(e["target"], []).append(fid)
    for n in graph["nodes"]:
        tag = BPMN_TAGS[n["type"]]
        el = ET.SubElement(process, f"{{{BPMN}}}{tag}", {"id": ids[n["key"]], "name": n["title"]})
        if n.get("description") or n.get("actor"):
            doc = ET.SubElement(el, f"{{{BPMN}}}documentation")
            parts = (f"Aktor: {n['actor']}" if n.get("actor") else "", n.get("description", ""))
            doc.text = " | ".join(x for x in parts if x)
        for fid in incoming.get(n["key"], []):
            ET.SubElement(el, f"{{{BPMN}}}incoming").text = fid
        for fid in outgoing.get(n["key"], []):
            ET.SubElement(el, f"{{{BPMN}}}outgoing").text = fid
        if n["type"] == "wait":
            ET.SubElement(el, f"{{{BPMN}}}timerEventDefinition", {"id": f"Timer_{n['key']}"})
    for fid, e in flows:
        attrs = {"id": fid, "sourceRef": ids[e["source"]], "targetRef": ids[e["target"]]}
        if e.get("label"):
            attrs["name"] = e["label"]
        flow = ET.SubElement(process, f"{{{BPMN}}}sequenceFlow", attrs)
        if e.get("condition") and e["condition"] != "error":
            ET.SubElement(flow, f"{{{BPMN}}}conditionExpression").text = e["condition"]

    diagram = ET.SubElement(defs, f"{{{BPMNDI}}}BPMNDiagram", {"id": "Diagram_1"})
    plane = ET.SubElement(diagram, f"{{{BPMNDI}}}BPMNPlane", {"id": "Plane_1", "bpmnElement": "Process_1"})
    pos = _levels(graph)
    bounds = {}
    for n in graph["nodes"]:
        w, h = SIZES.get(BPMN_TAGS[n["type"]], (120, 70))
        col, row = pos[n["key"]]
        x, y = 80 + col * 180 + (120 - w) / 2, 80 + row * 130 + (70 - h) / 2
        bounds[n["key"]] = (x, y, w, h)
        shape = ET.SubElement(plane, f"{{{BPMNDI}}}BPMNShape",
                              {"id": f"{ids[n['key']]}_di", "bpmnElement": ids[n["key"]]})
        ET.SubElement(shape, f"{{{DC}}}Bounds", {"x": f"{x:g}", "y": f"{y:g}", "width": str(w), "height": str(h)})
    for fid, e in flows:
        edge = ET.SubElement(plane, f"{{{BPMNDI}}}BPMNEdge", {"id": f"{fid}_di", "bpmnElement": fid})
        sx, sy, sw, sh = bounds[e["source"]]
        tx, ty, _tw, th = bounds[e["target"]]
        ET.SubElement(edge, f"{{{DI}}}waypoint", {"x": f"{sx + sw:g}", "y": f"{sy + sh / 2:g}"})
        ET.SubElement(edge, f"{{{DI}}}waypoint", {"x": f"{tx:g}", "y": f"{ty + th / 2:g}"})
    ET.indent(defs)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(defs, encoding="unicode") + "\n"


# --- Markdown specification ----------------------------------------------------

def _md(text: str) -> str:
    """Neutralise Markdown/HTML control characters in user and AI text."""
    return re.sub(r"([\\`*_{}\[\]<>#|])", r"\\\1", (text or "").replace("\n", " ")).strip()


def to_markdown(meta: dict, graph: dict, spec=None) -> str:
    """Readable spec. The data model comes from the spec layer (derived from the map when not given)."""
    from ..spec.derive import derive
    from ..spec.schema import FIELD_TYPE_LABELS

    spec = spec or derive(graph, meta)
    nodes = _ordered(graph)
    by_key = {n["key"]: n for n in nodes}
    rep = report(graph)
    actors = sorted({n["actor"] for n in nodes if n.get("actor")})
    screens = [n for n in nodes if n["type"] == "screen"]
    out = [f"# Specyfikacja: {_md(meta['name'])}", "",
           f"> Wygenerowano w FlowMap. Kompletność mapy: **{rep['score']}/100**.", "",
           "## 1. Opis procesu", "", f"Zdarzenie startowe: „{_md(meta['start_sentence'])}”.", ""]
    for i, n in enumerate(nodes, 1):
        actor = f" — *{_md(n['actor'])}*" if n.get("actor") else ""
        out.append(f"{i}. **{_md(n['title'])}** ({NODE_TYPE_LABELS[n['type']]}){actor}")
        for e in graph["edges"]:
            if e["source"] == n["key"] and e.get("label"):
                out.append(f"   - jeśli „{_md(e['label'])}” → {_md(by_key[e['target']]['title'])}")
    out += ["", "## 2. Role i uprawnienia", ""]
    for a in actors:
        steps = [n for n in nodes if n.get("actor") == a]
        out.append(f"- **{_md(a)}** — wykonuje: " + "; ".join(_md(n["title"]) for n in steps))
    if not actors:
        out.append("- (brak przypisanych ról)")
    out.append("- Każdy użytkownik widzi tylko własne dane; role inne niż System wymagają logowania.")

    out += ["", "## 3. Ekrany", ""]
    for s in screens:
        out.append(f"### {_md(s['title'])}")
        out.append(f"- Użytkownik: {_md(s.get('actor') or 'nie określono')}")
        if s.get("outputs"):
            out.append("- Wyświetla: " + ", ".join(_md(f) for f in s["outputs"]))
        if s.get("inputs"):
            out.append("- Pola do wypełnienia: " + ", ".join(_md(f) for f in s["inputs"]))
        if s.get("description"):
            out.append(f"- Opis: {_md(s['description'])}")
        out.append("")
    if not screens:
        out += ["Brak ekranów na mapie.", ""]

    out += ["## 4. Model danych", ""]
    for e in spec.entities:
        fields = ", ".join(f"{_md(f.name)} ({FIELD_TYPE_LABELS[f.type]})" for f in e.fields)
        out.append(f"- **{_md(e.name)}**: {fields}")
    if not spec.entities:
        out.append("- brak encji")

    out += ["", "## 5. Powiadomienia i integracje", ""]
    notif = [n for n in nodes if n["type"] in ("automation", "integration", "wait")]
    for n in notif:
        extra = f" — {', '.join(_md(f) for f in n['outputs'])}" if n.get("outputs") else ""
        out.append(f"- {NODE_TYPE_LABELS[n['type']]}: **{_md(n['title'])}**{extra}")
    if not notif:
        out.append("- brak")

    out += ["", "## 6. Historyjki użytkownika", ""]
    story_nodes = [n for n in nodes if n["type"] in ("user_action", "screen") and n.get("actor")]
    for n in story_nodes:
        nexts = [by_key[e["target"]]["title"] for e in graph["edges"] if e["source"] == n["key"]]
        out.append(f"- Jako **{_md(n['actor'])}** chcę: {_md(n['title'])[:1].lower() + _md(n['title'])[1:]}.")
        out.append("  - Kryteria akceptacji:")
        for f in n.get("inputs", []):
            out.append(f"    - [ ] pole „{_md(f)}” jest wymagane i walidowane")
        for f in n.get("outputs", []):
            out.append(f"    - [ ] widzę „{_md(f)}”")
        for t in nexts:
            out.append(f"    - [ ] po zakończeniu przechodzę do „{_md(t)}”")
        if not (n.get("inputs") or n.get("outputs") or nexts):
            out.append("    - [ ] krok da się wykonać i zapisuje wynik")

    out += ["", "## 7. Scenariusze testów", ""]
    for i, path in enumerate(_test_paths(graph), 1):
        steps = " → ".join(_md(by_key[k]["title"]) for k in path)
        out.append(f"{i}. {steps}")
    for n in nodes:
        if needs_error_path(n):
            out.append(f"- Test błędu: „{_md(n['title'])}” kończy się niepowodzeniem — proces obsługuje wyjątek.")

    out += ["", "## 8. Otwarte pytania", ""]
    questions = [i["message"] for i in rep["issues"]]
    known = " ".join(questions)
    questions += [f"Co dzieje się po „{n['title']}”?" for n in dead_ends(graph) if f"„{n['title']}”" not in known]
    out += [f"- {_md(qs)}" for qs in questions] or ["- brak — mapa jest kompletna"]
    return "\n".join(out) + "\n"


def _test_paths(graph: dict, limit: int = 8) -> list[list[str]]:
    """Distinct simple paths from start to any end/leaf (DFS, capped)."""
    out: dict[str, list[str]] = {}
    for e in graph["edges"]:
        out.setdefault(e["source"], []).append(e["target"])
    starts = [n["key"] for n in graph["nodes"] if n["type"] == "start"]
    paths: list[list[str]] = []

    def walk(path):
        if len(paths) >= limit:
            return
        nxt = [k for k in out.get(path[-1], []) if k not in path]
        if not nxt:
            paths.append(path)
            return
        for k in nxt:
            walk(path + [k])

    for s in starts:
        walk([s])
    return paths


# --- generator prompt ----------------------------------------------------------

TARGETS = {
    "claude_code": "Claude Code",
    "lovable": "Lovable",
    "bolt": "Bolt",
}


def to_prompt(meta: dict, spec_md: str, target: str = "claude_code") -> str:
    tool = TARGETS.get(target, "Claude Code")
    stack = ("Wybierz prosty, popularny stos (np. Python + Flask lub Next.js) i uzasadnij wybór w README."
             if target == "claude_code" else "Użyj domyślnego stosu narzędzia.")
    return (
        f"Zbuduj aplikację webową „{meta['name']}” w {tool} na podstawie poniższej specyfikacji.\n\n"
        "Wymagania ogólne:\n"
        "- Interfejs po polsku, responsywny (od 360 px), dostępny (WCAG AA).\n"
        "- Każdy krok procesu z sekcji 1 musi być obsłużony; ekrany z sekcji 3 jako osobne widoki.\n"
        "- Model danych z sekcji 4, walidacja pól, obsługa wszystkich gałęzi decyzji i ścieżek błędów.\n"
        "- Role z sekcji 2 z kontrolą dostępu; powiadomienia i integracje z sekcji 5 "
        "(integracje zewnętrzne zamockuj za interfejsem).\n"
        "- Testy automatyczne pokrywające scenariusze z sekcji 7.\n"
        "- Pytania otwarte z sekcji 8 rozstrzygnij najprostszym rozsądnym założeniem i wypisz je w README.\n"
        f"- {stack}\n\n"
        "---\n\n" + spec_md
    )


# --- JSON export/import ---------------------------------------------------------

class _NodeIn(BaseModel):
    key: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_-]+$")
    type: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    actor: str = Field(default="", max_length=100)
    inputs: list[str] = []
    outputs: list[str] = []
    data: dict = {}
    x: float | None = None
    y: float | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in NODE_TYPES:
            raise ValueError("nieznany typ kroku")
        return v


class _EdgeIn(BaseModel):
    source: str
    target: str
    label: str = Field(default="", max_length=100)
    condition: str = Field(default="", max_length=300)


class _ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_sentence: str = Field(min_length=1, max_length=500)
    mode: str = "quick"
    template: str | None = None


class ProjectFile(BaseModel):
    format: str
    project: _ProjectIn
    nodes: list[_NodeIn] = Field(max_length=500)
    edges: list[_EdgeIn] = Field(max_length=2000)
    spec: dict | None = None


def to_json(meta: dict, graph: dict, spec: dict | None = None) -> dict:
    data = {"format": FORMAT, "project": meta, "nodes": graph["nodes"], "edges": graph["edges"]}
    if spec:
        data["spec"] = spec
    return data


def parse_project_file(data) -> ProjectFile:
    """Validate an uploaded project JSON. Raises ValueError with a Polish message."""
    try:
        parsed = ProjectFile.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Niepoprawny plik projektu ({exc.error_count()} błędów).") from exc
    if parsed.format not in ACCEPTED_FORMATS:
        raise ValueError("Nieobsługiwany format pliku (oczekiwano flowmap/1 lub flowmap/2).")
    keys = [n.key for n in parsed.nodes]
    if len(keys) != len(set(keys)):
        raise ValueError("Powtórzone klucze kroków w pliku.")
    known = set(keys)
    if any(e.source not in known or e.target not in known for e in parsed.edges):
        raise ValueError("Połączenie wskazuje na nieistniejący krok.")
    return parsed
