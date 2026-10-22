"""Time and cost of a case: minutes and PLN entered per step, summed over the happy path. Pure functions."""

from ..design.derive import main_path
from .lanes import assign

TIMED = ("user_action", "screen", "automation", "integration", "wait")  # events and gateways take no time


def step_minutes(node: dict) -> int | None:
    value = (node.get("data") or {}).get("minutes")
    return value if isinstance(value, int) and value >= 0 else None


def step_cost(node: dict) -> float | None:
    value = (node.get("data") or {}).get("cost")
    return float(value) if isinstance(value, int | float) and value >= 0 else None


def analyze(graph: dict) -> dict | None:
    """Happy-path totals, waiting share, the slowest steps and minutes per role; None when nothing is timed."""
    by_key = {n["key"]: n for n in graph["nodes"]}
    timed = [n for n in graph["nodes"] if n["type"] in TIMED]
    if not any(step_minutes(n) is not None or step_cost(n) is not None for n in timed):
        return None
    path = [by_key[k] for k in main_path(graph) if k in by_key and by_key[k]["type"] in TIMED]
    minutes = sum(step_minutes(n) or 0 for n in path)
    waiting = sum(step_minutes(n) or 0 for n in path if n["type"] == "wait")
    lanes = assign(graph)
    roles: dict[str, int] = {}
    for n in path:
        if step_minutes(n):
            role = lanes.get(n["key"]) or "bez roli"
            roles[role] = roles.get(role, 0) + step_minutes(n)
    slowest = sorted((n for n in path if step_minutes(n)), key=lambda n: -step_minutes(n))[:3]
    return {
        "minutes": minutes, "cost": round(sum(step_cost(n) or 0 for n in path), 2),
        "waiting_pct": round(100 * waiting / minutes) if minutes else 0,
        "slowest": [{"title": n["title"], "minutes": step_minutes(n),
                     "pct": round(100 * step_minutes(n) / minutes) if minutes else 0} for n in slowest],
        "roles": sorted(roles.items(), key=lambda r: -r[1]),
        "missing": [n["title"] for n in path if step_minutes(n) is None],
        "path_steps": len(path),
    }


def duration_label(minutes: int) -> str:
    """90 → "1 h 30 min", 2880 → "2 dni"; working out a calendar is out of scope."""
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = [f"{days} {'dzień' if days == 1 else 'dni'}" if days else "", f"{hours} h" if hours else "",
             f"{mins} min" if mins else ""]
    return " ".join(p for p in parts if p) or "0 min"
