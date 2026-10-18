"""What changed between two map snapshots (graph dicts). Nodes match by key, edges by (source, target, label)."""

FIELDS = {"title": "tytuł", "type": "typ", "actor": "aktor", "description": "opis", "inputs": "dane wejściowe",
          "outputs": "dane wyjściowe"}


def _edge_id(e: dict) -> tuple[str, str, str]:
    return e["source"], e["target"], e.get("label") or ""


def diff_graphs(old: dict, new: dict) -> dict:
    old_nodes = {n["key"]: n for n in old["nodes"]}
    new_nodes = {n["key"]: n for n in new["nodes"]}
    changed = []
    for key in old_nodes.keys() & new_nodes.keys():
        a, b = old_nodes[key], new_nodes[key]
        fields = [(label, a.get(f), b.get(f)) for f, label in FIELDS.items() if (a.get(f) or "") != (b.get(f) or "")]
        if (a.get("data") or {}).get("branches", []) != (b.get("data") or {}).get("branches", []):
            fields.append(("gałęzie", a["data"].get("branches", []), b["data"].get("branches", [])))
        if fields:
            changed.append({"node": b, "fields": fields})

    titles = {**{k: n["title"] for k, n in old_nodes.items()}, **{k: n["title"] for k, n in new_nodes.items()}}
    old_edges = {_edge_id(e) for e in old["edges"]}
    new_edges = {_edge_id(e) for e in new["edges"]}

    def edge_view(e):
        return {"source": titles.get(e[0], e[0]), "target": titles.get(e[1], e[1]), "label": e[2]}

    return {
        "added": [new_nodes[k] for k in new_nodes if k not in old_nodes],
        "removed": [old_nodes[k] for k in old_nodes if k not in new_nodes],
        "changed": sorted(changed, key=lambda c: c["node"]["title"]),
        "edges_added": [edge_view(e) for e in sorted(new_edges - old_edges)],
        "edges_removed": [edge_view(e) for e in sorted(old_edges - new_edges)],
    }


def node_status(diff: dict) -> dict[str, str]:
    """key -> 'added' | 'changed' for highlighting the newer map."""
    status = {n["key"]: "added" for n in diff["added"]}
    status.update({c["node"]["key"]: "changed" for c in diff["changed"]})
    return status
