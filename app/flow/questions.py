"""Which question to ask next, and how an answer changes the map."""


from ..ai import rules
from ..ai.client import AIError, ai_enabled, ask_next_step, spend_ai_request
from ..ai.draft import _lines, _title, guess_actor, guess_type
from ..ai.schemas import Option, Question
from ..extensions import db
from ..models import Node, Project, QuestionLog
from . import graph as g


def pending_kind(project: Project, node: Node) -> tuple[str, str | None] | None:
    """(kind, slot label) of the question waiting on this node, or None when the node is done."""
    nd = node.to_dict()
    if node.type == "decision" and not nd["data"].get("branches"):
        return "branches", None
    helpers = rules.helper_kinds(nd, project.mode)
    if helpers:
        return helpers[0], None
    labels = g.open_labels(project, node)
    if labels:
        return "next", labels[0]
    return None


def pending_nodes(project: Project) -> list[Node]:
    """Nodes with an open question, in walk order from the start node."""
    order = _walk_order(project)
    return [n for n in order if pending_kind(project, n)]


def _walk_order(project: Project) -> list[Node]:
    by_id = {n.id: n for n in project.nodes}
    children: dict[int, list[int]] = {}
    for e in project.edges:
        children.setdefault(e.source_id, []).append(e.target_id)
    starts = [n for n in project.nodes if n.type == "start"] or project.nodes[:1]
    seen, order, queue = set(), [], [n.id for n in starts]
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        order.append(by_id[nid])
        queue.extend(children.get(nid, []))
    return order + [n for n in project.nodes if n.id not in seen]


def build_question(project: Project, node: Node, kind: str, slot: str | None) -> Question:
    graph = project.graph()
    nd = node.to_dict()
    if kind == "branches":
        return rules.branches_question(nd)
    if kind != "next":
        return rules.helper_question(graph, nd, kind, project.template)
    fallback = rules.next_question(graph, nd, slot, project.mode, project.template)
    if not ai_enabled():
        return fallback
    reason = spend_ai_request()
    if reason:
        fallback.notice = f"{reason} — podpowiedzi z reguł."
        return fallback
    try:
        question = ask_next_step(project, graph, nd, slot)
    except AIError as exc:
        fallback.notice = f"AI niedostępne ({exc}) — podpowiedzi z reguł."
        return fallback
    question.options = question.options[:4] + [fallback.options[-1]]  # always offer "Koniec procesu"
    return question


def current_question(project: Project, node: Node, kind: str | None = None, slot: str | None = None):
    """Return (QuestionLog, Question). Reuses an unanswered log so re-rendering costs no AI call."""
    if kind is None:
        pk = pending_kind(project, node)
        if pk is None:
            return None, None
        kind, slot = pk
    log = (QuestionLog.query.filter_by(project_id=project.id, node_key=node.key, kind=kind, answer="")
           .order_by(QuestionLog.id.desc()).first())
    if (log and log.options and log.options.get("slot", "") == (slot or "")
            and log.options.get("version") == project.version_cursor_id):
        return log, Question.model_validate(log.options)
    question = build_question(project, node, kind, slot)
    question.version = project.version_cursor_id
    log = QuestionLog(project_id=project.id, node_key=node.key, kind=kind, question=question.text,
                      options=question.model_dump(), answer="", source=question.source)
    db.session.add(log)
    db.session.commit()
    return log, question


def option_from_other(kind: str, form) -> Option:
    """Build an Option from the free-text 'inne' form."""
    text = (form.get("text") or "").strip()
    if not text:
        raise ValueError("Wpisz odpowiedź w polu „inne”.")
    if kind == "actor":
        return Option(label=text, kind="actor", values=[text[:100]])
    if kind in ("screen", "data", "branches"):
        values = [v.strip() for v in text.split(",") if v.strip()]
        if kind == "branches" and len(values) < 2:
            raise ValueError("Decyzja potrzebuje co najmniej dwóch wyjść (po przecinku).")
        return Option(label=text, kind="branches" if kind == "branches" else "fields", values=values)
    error = kind == "error"
    edge = {"edge_label": (form.get("edge_label") or ("błąd" if error else "")).strip(),
            "edge_condition": "error" if error else ""}
    actor = (form.get("actor") or "").strip()
    lines = _lines(text) if "\n" in text else [text]
    if len(lines) > 1:  # one step per line, types guessed like "Mapa z dokumentu"
        steps = []
        for line in lines:
            step_type = guess_type(line)
            steps.append({"type": step_type, "title": _title(line), "actor": actor or guess_actor(line, step_type, ""),
                          **({"branches": ["tak", "nie"]} if step_type == "decision" else {})})
            if step_type == "end":
                break
        return Option(label=f"{steps[0]['title']} (+{len(steps) - 1})", steps=steps, **edge)
    step_type = form.get("type") or "user_action"
    step = {"type": step_type, "title": text, "actor": actor}
    if step_type == "decision":
        branches = [b.strip() for b in (form.get("branches") or "").split(",") if b.strip()]
        step["branches"] = branches if len(branches) >= 2 else ["tak", "nie"]
    return Option(label=text, steps=[step], **edge)


def apply_option(project: Project, node: Node, question: Question, option: Option) -> list[Node]:
    """Mutate the map according to the chosen option. Returns created nodes."""
    created: list[Node] = []
    if question.kind in ("actor", "screen", "data", "error"):
        asked = list(node.data.get("asked", [])) + [question.kind]
        g.set_node_data(node, asked=asked)
    if option.kind == "skip":
        return created
    if option.kind == "actor":
        node.actor = option.values[0][:100]
        return created
    if option.kind == "fields":
        if question.kind == "screen":
            node.outputs = option.values
        else:
            node.inputs = option.values
        return created
    if option.kind == "branches":
        g.set_node_data(node, branches=list(dict.fromkeys(option.values)))
        return created

    slot = question.slot or None
    first_label = slot or option.edge_label
    if option.kind == "connect":
        target = g.owned_node(project, option.connect_to)
        g.add_edge(project, node, target, first_label, option.edge_condition)
        return created

    prev, label = node, None
    for i, spec in enumerate(option.steps):
        data = {"tpl": spec.tpl} if spec.tpl else {}
        if spec.type == "decision" and spec.branches:
            data["branches"] = list(dict.fromkeys(spec.branches))
        new = g.add_node(project, spec.type, spec.title, spec.actor, spec.description, spec.inputs, spec.outputs, data)
        if i == 0:
            g.add_edge(project, prev, new, first_label, option.edge_condition)
        else:
            g.add_edge(project, prev, new, label or "")
        created.append(new)
        prev = new
        if spec.type == "end":
            break
        if spec.type == "decision":
            # Following steps continue on the first branch; the other branches stay open as questions.
            label = (data.get("branches") or ["tak"])[0]
            if i == len(option.steps) - 1:
                break
        else:
            label = None
    if option.connect_to and created and prev.type not in ("decision", "end") and label is None:
        target = node if option.connect_to == "source" else project.node_by_key(option.connect_to)
        if target is not None:
            g.add_edge(project, prev, target)
    return created


def next_focus(project: Project, created: list[Node], node: Node) -> Node | None:
    """Where the panel goes after an answer: newest node first (depth-first), then the same node, then walk order."""
    for candidate in [*reversed(created), node]:
        if pending_kind(project, candidate):
            return candidate
    remaining = pending_nodes(project)
    return remaining[0] if remaining else None
