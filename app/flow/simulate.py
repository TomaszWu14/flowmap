"""'Walk the process' simulation over a graph dict. Stateless: the path travels in the URL."""

MAX_PATH = 200


def dead_ends(graph: dict) -> list[dict]:
    sources = {e["source"] for e in graph["edges"]}
    return [n for n in graph["nodes"] if n["type"] != "end" and n["key"] not in sources]


def simulation_state(graph: dict, role: str, path: list[str]) -> dict:
    by_key = {n["key"]: n for n in graph["nodes"]}
    out: dict[str, list[dict]] = {}
    for e in graph["edges"]:
        out.setdefault(e["source"], []).append(e)
    if not path:
        start = next((n for n in graph["nodes"] if n["type"] == "start"), None)
        path = [start["key"]] if start else []
    # Keep only a valid walk: every hop must follow an existing edge.
    valid = path[:1] if path and path[0] in by_key else []
    for key in path[1:MAX_PATH]:
        if any(e["target"] == key for e in out.get(valid[-1], [])):
            valid.append(key)
        else:
            break
    if not valid:
        return {"node": None, "choices": [], "path": [], "finished": True, "summary": _summary(graph, [], role)}
    node = by_key[valid[-1]]
    choices = [{"label": e["label"] or "Dalej", "target": e["target"], "title": by_key[e["target"]]["title"],
                "error": e.get("condition") == "error"} for e in out.get(node["key"], [])]
    finished = node["type"] == "end" or not choices or len(valid) >= MAX_PATH
    return {
        "node": node, "choices": choices, "path": valid, "path_str": ",".join(valid),
        "mine": node["actor"] == role, "finished": finished,
        "dead_end": not choices and node["type"] != "end",
        "summary": _summary(graph, valid, role) if finished else None,
        "trail": [by_key[k] for k in valid],
    }


def _summary(graph: dict, path: list[str], role: str) -> dict:
    by_key = {n["key"]: n for n in graph["nodes"]}
    walked = [by_key[k] for k in path]
    return {
        "steps": len(walked),
        "role_steps": sum(1 for n in walked if n["actor"] == role),
        "screens": len({n["key"] for n in walked if n["type"] == "screen"}),
        "dead_ends": dead_ends(graph),
        "reached_end": bool(walked) and walked[-1]["type"] == "end",
    }
