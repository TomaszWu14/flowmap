import json

from flask import Blueprint, abort, jsonify, make_response, render_template, request, url_for
from flask_login import login_required

from ..ai.client import AIError, ai_enabled, fill_map, review_map, spend_ai_request
from ..ai.schemas import Option, Question
from ..comments.routes import open_comment_counts
from ..extensions import db
from ..models import NODE_TYPE_LABELS, NODE_TYPES, QuestionLog
from . import graph as g
from . import guard
from . import lanes as lanes_mod
from . import questions as q
from .pictograms import PICTOGRAMS, icon_for
from .simulate import simulation_state

bp = Blueprint("flow", __name__)


def graph_payload(graph: dict, pending: set[str] | None = None, comments: dict[str, int] | None = None,
                  display: dict | None = None) -> dict:
    report = guard.report(graph, comments)
    by_node: dict[str, list[str]] = {}
    for issue in report["issues"]:
        if issue["node_key"]:
            by_node.setdefault(issue["node_key"], []).append(issue["message"])
    for n in graph["nodes"]:
        n["issues"] = by_node.get(n["key"], [])
        n["pending"] = bool(pending and n["key"] in pending)
        n["comments"] = (comments or {}).get(n["key"], 0)
        n["type_label"] = NODE_TYPE_LABELS[n["type"]]
        n["icon"] = icon_for(n)
        n["icon_label"] = PICTOGRAMS[n["icon"]][0] if n["icon"] else ""
    lanes = lanes_mod.lanes_info(graph, display)
    for n in graph["nodes"]:
        n["lane"] = lanes["of"].get(n["key"], "")
    lanes.pop("of")
    return {"nodes": graph["nodes"], "edges": graph["edges"], "lanes": lanes, **report}


def render_panel(project, node=None, kind=None, slot=None, error=None, focus_changed=True, status=200):
    pending = q.pending_nodes(project)
    if node is None:
        node = pending[0] if pending else None
    log, question = (None, None)
    if node is not None:
        log, question = q.current_question(project, node, kind, slot)
    remaining = len(pending)
    if remaining == 0 and project.status != "complete":
        project.status = "complete"
        db.session.commit()
    elif remaining and project.status == "complete":
        project.status = "draft"
        db.session.commit()
    others = [n for n in project.nodes if node is None or n.key != node.key]
    html = render_template(
        "flow/_panel.html", project=project, node=node, log=log, question=question, error=error,
        node_types=NODE_TYPES, others=others, remaining=remaining,
        step_images=_step_images(project, node),
        outgoing=g.outgoing(project, node) if node else [],
    )
    resp = make_response(html, status)
    if focus_changed:
        resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": node.key if node else ""}})
    return resp


PENDING_LABELS = {"next": "co dalej", "branches": "wyjścia decyzji", "actor": "kto wykonuje",
                  "screen": "co pokazuje ekran", "data": "jakie dane", "error": "ścieżka błędu"}


def open_questions(project) -> list[dict]:
    """Steps still waiting for an answer, in walk order — the "Do zrobienia" list."""
    out = []
    for n in q.pending_nodes(project):
        kind, slot = q.pending_kind(project, n)
        out.append({"key": n.key, "title": n.title,
                    "what": PENDING_LABELS.get(kind, kind) + (f" → „{slot}”" if slot else "")})
    return out


def with_toast(resp, message: str, undo: bool = True):
    """Add a "toast" event (shown by app.js, with an Undo button) to the response's HX-Trigger."""
    events = json.loads(resp.headers.get("HX-Trigger") or "{}")
    events["toast"] = {"message": message, "undo": undo}
    resp.headers["HX-Trigger"] = json.dumps(events)
    return resp


def _step_images(project, node):
    from ..media.routes import images_of

    return images_of(project, node.key) if node is not None else []


def _changed(project, description: str, node=None, toast: bool = False, **kw):
    g.save_version(project, description)
    db.session.commit()
    resp = render_panel(project, node, **kw)
    return with_toast(resp, description) if toast else resp


@bp.get("/p/<int:project_id>")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    return render_template("flow/view.html", project=project, ai=ai_enabled())


@bp.get("/p/<int:project_id>/graph.json")
@login_required
def graph_json(project_id):
    project = g.project_for(project_id, "view")
    pending = {n.key for n in q.pending_nodes(project)}
    payload = graph_payload(project.graph(), pending, open_comment_counts(project), project.display)
    payload.update(can_undo=g.can_undo(project), can_redo=g.can_redo(project), status=project.status)
    add_images(payload, project, lambda att: url_for("media.show", project_id=project.id, att_id=att))
    return jsonify(payload)


@bp.get("/p/<int:project_id>/panel")
@login_required
def panel(project_id):
    project = g.project_for(project_id, "view")
    key = request.args.get("node")
    node = g.owned_node(project, key) if key else None
    kind = request.args.get("ask") or None
    if kind and kind not in ("next", "actor", "screen", "data", "error", "branches"):
        abort(400)
    if not project.can_edit:
        return render_template("flow/_panel_readonly.html", project=project,
                               node=node or (project.nodes[0] if project.nodes else None))
    slot = (request.args.get("slot") or "").strip()[:100] or None
    if kind == "next" and slot is None and node is not None:
        labels = g.open_labels(project, node)
        slot = labels[0] if labels else ""
    return render_panel(project, node, kind, slot, focus_changed=False)


@bp.post("/p/<int:project_id>/answer")
@login_required
def answer(project_id):
    project = g.project_for(project_id, "edit")
    log = db.session.get(QuestionLog, request.form.get("log_id", type=int) or 0)
    if log is None or log.project_id != project.id:
        abort(404)
    node = g.owned_node(project, log.node_key)
    question = Question.model_validate(log.options)
    if log.answer:
        return render_panel(project, None, error="To pytanie ma już odpowiedź — pokazuję kolejne.")
    if question.version != project.version_cursor_id:
        return render_panel(project, node, question.kind, question.slot or None, focus_changed=False,
                            error="Mapa zmieniła się od zadania pytania — oto aktualne propozycje.")
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
    project = g.project_for(project_id, "edit")
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
    if "icon" in f:  # "" = automatic, otherwise a known pictogram
        icon = f.get("icon") if f.get("icon") in PICTOGRAMS else None
        g.set_node_data(node, icon=icon)
    return _changed(project, f"Zmieniono krok „{node.title}”", node)


@bp.post("/p/<int:project_id>/node/<key>/delete")
@login_required
def delete_node(project_id, key):
    project = g.project_for(project_id, "edit")
    node = g.owned_node(project, key)
    if node.type == "start":
        return render_panel(project, node, error="Nie można usunąć kroku startowego.", focus_changed=False)
    title = node.title
    g.delete_node(project, node)
    return _changed(project, f"Usunięto krok „{title}”", toast=True)


@bp.post("/p/<int:project_id>/node/<key>/connect")
@login_required
def connect_node(project_id, key):
    project = g.project_for(project_id, "edit")
    node = g.owned_node(project, key)
    target = g.owned_node(project, request.form.get("target", ""))
    label = (request.form.get("label") or "").strip()
    if node.type == "decision":
        open_ = g.open_labels(project, node)
        label = label or (open_[0] if open_ else "")
        if label and label not in node.data.get("branches", []):
            g.set_node_data(node, branches=list(node.data.get("branches", [])) + [label])
    g.add_edge(project, node, target, label)
    return _changed(project, f"Połączono „{node.title}” → „{target.title}”", node, toast=True)


@bp.post("/p/<int:project_id>/node/<key>/end")
@login_required
def mark_end(project_id, key):
    project = g.project_for(project_id, "edit")
    node = g.owned_node(project, key)
    if node.type == "start":
        return render_panel(project, node, error="Start nie może być końcem.", focus_changed=False)
    if g.outgoing(project, node):
        return render_panel(project, node, focus_changed=False,
                            error="Ten krok ma kolejne kroki — usuń je albo dodaj koniec jako nowy krok.")
    node.type = "end"
    return _changed(project, f"Oznaczono „{node.title}” jako koniec", node, toast=True)


@bp.post("/p/<int:project_id>/edge/<int:edge_id>/delete")
@login_required
def delete_edge(project_id, edge_id):
    project = g.project_for(project_id, "edit")
    edge = next((e for e in project.edges if e.id == edge_id), None)
    if edge is None:  # stale panel (e.g. after undo): never delete a different edge by position
        abort(404)
    source = edge.source
    project.edges.remove(edge)
    db.session.delete(edge)
    return _changed(project, f"Usunięto połączenie z „{source.title}”", source, toast=True)


@bp.post("/p/<int:project_id>/edge/<int:edge_id>/insert")
@login_required
def insert_on_edge(project_id, edge_id):
    project = g.project_for(project_id, "edit")
    edge = next((e for e in project.edges if e.id == edge_id), None)
    if edge is None:
        abort(404)
    title = (request.form.get("title") or "").strip()
    if not title:
        return render_panel(project, edge.source, error="Podaj nazwę wstawianego kroku.", focus_changed=False)
    step_type = request.form.get("type", "user_action")
    if step_type not in NODE_TYPES or step_type in ("start", "end", "decision"):
        step_type = "user_action"
    source, target = edge.source, edge.target
    new = g.add_node(project, step_type, title, (request.form.get("actor") or "").strip() or source.actor)
    g.add_edge(project, source, new, edge.label, edge.condition)
    g.add_edge(project, new, target)
    project.edges.remove(edge)
    db.session.delete(edge)
    return _changed(project, f"Wstawiono „{new.title}” między „{source.title}” a „{target.title}”", new,
                    toast=True)


@bp.post("/p/<int:project_id>/undo")
@login_required
def undo(project_id):
    project = g.project_for(project_id, "edit")
    g.step_history(project, older=True)
    db.session.commit()
    return render_panel(project)


@bp.post("/p/<int:project_id>/redo")
@login_required
def redo(project_id):
    project = g.project_for(project_id, "edit")
    g.step_history(project, older=False)
    db.session.commit()
    return render_panel(project)


@bp.post("/p/<int:project_id>/positions")
@login_required
def positions(project_id):
    project = g.project_for(project_id, "edit")
    data = request.get_json(silent=True) or {}
    for node in project.nodes:
        pos = data.get(node.key)
        if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int | float) for v in pos):
            node.pos_x, node.pos_y = float(pos[0]), float(pos[1])
    db.session.commit()
    return {"ok": True}


@bp.post("/p/<int:project_id>/lanes")
@login_required
def lanes(project_id):
    """Change a swimlane's workstation icon or move it up/down. JSON: {role, icon} or {role, move: -1|1}."""
    project = g.project_for(project_id, "edit")
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    move = data.get("move", 0)
    order = lanes_mod.lanes_info(project.graph(), project.display)["order"]
    if not isinstance(role, str) or role not in order or move not in (-1, 0, 1):
        abort(400)
    try:
        project.display = lanes_mod.update(project.display, role, icon=data.get("icon"), move=move, order=order)
    except ValueError as exc:
        abort(400, str(exc))
    db.session.commit()
    return {"ok": True}


@bp.post("/p/<int:project_id>/layout")
@login_required
def reset_layout(project_id):
    project = g.project_for(project_id, "edit")
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
    return _guard_html(g.project_for(project_id, "view"))


def _guard_html(project, **kw):
    """Guard panel: score, open questions, problems with fixes, AI review and AI fill sections."""
    ctx = {"suggestions": None, "log": None, "fill": None, "fill_log": None, "error": None} | kw
    ctx["handoffs"] = lanes_mod.lanes_info(project.graph(), project.display)["handoffs"]
    report = guard.report(project.graph(), open_comment_counts(project))
    return render_template("flow/_guard.html", project=project, report=report, ai=ai_enabled(),
                           titles={n.key: n.title for n in project.nodes}, todo=open_questions(project), **ctx)


def open_slots(project) -> list[dict]:
    """"What next" slots waiting for an answer (helper questions like actor/fields are left to the user)."""
    out = []
    for n in q.pending_nodes(project):
        if q.pending_kind(project, n)[0] == "next":  # every open branch of a decision, not just the first
            out += [{"node_key": n.key, "title": n.title, "slot": label or ""} for label in g.open_labels(project, n)]
    return out


def _guard_response(project, description: str):
    """Save the fix and stay in the guard panel, so the next problem is one click away."""
    g.save_version(project, description)
    db.session.commit()
    resp = make_response(_guard_html(project))
    resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": ""}})
    return with_toast(resp, description)


@bp.post("/p/<int:project_id>/guard/fix")
@login_required
def guard_fix(project_id):
    """Rule-based one-click fixes for guard issues (no AI)."""
    project = g.project_for(project_id, "edit")
    f = request.form
    node = g.owned_node(project, f.get("node_key", ""))
    code = f.get("code")
    if code in ("dead_end", "open_branch", "decision_exits"):
        if node.type == "end" or (code != "dead_end" and node.type != "decision"):
            abort(400)
        labels = [f.get("label") or ""]
        if code == "decision_exits":  # close every unused branch, then add "nie"/"inne" until there are 2 exits
            used = {e.label for e in g.outgoing(project, node)}
            branches = list((node.data or {}).get("branches", []))
            labels = [b for b in branches if b not in used]
            for extra in ("nie", "inne"):
                if len(used) + len(labels) < 2 and extra not in used | set(labels):
                    labels.append(extra)
            g.set_node_data(node, branches=list(dict.fromkeys(branches + labels)))
        for label in labels:
            g.add_edge(project, node, g.add_node(project, "end", "Koniec procesu", node.actor), label)
        return _guard_response(project, f"Zakończono „{node.title}”" + (f" → {', '.join(filter(None, labels))}"
                                                                         if any(labels) else ""))
    if code == "missing_error_path":
        actor = "Klient" if node.actor == "System" else node.actor
        screen = g.add_node(project, "screen", f"Błąd: {node.title}"[:200], actor)
        g.add_edge(project, node, screen, "błąd", g.ERROR_CONDITION)
        g.add_edge(project, screen, g.add_node(project, "end", "Proces przerwany", screen.actor))
        return _guard_response(project, f"Dodano ścieżkę błędu dla „{node.title}”")
    if code in ("similar_steps", "duplicate_step"):
        if code == "similar_steps":
            keep = g.owned_node(project, f.get("other", ""))
        else:
            same = (node.type, node.title.strip().lower())
            keep = next((e.source for e in project.edges if e.target_id == node.id
                         and (e.source.type, e.source.title.strip().lower()) == same), None)
        if keep is None or keep.id == node.id:
            abort(400)
        g.merge_nodes(project, keep, node)
        return _guard_response(project, f"Scalono „{node.title}” z „{keep.title}”")
    abort(400)


@bp.post("/p/<int:project_id>/guard/review")
@login_required
def guard_review(project_id):
    project = g.project_for(project_id, "edit")
    graph = project.graph()
    report = guard.report(graph)
    error, log, suggestions = None, None, None
    reason = spend_ai_request()
    if reason:
        error = f"{reason}."
    else:
        try:
            suggestions = review_map(project, graph, report["issues"])
            log = QuestionLog(project_id=project.id, kind="review", question="Przegląd AI: brakujące wyjątki",
                              options={"suggestions": suggestions}, answer="", source="ai")
            db.session.add(log)
        except AIError as exc:
            error = f"Przegląd AI nieudany: {exc}."
    db.session.commit()
    return _guard_html(project, error=error, suggestions=suggestions, log=log)


MAX_FILL = 12


@bp.post("/p/<int:project_id>/guard/fill")
@login_required
def guard_fill(project_id):
    """AI proposes how to close every open branch in one request; nothing changes until accepted."""
    project = g.project_for(project_id, "edit")
    slots = open_slots(project)[:MAX_FILL]
    if not slots:
        return _guard_html(project, error="Nie ma otwartych gałęzi do uzupełnienia.")
    reason = spend_ai_request()
    if reason:
        return _guard_html(project, error=f"{reason}.")
    try:
        items = fill_map(project, project.graph(), slots)
    except AIError as exc:
        return _guard_html(project, error=f"Uzupełnianie AI nieudane: {exc}.")
    log = QuestionLog(project_id=project.id, kind="fill", question="AI: uzupełnij otwarte gałęzie",
                      options={"items": items}, answer="", source="ai")
    db.session.add(log)
    db.session.commit()
    return _guard_html(project, fill=items, fill_log=log)


@bp.post("/p/<int:project_id>/guard/fill/apply")
@login_required
def guard_fill_apply(project_id):
    project = g.project_for(project_id, "edit")
    log = db.session.get(QuestionLog, request.form.get("log_id", type=int) or 0)
    if log is None or log.project_id != project.id or log.kind != "fill":
        abort(404)
    items = log.options.get("items", [])
    done = {int(i) for i in log.answer.split(";") if i}
    which = request.form.get("index", "all")
    indexes = [i for i in range(len(items)) if i not in done] if which == "all" else [int(which)]
    if any(not 0 <= i < len(items) for i in indexes):
        abort(404)
    added, skipped = 0, 0
    for i in indexes:
        item = items[i]
        node = project.node_by_key(item["node_key"])
        if node is None or (item["slot"] or None) not in g.open_labels(project, node):
            skipped += 1  # already answered elsewhere — never stack a second continuation
            done.add(i)
            continue
        option = Option(label=item["summary"], steps=item["steps"])
        question = Question(kind="next", node_key=node.key, slot=item["slot"], text=item["summary"], options=[option])
        q.apply_option(project, node, question, option)
        done.add(i)
        added += 1
    log.answer = ";".join(str(i) for i in sorted(done))[:1000]
    g.save_version(project, f"AI uzupełniło gałęzie: {added}")
    db.session.commit()
    left = [it for i, it in enumerate(items) if i not in done]
    note = f"Dodano {added}." + (f" Pominięto {skipped} — już mają dalszy ciąg." if skipped else "")
    resp = make_response(_guard_html(project, fill=items, fill_log=log, fill_note=note, fill_done=done)
                         if left else _guard_html(project, fill_note=note))
    resp.headers["HX-Trigger"] = json.dumps({"mapChanged": {"focus": ""}})
    return with_toast(resp, f"AI uzupełniło gałęzie: {added}")


@bp.post("/p/<int:project_id>/guard/apply")
@login_required
def guard_apply(project_id):
    project = g.project_for(project_id, "edit")
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
    return _changed(project, f"Dodano wyjątek: {s['problem']}", created[-1] if created else node, toast=True)


# --- simulation -----------------------------------------------------------------

@bp.get("/p/<int:project_id>/symulacja")
@login_required
def simulate(project_id):
    project = g.project_for(project_id, "view")
    return render_simulation(project, url_for("flow.view", project_id=project.id),
                             lambda **kw: url_for("flow.simulate", project_id=project.id, **kw),
                             lambda att: url_for("media.show", project_id=project.id, att_id=att))


def add_images(payload: dict, project, url) -> dict:
    """Image count and the first image's URL per step (map badge, tooltip, playback)."""
    from ..media.routes import image_counts

    counts = image_counts(project)
    for n in payload["nodes"]:
        count, first = counts.get(n["key"], (0, None))
        n["images"] = count
        n["image_url"] = url(first) if first else ""
    return payload


def render_simulation(project, back_url, sim_url, image_url=None):
    """Shared by the owner view and the public share link."""
    graph = project.graph()
    role = request.args.get("role")
    path = [k for k in (request.args.get("path") or "").split(",") if k]
    state = simulation_state(graph, role, path) if role else None
    actors = sorted({n["actor"] for n in graph["nodes"] if n["actor"]})
    shot = ""
    if state and state.get("node") and image_url:
        from ..media.routes import image_counts

        first = image_counts(project).get(state["node"]["key"], (0, None))[1]
        shot = image_url(first) if first else ""
    return render_template("flow/simulate.html", project=project, actors=actors, role=role, state=state,
                           back_url=back_url, sim_url=sim_url, shot=shot)
