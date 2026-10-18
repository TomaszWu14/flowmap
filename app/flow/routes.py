import json

from flask import Blueprint, abort, jsonify, make_response, render_template, request
from flask_login import login_required

from ..ai.client import AIError, ai_enabled, review_map
from ..ai.schemas import Option, Question
from ..extensions import db
from ..models import NODE_TYPE_LABELS, NODE_TYPES, QuestionLog
from . import graph as g
from . import guard
from . import questions as q
from .simulate import simulation_state

bp = Blueprint("flow", __name__)


def graph_payload(graph: dict, pending: set[str] | None = None) -> dict:
    report = guard.report(graph)
    by_node: dict[str, list[str]] = {}
    for issue in report["issues"]:
        if issue["node_key"]:
            by_node.setdefault(issue["node_key"], []).append(issue["message"])
    for n in graph["nodes"]:
        n["issues"] = by_node.get(n["key"], [])
        n["pending"] = bool(pending and n["key"] in pending)
        n["type_label"] = NODE_TYPE_LABELS[n["type"]]
    return {"nodes": graph["nodes"], "edges": graph["edges"], **report}


def render_panel(project, node=None, kind=None, slot=None, error=None, focus_changed=True, status=200):
    if node is None:
        pending = q.pending_nodes(project)
        node = pending[0] if pending else None
    log, question = (None, None)
    if node is not None:
        log, question = q.current_question(project, node, kind, slot)
    remaining = len(q.pending_nodes(project))
    if remaining == 0 and project.status != "complete":
        project.status = "complete"
        db.session.commit()
    elif remaining and project.status == "complete":
        project.status = "draft"
        db.session.commit()
    others = [n for n in project.nodes if node is None or n.key != node.key]
    html = render_template(
        "flow/_panel.html", project=project, node=node, log=log, question=question, error=error,
        node_types=NODE_TYPES, type_labels=NODE_TYPE_LABELS, others=others, remaining=remaining,
        outgoing=g.outgoing(project, node) if node else [],
    )
    resp = make_response(html, status)
    if focus_changed:
        resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": node.key if node else ""}})
    return resp


def _changed(project, description: str, node=None, **kw):
    g.save_version(project, description)
    db.session.commit()
    return render_panel(project, node, **kw)


@bp.get("/p/<int:project_id>")
@login_required
def view(project_id):
    project = g.owned_project(project_id)
    return render_template("flow/view.html", project=project, ai=ai_enabled())


@bp.get("/p/<int:project_id>/graph.json")
@login_required
def graph_json(project_id):
    project = g.owned_project(project_id)
    pending = {n.key for n in q.pending_nodes(project)}
    payload = graph_payload(project.graph(), pending)
    payload.update(can_undo=g.can_undo(project), can_redo=g.can_redo(project), status=project.status)
    return jsonify(payload)


@bp.get("/p/<int:project_id>/panel")
@login_required
def panel(project_id):
    project = g.owned_project(project_id)
    key = request.args.get("node")
    node = g.owned_node(project, key) if key else None
    kind = request.args.get("ask") or None
    if kind and kind not in ("next", "actor", "screen", "data", "error", "branches"):
        abort(400)
    slot = (request.args.get("slot") or "").strip()[:100] or None
    if kind == "next" and slot is None and node is not None:
        labels = g.open_labels(project, node)
        slot = labels[0] if labels else ""
    return render_panel(project, node, kind, slot, focus_changed=False)


@bp.post("/p/<int:project_id>/answer")
@login_required
def answer(project_id):
    project = g.owned_project(project_id)
    log = db.session.get(QuestionLog, request.form.get("log_id", type=int) or 0)
    if log is None or log.project_id != project.id:
        abort(404)
    node = g.owned_node(project, log.node_key)
    question = Question.model_validate(log.options)
    if log.answer:
        return render_panel(project, None, error="To pytanie ma już odpowiedź — pokazuję kolejne.")
    try:
        if request.form.get("other"):
            option = q.option_from_other(question.kind, request.form)
        else:
            idx = request.form.get("option", type=int)
            if idx is None or not 0 <= idx < len(question.options):
                abort(400)
            option = question.options[idx]
    except ValueError as exc:
        return render_panel(project, node, question.kind, question.slot, error=str(exc), focus_changed=False)
    if node.type == "decision" and question.kind == "next" and question.slot:
        branches = list(node.data.get("branches", []))
        if question.slot not in branches:
            g.set_node_data(node, branches=branches + [question.slot])
    created = q.apply_option(project, node, question, option)
    log.answer = option.label
    focus = q.next_focus(project, created, node)
    return _changed(project, f"{question.text} → {option.label}", focus)


@bp.post("/p/<int:project_id>/node/<key>/edit")
@login_required
def edit_node(project_id, key):
    project = g.owned_project(project_id)
    node = g.owned_node(project, key)
    f = request.form
    title = (f.get("title") or "").strip()
    if not title:
        return render_panel(project, node, error="Tytuł kroku nie może być pusty.", focus_changed=False)
    if node.type != "start":
        new_type = f.get("type", node.type)
        node.type = new_type if new_type in NODE_TYPES and new_type != "start" else node.type
    node.title = title[:200]
    node.actor = (f.get("actor") or "").strip()[:100]
    node.description = (f.get("description") or "").strip()[:2000]
    node.inputs = [v.strip()[:100] for v in (f.get("inputs") or "").split(",") if v.strip()]
    node.outputs = [v.strip()[:100] for v in (f.get("outputs") or "").split(",") if v.strip()]
    if node.type == "decision":
        branches = [b.strip()[:100] for b in (f.get("branches") or "").split(",") if b.strip()]
        g.set_node_data(node, branches=list(dict.fromkeys(branches)))
    return _changed(project, f"Zmieniono krok „{node.title}”", node)


@bp.post("/p/<int:project_id>/node/<key>/delete")
@login_required
def delete_node(project_id, key):
    project = g.owned_project(project_id)
    node = g.owned_node(project, key)
    if node.type == "start":
        return render_panel(project, node, error="Nie można usunąć kroku startowego.", focus_changed=False)
    title = node.title
    g.delete_node(project, node)
    return _changed(project, f"Usunięto krok „{title}”")


@bp.post("/p/<int:project_id>/node/<key>/connect")
@login_required
def connect_node(project_id, key):
    project = g.owned_project(project_id)
    node = g.owned_node(project, key)
    target = g.owned_node(project, request.form.get("target", ""))
    label = (request.form.get("label") or "").strip()
    if node.type == "decision":
        open_ = g.open_labels(project, node)
        label = label or (open_[0] if open_ else "")
        if label and label not in node.data.get("branches", []):
            g.set_node_data(node, branches=list(node.data.get("branches", [])) + [label])
    g.add_edge(project, node, target, label)
    return _changed(project, f"Połączono „{node.title}” → „{target.title}”", node)


@bp.post("/p/<int:project_id>/node/<key>/end")
@login_required
def mark_end(project_id, key):
    project = g.owned_project(project_id)
    node = g.owned_node(project, key)
    if node.type == "start":
        return render_panel(project, node, error="Start nie może być końcem.", focus_changed=False)
    if g.outgoing(project, node):
        return render_panel(project, node, focus_changed=False,
                            error="Ten krok ma kolejne kroki — usuń je albo dodaj koniec jako nowy krok.")
    node.type = "end"
    return _changed(project, f"Oznaczono „{node.title}” jako koniec", node)


@bp.post("/p/<int:project_id>/edge/<int:index>/delete")
@login_required
def delete_edge(project_id, index):
    project = g.owned_project(project_id)
    if not 0 <= index < len(project.edges):
        abort(404)
    edge = project.edges[index]
    source = edge.source
    project.edges.remove(edge)
    db.session.delete(edge)
    return _changed(project, f"Usunięto połączenie z „{source.title}”", source)


@bp.post("/p/<int:project_id>/undo")
@login_required
def undo(project_id):
    project = g.owned_project(project_id)
    g.step_history(project, older=True)
    db.session.commit()
    return render_panel(project)


@bp.post("/p/<int:project_id>/redo")
@login_required
def redo(project_id):
    project = g.owned_project(project_id)
    g.step_history(project, older=False)
    db.session.commit()
    return render_panel(project)


@bp.post("/p/<int:project_id>/positions")
@login_required
def positions(project_id):
    project = g.owned_project(project_id)
    data = request.get_json(silent=True) or {}
    for node in project.nodes:
        pos = data.get(node.key)
        if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int | float) for v in pos):
            node.pos_x, node.pos_y = float(pos[0]), float(pos[1])
    db.session.commit()
    return {"ok": True}


@bp.post("/p/<int:project_id>/layout")
@login_required
def reset_layout(project_id):
    project = g.owned_project(project_id)
    for node in project.nodes:
        node.pos_x = node.pos_y = None
    db.session.commit()
    resp = make_response("", 204)
    resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": ""}})
    return resp


# --- completeness guard -------------------------------------------------------

@bp.get("/p/<int:project_id>/guard")
@login_required
def guard_panel(project_id):
    project = g.owned_project(project_id)
    report = guard.report(project.graph())
    return render_template("flow/_guard.html", project=project, report=report, ai=ai_enabled(),
                           suggestions=None, log=None, titles={n.key: n.title for n in project.nodes})


@bp.post("/p/<int:project_id>/guard/review")
@login_required
def guard_review(project_id):
    from flask import current_app
    from flask_login import current_user

    project = g.owned_project(project_id)
    graph = project.graph()
    report = guard.report(graph)
    error, log, suggestions = None, None, None
    if not ai_enabled():
        error = "Przegląd AI wymaga klucza ANTHROPIC_API_KEY."
    elif not current_user.consume_ai_request(current_app.config["AI_DAILY_LIMIT"]):
        error = "Dzienny limit zapytań do AI został wyczerpany."
    else:
        db.session.commit()
        try:
            suggestions = review_map(project, graph, report["issues"])
            log = QuestionLog(project_id=project.id, kind="review", question="Przegląd AI: brakujące wyjątki",
                              options={"suggestions": suggestions}, answer="", source="ai")
            db.session.add(log)
        except AIError as exc:
            error = f"Przegląd AI nieudany: {exc}."
    db.session.commit()
    return render_template("flow/_guard.html", project=project, report=report, ai=True, error=error,
                           suggestions=suggestions, log=log, titles={n.key: n.title for n in project.nodes})


@bp.post("/p/<int:project_id>/guard/apply")
@login_required
def guard_apply(project_id):
    project = g.owned_project(project_id)
    log = db.session.get(QuestionLog, request.form.get("log_id", type=int) or 0)
    idx = request.form.get("index", type=int)
    if log is None or log.project_id != project.id or log.kind != "review" or idx is None:
        abort(404)
    suggestions = log.options.get("suggestions", [])
    if not 0 <= idx < len(suggestions):
        abort(404)
    s = suggestions[idx]
    node = g.owned_node(project, s["node_key"])
    option = Option(label=s["problem"], steps=s["steps"], edge_label=s["edge_label"] or "wyjątek",
                    edge_condition="error")
    question = Question(kind="next", node_key=node.key, text=s["problem"], options=[option])
    created = q.apply_option(project, node, question, option)
    log.answer = (log.answer + f"{idx};")[:1000]
    return _changed(project, f"Dodano wyjątek: {s['problem']}", created[-1] if created else node)


# --- simulation -----------------------------------------------------------------

@bp.get("/p/<int:project_id>/symulacja")
@login_required
def simulate(project_id):
    project = g.owned_project(project_id)
    graph = project.graph()
    role = request.args.get("role")
    path = [k for k in (request.args.get("path") or "").split(",") if k]
    state = simulation_state(graph, role, path) if role else None
    actors = sorted({n["actor"] for n in graph["nodes"] if n["actor"]})
    return render_template("flow/simulate.html", project=project, actors=actors, role=role, state=state)
