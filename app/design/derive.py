"""Use cases from the map: one per human lane, alternatives from gateways and error paths, «include» to System."""

from itertools import pairwise

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
        nxt = [e["target"] for e in out.get(key, []) if e.get("condition") != "error" and e["target"] in by_key]
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
                if e.get("condition") == "error" and e["target"] in by_key:
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
    hand_to_system = {slug(lanes[a]) for a, b in pairwise(acting) if is_system(lanes[b])}
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
