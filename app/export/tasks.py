"""Backlog export: one ticket per step, ready to import into Jira, Linear or GitHub Issues."""

import csv
import io
import json

from ..ai.rules import needs_error_path
from ..models import NODE_TYPE_LABELS
from .builders import _ordered

SKIP = ("start", "end")


def _criteria(n: dict, graph: dict, titles: dict) -> list[str]:
    out = [f"Pole „{f}” jest wymagane i walidowane" for f in n.get("inputs", [])]
    out += [f"Widać „{f}”" for f in n.get("outputs", [])]
    for e in graph["edges"]:
        if e["source"] == n["key"]:
            label = f" (gdy „{e['label']}”)" if e.get("label") else ""
            out.append(f"Dalej: „{titles[e['target']]}”{label}")
    if n["type"] == "decision":
        out += [f"Obsłużona gałąź „{b}”" for b in (n.get("data") or {}).get("branches", [])]
    if needs_error_path(n):
        out.append("Błąd jest obsłużony i widoczny dla użytkownika")
    return out or ["Krok da się wykonać i zapisuje wynik"]


def build_tasks(meta: dict, graph: dict) -> list[dict]:
    titles = {n["key"]: n["title"] for n in graph["nodes"]}
    tasks = []
    for n in _ordered(graph):
        if n["type"] in SKIP:
            continue
        human = n["type"] in ("user_action", "screen") and n.get("actor") and n["actor"] != "System"
        title = f"{n['actor']}: {n['title']}" if human else f"{NODE_TYPE_LABELS[n['type']]}: {n['title']}"
        criteria = _criteria(n, graph, titles)
        body = []
        if human:
            body.append(f"Jako {n['actor']} chcę: {n['title'][:1].lower()}{n['title'][1:]}.")
        if n.get("description"):
            body.append(n["description"])
        body.append("Kryteria akceptacji:\n" + "\n".join(f"- [ ] {c}" for c in criteria))
        body.append(f"Proces: {meta['name']} — wygenerowano w FlowMap.")
        tasks.append({
            "title": title[:250],
            "body": "\n\n".join(body),
            "type": "Story" if human else "Task",
            "labels": ["flowmap", n["type"].replace("_", "-")],
        })
    return tasks


def _cell(value: str) -> str:
    """Neutralise spreadsheet formulas (=, +, -, @) coming from user-written step titles."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    # nosemgrep: use-defusedcsv — _cell() neutralises spreadsheet formulas
    csv.writer(buf, lineterminator="\n").writerows([[_cell(c) for c in row] for row in rows])
    return buf.getvalue()


def to_jira_csv(tasks: list[dict]) -> str:
    """Jira: System → External system import → CSV; map Summary, Description, Issue Type, Labels."""
    return _csv([["Summary", "Description", "Issue Type", "Labels", "Labels"]] +
                [[t["title"], t["body"], t["type"], *t["labels"][:2]] for t in tasks])


def to_linear_csv(tasks: list[dict]) -> str:
    """Linear: Settings → Import/Export → CSV."""
    return _csv([["Title", "Description", "Labels"]] + [[t["title"], t["body"], ",".join(t["labels"])] for t in tasks])


def to_github_json(tasks: list[dict]) -> str:
    """One GitHub Issues API payload per line (JSON Lines) — fed to `gh api` without touching the shell."""
    lines = (json.dumps({"title": t["title"], "body": t["body"], "labels": t["labels"]}, ensure_ascii=False)
             for t in tasks)
    return "".join(line + "\n" for line in lines)


GITHUB_COMMAND = ("while IFS= read -r issue; do printf '%s' \"$issue\" | gh api repos/OWNER/REPO/issues --input -; "
                  "done < zadania-github.jsonl")
