"""Map mutations, open slots and version history (undo/redo) for a project."""

from flask import abort
from flask_login import current_user

from ..extensions import db
from ..models import Edge, Node, Project, ProjectMember, Version, new_key

ERROR_CONDITION = "error"
DEFAULT_ACTORS = {"automation": "System", "integration": "System", "wait": "System"}
NEEDS_ACTOR = ("user_action", "screen", "automation", "decision", "wait", "integration")


ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
NEED_RANK = {"view": 1, "edit": 2, "owner": 3}
ROLE_LABELS = {"viewer": "podgląd", "editor": "edytor", "owner": "właściciel"}


def project_role(project: Project, user) -> str | None:
    if project.owner_id == user.id:
        return "owner"
    member = ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first()
    return member.role if member else None


def project_for(project_id: int, need: str) -> Project:
    """Every project endpoint goes through here.

    Not a member (or missing project) -> 404, so foreign projects stay invisible.
    Member without enough rights (viewer trying to edit) -> 403.
    """
    project = db.session.get(Project, project_id)
    role = project_role(project, current_user) if project else None
    if role is None:
        abort(404)
    if ROLE_RANK[role] < NEED_RANK[need]:
        abort(403)
    project.current_role = role  # for templates
    return project


def owned_node(project: Project, key: str) -> Node:
    node = project.node_by_key(key)
    if node is None:
        abort(404)
    return node


def add_node(project: Project, type: str, title: str, actor: str = "", description: str = "",
             inputs=None, outputs=None, data=None) -> Node:
    node = Node(
        project=project,
        key=new_key(),
        type=type,
        title=title.strip()[:200] or "Krok",
        actor=(actor or DEFAULT_ACTORS.get(type, "")).strip()[:100],
        description=(description or "").strip(),
        inputs=list(inputs or []),
        outputs=list(outputs or []),
        data=dict(data or {}),
    )
    db.session.add(node)
    db.session.flush()
    return node


def add_edge(project: Project, source: Node, target: Node, label: str = "", condition: str = "") -> Edge:
    edge = Edge(project=project, source_id=source.id, target_id=target.id,
                label=(label or "").strip()[:100], condition=(condition or "").strip()[:300])
    db.session.add(edge)
    db.session.flush()
    return edge


def outgoing(project: Project, node: Node) -> list[Edge]:
    return [e for e in project.edges if e.source_id == node.id]


def delete_node(project: Project, node: Node) -> None:
    for edge in [e for e in project.edges if node.id in (e.source_id, e.target_id)]:
        project.edges.remove(edge)
        db.session.delete(edge)
    project.nodes.remove(node)
    db.session.delete(node)
    db.session.flush()


def set_node_data(node: Node, **values) -> None:
    data = dict(node.data or {})
    data.update(values)
    node.data = data  # reassign so SQLAlchemy sees the JSON change


def open_labels(project: Project, node: Node) -> list[str | None]:
    """Branch labels still waiting for a next step. None = plain 'what next' slot."""
    if node.type == "end":
        return []
    out = outgoing(project, node)
    if node.type == "decision":
        used = {e.label for e in out}
        return [b for b in (node.data or {}).get("branches", []) if b not in used]
    return [] if any(e.condition != ERROR_CONDITION for e in out) else [None]


# --- versions -------------------------------------------------------------

def save_version(project: Project, description: str) -> Version:
    """Snapshot after a change. Drops the redo tail, like any editor."""
    if project.version_cursor_id is not None:
        for v in [v for v in project.versions if v.id > project.version_cursor_id]:
            project.versions.remove(v)
            db.session.delete(v)
    version = Version(project_id=project.id, description=description[:300], snapshot=project.graph())
    project.versions.append(version)
    db.session.flush()
    project.version_cursor_id = version.id
    return version


def load_graph(project: Project, graph: dict) -> None:
    """Replace the whole map with a graph dict (keys preserved)."""
    for edge in list(project.edges):
        db.session.delete(edge)
    for node in list(project.nodes):
        db.session.delete(node)
    project.edges.clear()
    project.nodes.clear()
    db.session.flush()
    by_key = {}
    for n in graph.get("nodes", []):
        node = Node(project=project, key=n["key"], type=n["type"], title=n["title"],
                    description=n.get("description", ""), actor=n.get("actor", ""),
                    inputs=n.get("inputs", []), outputs=n.get("outputs", []), data=n.get("data", {}),
                    pos_x=n.get("x"), pos_y=n.get("y"))
        db.session.add(node)
        by_key[node.key] = node
    db.session.flush()
    for e in graph.get("edges", []):
        if e["source"] in by_key and e["target"] in by_key:
            add_edge(project, by_key[e["source"]], by_key[e["target"]], e.get("label", ""), e.get("condition", ""))


def _neighbour_version(project: Project, older: bool) -> Version | None:
    cursor = project.version_cursor_id
    if cursor is None:
        return None
    candidates = [v for v in project.versions if (v.id < cursor if older else v.id > cursor)]
    if not candidates:
        return None
    return max(candidates, key=lambda v: v.id) if older else min(candidates, key=lambda v: v.id)


def can_undo(project: Project) -> bool:
    return _neighbour_version(project, older=True) is not None


def can_redo(project: Project) -> bool:
    return _neighbour_version(project, older=False) is not None


def step_history(project: Project, older: bool) -> Version | None:
    version = _neighbour_version(project, older)
    if version:
        load_graph(project, version.snapshot)
        project.version_cursor_id = version.id
    return version


def restore_version(project: Project, version: Version) -> None:
    load_graph(project, version.snapshot)
    project.version_cursor_id = max(v.id for v in project.versions)
    save_version(project, f"Przywrócono wersję: {version.description}")
