"""Rule-based scores (no AI): map and app design, each 0–100 as a list of criteria with a note."""

from ..ai.rules import needs_error_path
from ..design.trace import trace_issues, trace_rows
from ..flow import questions as q
from ..flow.guard import report
from ..flow.lanes import lanes_info
from ..models import QuestionLog
from ..spec.readiness import readiness

FLOW = ("start", "end", "decision", "parallel", "wait")


def _c(code, label, points, maximum, note):
    return {"code": code, "label": label, "points": max(0, min(maximum, round(points))), "max": maximum, "note": note}


def _result(kind, label, criteria):
    return {"kind": kind, "label": label, "score": sum(c["points"] for c in criteria), "criteria": criteria}


def map_score(project, graph: dict) -> dict:
    guard = report(graph)
    risky = [n for n in graph["nodes"] if needs_error_path(n)]
    handled = [n for n in risky if any(e["source"] == n["key"] and e.get("condition") == "error"
                                       for e in graph["edges"])]
    acting = [n for n in graph["nodes"] if n["type"] not in FLOW]
    lane_of = lanes_info(graph, project.display)["of"]
    with_role = [n for n in acting if lane_of.get(n["key"])]
    pending = len(q.pending_nodes(project))
    used = [log.hint_level for log in QuestionLog.query.filter_by(project_id=project.id) if log.hint_level > 1]
    penalty = 2 * sum(level - 1 for level in used)
    if project.learning:
        hints_note = f"Pełnych podpowiedzi: {len(used)} (−{penalty} pkt)" if used else "Bez podpowiedzi z odpowiedziami"
    else:
        hints_note = "Tryb Praca — bez kary za podpowiedzi"
    criteria = [
        _c("guard", "Strażnik mapy", guard["score"] * 0.4, 40,
           f"Wynik strażnika {guard['score']}/100" + (f", uwagi: {len(guard['issues'])}" if guard["issues"] else "")),
        _c("errors", "Ścieżki błędu", (20 * len(handled) / len(risky) if risky else 20) if acting else 0, 20,
           "Mapa nie ma jeszcze kroków" if not acting
           else f"{len(handled)} z {len(risky)} ryzykownych kroków ma ścieżkę błędu" if risky
           else "Brak kroków wymagających ścieżki błędu"),
        _c("roles", "Role i przekazania", 15 * len(with_role) / len(acting) if acting else 0, 15,
           f"{len(with_role)} z {len(acting)} kroków ma przypisaną rolę" if acting else "Mapa nie ma jeszcze kroków"),
        _c("open", "Otwarte pytania", 15 - 3 * pending, 15,
           f"Otwartych pytań: {pending}" if pending else "Wszystkie pytania mają odpowiedź"),
        _c("hints", "Samodzielność", 10 - penalty if project.learning else 10, 10, hints_note),
    ]
    return _result("map", "Mapa procesu", criteria)


def design_score(graph: dict, spec) -> dict:
    if spec is None:
        return _result("design", "Projekt aplikacji",
                       [_c("readiness", "Specyfikacja", 0, 100, "Specyfikacja jest uszkodzona — Odbuduj specyfikację")])
    ready = readiness(spec)["score"]
    gaps = trace_issues(graph, spec)
    rows = trace_rows(graph, spec)
    tested = [r for r in rows if r["tests"]]
    v = spec.vision
    checks = (("mierniki", 10, bool(v.metrics)), ("Won't", 5, bool(v.wont)),
              ("opis problemu", 5, "problem" in v.manual))
    missing = [name for name, _pts, ok in checks if not ok]
    criteria = [
        _c("readiness", "Gotowość specyfikacji", ready * 0.4, 40, f"Gotowość {ready}/100 (z uwagami strażnika UML)"),
        _c("trace", "Śledzenie wymagań", 20 - 5 * len(gaps) if rows else 0, 20,
           "Mapa nie ma jeszcze kroków do śledzenia" if not rows
           else f"Luki w macierzy śledzenia: {len(gaps)}" if gaps else "Każdy krok ma realizację i test"),
        _c("tests", "Pokrycie testami", 20 * len(tested) / len(rows) if rows else 0, 20,
           f"{len(tested)} z {len(rows)} kroków w scenariuszach testów" if rows else "Brak kroków do pokrycia"),
        _c("vision", "Wizja i zakres", sum(pts for _name, pts, ok in checks if ok), 20,
           "Uzupełnij: " + ", ".join(missing) if missing else "Wizja ma mierniki, Won't i opis problemu"),
    ]
    return _result("design", "Projekt aplikacji", criteria)


def evaluate(project) -> list[dict]:
    from ..flow import graph as g  # local: flow.graph pulls in the spec layer

    graph = project.graph()
    return [map_score(project, graph), design_score(graph, g.project_spec(project))]
