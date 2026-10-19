"""Requirements traceability: map step → what realizes it in the spec → use case → test scenarios."""

from ..export.builders import _ordered, _test_paths
from ..flow.lanes import assign
from ..spec.schema import Spec

FLOW = ("start", "end", "decision", "parallel", "wait")
NEEDS_SCREEN = ("screen", "user_action")


def _realized(node: dict, spec: Spec) -> list[str]:
    key, title = node["key"], node["title"].strip().lower()
    out = [f"Ekran: {s.name}" for s in spec.screens if s.node_key == key or s.name.strip().lower() == title]
    out += [f"Integracja: {i.name}" for i in spec.integrations if i.node_key == key]
    out += [f"Powiadomienie: {n.trigger}" for n in spec.notifications if n.node_key == key]
    return out


def trace_rows(graph: dict, spec: Spec) -> list[dict]:
    lanes = assign(graph)
    paths = _test_paths(graph)
    by_actor = {u.actor: u.name for u in spec.use_cases}
    roles = {r.name.strip().lower(): r.key for r in spec.roles}
    system_uc = next((u.name for u in spec.use_cases if not u.actor), "")
    rows = []
    for n in _ordered(graph):
        if n["type"] in FLOW:
            continue
        actor = lanes.get(n["key"]) or "System"
        role = roles.get(actor.strip().lower(), "")
        rows.append({"node_key": n["key"], "step": n["title"], "actor": actor, "realized_by": _realized(n, spec),
                     "use_case": by_actor.get(role, "") if role else system_uc,
                     "tests": [i for i, p in enumerate(paths, 1) if n["key"] in p], "type": n["type"]})
    return rows


def _i(code, message, key, why):
    return {"code": code, "message": message, "target_key": key, "why": why}


def trace_issues(graph: dict, spec: Spec) -> list[dict]:
    issues = []
    for r in trace_rows(graph, spec):
        if r["type"] in NEEDS_SCREEN and not any(x.startswith("Ekran:") for x in r["realized_by"]):
            issues.append(_i("step_without_screen", f"Krok „{r['step']}” nie ma ekranu w specyfikacji.", r["node_key"],
                             "Użytkownik musi gdzieś wykonać tę czynność. Dodaj ekran o tej nazwie w specyfikacji "
                             "albo zmień typ kroku na mapie na „Ekran”."))
        if not r["tests"]:
            issues.append(_i("step_without_test", f"Krok „{r['step']}” nie występuje w żadnym scenariuszu testu.",
                             r["node_key"], "Krok poza scenariuszami nie zostanie sprawdzony — zwykle jest "
                             "nieosiągalny ze startu. Połącz go z procesem albo usuń."))
    return issues
