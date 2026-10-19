"""Swimlanes: one lane per workstation (role). Pure functions over a graph dict + Project.display."""

import re

# Workstation icons (keys of the bundled Lucide set) with Polish names.
LANE_ICONS = {
    "briefcase": "Biuro", "warehouse": "Magazyn", "truck": "Transport", "user": "Klient / osoba",
    "users": "Zespół", "server": "System", "bot": "Automat",
}
LANE_RULES = [
    ("server", r"system|\bsap\b|\berp\b|\bwms\b|\bcrm\b|serwer|aplikacj|platform|\bapi\b|bramk"),
    ("warehouse", r"magazyn|kompletuj|kontroler|operator|wózk|przyjmuj"),
    ("truck", r"kierowc|spedyt|kurier|logisty|przewoźn|transport"),
    ("user", r"klient|użytkownik|kupując|pacjent|obywatel|gość|odbiorc|zgłaszając"),
    ("users", r"zespół|dział|komisj|zarząd"),
]
UNASSIGNED = ""
# Events and gateways without a role sit in their neighbour's lane.
INHERIT = ("start", "end", "decision", "parallel", "wait")


def lane_icon(role: str) -> str:
    for key, rx in LANE_RULES:
        if re.search(rx, role or "", re.I):
            return key
    return "briefcase"


def _walk(graph: dict) -> list[dict]:
    by_key = {n["key"]: n for n in graph["nodes"]}
    children: dict[str, list[str]] = {}
    for e in graph["edges"]:
        children.setdefault(e["source"], []).append(e["target"])
    queue = [n["key"] for n in graph["nodes"] if n["type"] == "start"] or [n["key"] for n in graph["nodes"][:1]]
    seen, order = set(), []
    while queue:
        k = queue.pop(0)
        if k in seen or k not in by_key:
            continue
        seen.add(k)
        order.append(by_key[k])
        queue.extend(children.get(k, []))
    return order + [n for n in graph["nodes"] if n["key"] not in seen]


def assign(graph: dict) -> dict[str, str]:
    """node key -> lane (role). Roleless events and gateways inherit the lane of a neighbour."""
    lanes = {n["key"]: (n.get("actor") or "").strip() for n in graph["nodes"]}
    types = {n["key"]: n["type"] for n in graph["nodes"]}
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    for e in graph["edges"]:
        parents.setdefault(e["target"], []).append(e["source"])
        children.setdefault(e["source"], []).append(e["target"])
    for _ in range(len(lanes)):  # propagate until stable
        changed = False
        for key, lane in lanes.items():
            if lane or types[key] not in INHERIT:
                continue
            near = [lanes[k] for k in parents.get(key, []) + children.get(key, []) if lanes.get(k)]
            if near:
                lanes[key] = near[0]
                changed = True
        if not changed:
            break
    return lanes


def lanes_info(graph: dict, display: dict | None = None) -> dict:
    """Lane order, workstation icons, per-node lane and the number of hand-offs between workstations."""
    settings = (display or {}).get("lanes", {})
    lane_of = assign(graph)
    first_seen = list(dict.fromkeys(lane_of[n["key"]] for n in _walk(graph)))
    saved = [r for r in settings.get("order", []) if r in first_seen]
    order = saved + [r for r in first_seen if r not in saved]
    if UNASSIGNED in order:  # the "no role" lane always goes last
        order = [r for r in order if r != UNASSIGNED] + [UNASSIGNED]
    icons = {r: (settings.get("icons", {}).get(r) if settings.get("icons", {}).get(r) in LANE_ICONS
                 else ("user" if r == UNASSIGNED else lane_icon(r))) for r in order}
    handoffs = sum(1 for e in graph["edges"] if lane_of.get(e["source"]) != lane_of.get(e["target"]))
    return {"order": order, "icons": icons, "of": lane_of, "handoffs": handoffs}


def update(display: dict | None, role: str, *, icon: str | None = None, move: int = 0, order: list[str]) -> dict:
    """New display dict with the lane's icon changed or the lane moved up/down."""
    data = dict(display or {})
    lanes = dict(data.get("lanes", {}))
    if icon is not None:
        if icon not in LANE_ICONS:
            raise ValueError("Nieznana ikona stanowiska.")
        lanes["icons"] = dict(lanes.get("icons", {})) | {role: icon}
    if move:
        current = list(order)
        if role not in current:
            raise ValueError("Nie ma takiego toru.")
        i = current.index(role)
        j = max(0, min(len(current) - 1, i + move))
        current[i], current[j] = current[j], current[i]
        lanes["order"] = current
    data["lanes"] = lanes
    return data
