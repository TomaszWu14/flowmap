"""Completeness guard: deterministic checks over a graph dict, plus a 0-100 score."""

from ..ai.rules import needs_error_path

WEIGHTS = {
    "no_start": 25, "no_end": 25, "dead_end": 10, "open_branch": 8, "decision_exits": 10,
    "missing_actor": 3, "missing_error_path": 8, "unreachable": 10, "open_comment": 2,
}


def _issue(code: str, message: str, node_key: str | None = None) -> dict:
    return {"code": code, "message": message, "node_key": node_key}


def reachable(graph: dict, start_keys: list[str]) -> set[str]:
    children: dict[str, list[str]] = {}
    for e in graph["edges"]:
        children.setdefault(e["source"], []).append(e["target"])
    seen, stack = set(), list(start_keys)
    while stack:
        k = stack.pop()
        if k not in seen:
            seen.add(k)
            stack.extend(children.get(k, []))
    return seen


def check(graph: dict) -> list[dict]:
    nodes = graph["nodes"]
    issues: list[dict] = []
    out: dict[str, list[dict]] = {n["key"]: [] for n in nodes}
    for e in graph["edges"]:
        out.setdefault(e["source"], []).append(e)

    starts = [n["key"] for n in nodes if n["type"] == "start"]
    if not starts:
        issues.append(_issue("no_start", "Brak kroku startowego."))
    if not any(n["type"] == "end" for n in nodes):
        issues.append(_issue("no_end", "Proces nie ma żadnego końca (węzła „Koniec”)."))

    seen = reachable(graph, starts)
    for n in nodes:
        key, title, edges = n["key"], n["title"], out.get(n["key"], [])
        if n["type"] != "end" and not edges:
            issues.append(_issue("dead_end", f"Gałąź kończy się na „{title}” bez węzła końca.", key))
        if n["type"] == "decision":
            if len(edges) < 2:
                issues.append(_issue("decision_exits", f"Decyzja „{title}” ma mniej niż 2 wyjścia.", key))
            used = {e["label"] for e in edges}
            for label in n.get("data", {}).get("branches", []):
                if label not in used and edges:
                    msg = f"Gałąź „{label}” decyzji „{title}” nie ma dalszego kroku."
                    issues.append(_issue("open_branch", msg, key))
        if n["type"] not in ("start", "end") and not n.get("actor"):
            issues.append(_issue("missing_actor", f"Krok „{title}” nie ma aktora (roli).", key))
        if needs_error_path(n) and len(edges) < 2 and not any(e.get("condition") == "error" for e in edges):
            issues.append(_issue("missing_error_path", f"Brak ścieżki błędu dla „{title}”.", key))
        if starts and key not in seen:
            issues.append(_issue("unreachable", f"Krok „{title}” jest nieosiągalny ze startu.", key))
    return issues


def score(issues: list[dict]) -> int:
    return max(0, 100 - sum(WEIGHTS.get(i["code"], 5) for i in issues))


def report(graph: dict, open_comments: dict[str, int] | None = None) -> dict:
    issues = check(graph)
    titles = {n["key"]: n["title"] for n in graph["nodes"]}
    for key, count in (open_comments or {}).items():
        if key in titles:
            issues.append(_issue("open_comment", f"Nierozwiązane komentarze przy „{titles[key]}”: {count}.", key))
    return {"score": score(issues), "issues": issues}
