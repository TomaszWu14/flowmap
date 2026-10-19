"""Completeness guard: deterministic checks over a graph dict, plus a 0-100 score."""

import re
import unicodedata

from ..ai.rules import needs_error_path

WEIGHTS = {
    "no_start": 25, "no_end": 25, "dead_end": 10, "open_branch": 8, "decision_exits": 10,
    "missing_actor": 3, "missing_error_path": 8, "unreachable": 10, "open_comment": 2,
    "duplicate_step": 5, "similar_steps": 0, "parallel_unjoined": 5,
}
STOP = {"oraz", "przez", "dla", "danych", "systemie", "procesu"}
MAX_SIMILAR = 5


def _issue(code: str, message: str, node_key: str | None = None, **extra) -> dict:
    return {"code": code, "message": message, "node_key": node_key, **extra}


def _stems(title: str) -> set[str]:
    """Rough Polish stems: no diacritics, words of 3+ letters cut to 6 chars (powiadomienie ~ powiadomienia)."""
    text = unicodedata.normalize("NFKD", title.lower().replace("ł", "l")).encode("ascii", "ignore").decode()
    return {w[:6] for w in re.findall(r"[a-z0-9]{3,}", text) if w not in STOP}


def similar_pairs(nodes: list[dict], edges: list[dict]) -> list[tuple[dict, dict]]:
    """Same-type steps whose titles look alike (not start/end, not already reported as consecutive repeats)."""
    linked = {(e["source"], e["target"]) for e in edges}
    cand = [(n, _stems(n["title"])) for n in nodes if n["type"] not in ("start", "end")]
    pairs = []
    for i, (a, sa) in enumerate(cand):
        for b, sb in cand[i + 1:]:
            if a["type"] != b["type"] or not sa or not sb or (a["key"], b["key"]) in linked \
                    or (b["key"], a["key"]) in linked:
                continue
            if sa == sb or (min(len(sa), len(sb)) >= 2 and len(sa & sb) / len(sa | sb) >= 0.6):
                pairs.append((a, b))
    return pairs[:MAX_SIMILAR]


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
    by_key = {n["key"]: n for n in nodes}
    for e in graph["edges"]:
        a, b = by_key.get(e["source"]), by_key.get(e["target"])
        same = a and b and (a["type"], a["title"].strip().lower()) == (b["type"], b["title"].strip().lower())
        if same and a["key"] != b["key"]:
            issues.append(_issue("duplicate_step", f"Krok „{b['title']}” powtarza poprzedni krok.", b["key"]))
    for n in nodes:
        key, title, edges = n["key"], n["title"], out.get(n["key"], [])
        if n["type"] != "end" and not edges:
            issues.append(_issue("dead_end", f"Gałąź kończy się na „{title}” bez węzła końca.", key))
        split = n["type"] == "parallel" and (n.get("data") or {}).get("branches")
        if n["type"] == "decision" or split:
            kind = "Decyzja" if n["type"] == "decision" else "Bramka AND"
            if len(edges) < 2:
                issues.append(_issue("decision_exits", f"{kind} „{title}” ma mniej niż 2 wyjścia.", key))
            used = {e["label"] for e in edges}
            for label in n.get("data", {}).get("branches", []):
                if label not in used and edges:
                    owner = "decyzji" if n["type"] == "decision" else "bramki AND"
                    msg = f"Gałąź „{label}” {owner} „{title}” nie ma dalszego kroku."
                    issues.append(_issue("open_branch", msg, key, label=label))
        if n["type"] not in ("start", "end", "parallel") and not n.get("actor"):
            issues.append(_issue("missing_actor", f"Krok „{title}” nie ma aktora (roli).", key))
        if needs_error_path(n) and len(edges) < 2 and not any(e.get("condition") == "error" for e in edges):
            issues.append(_issue("missing_error_path", f"Brak ścieżki błędu dla „{title}”.", key))
        if starts and key not in seen:
            issues.append(_issue("unreachable", f"Krok „{title}” jest nieosiągalny ze startu.", key))
    joins = {n["key"] for n in nodes if n["type"] == "parallel" and not (n.get("data") or {}).get("branches")}
    for n in nodes:  # parallel paths must meet again at a join, otherwise "all of them" never finishes
        branches = out.get(n["key"], [])
        if n["type"] == "parallel" and (n.get("data") or {}).get("branches") and len(branches) >= 2:
            common = set.intersection(*(reachable(graph, [e["target"]]) for e in branches)) & joins
            if not common:
                issues.append(_issue("parallel_unjoined", f"Ścieżki równoległe po „{n['title']}” się nie zbiegają "
                                     "— dodaj bramkę łączącą AND.", n["key"]))
    for a, b in similar_pairs(nodes, graph["edges"]):
        issues.append(_issue("similar_steps", f"Kroki „{a['title']}” i „{b['title']}” wyglądają podobnie — "
                             "może to ten sam krok?", b["key"], other=a["key"]))
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
