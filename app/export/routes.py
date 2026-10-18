import json

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pydantic import ValidationError

from ..ai import templates
from ..flow import graph as g
from ..flow.routes import graph_payload
from ..projects.service import project_from_graph
from ..spec.package import PASTE_PROMPT
from ..spec.readiness import readiness
from ..spec.schema import load_spec
from . import builders, tasks

bp = Blueprint("export", __name__)
EXAMPLE = "booking"


def _meta(project) -> dict:
    return {"name": project.name, "start_sentence": project.start_sentence, "mode": project.mode,
            "template": project.template}


def _download(body: str, filename: str, mimetype: str) -> Response:
    return Response(body, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/p/<int:project_id>/eksport")
@login_required
def index(project_id):
    project = g.project_for(project_id, "view")
    graph = project.graph()
    spec = builders.to_markdown(_meta(project), graph)
    target = request.args.get("target", "claude_code")
    project_spec = g.project_spec(project)
    return render_template(
        "export/index.html", project=project, spec=spec, mermaid=builders.to_mermaid(graph),
        prompt=builders.to_prompt(_meta(project), spec, target), target=target, targets=builders.TARGETS,
        task_count=len(tasks.build_tasks(_meta(project), graph)), github_command=tasks.GITHUB_COMMAND,
        ready=readiness(project_spec) if project_spec else None, paste_prompt=PASTE_PROMPT,
    )


@bp.get("/p/<int:project_id>/eksport/<kind>")
@login_required
def download(project_id, kind):
    project = g.project_for(project_id, "view")
    graph = project.graph()
    meta = _meta(project)
    if kind == "spec.md":
        return _download(builders.to_markdown(meta, graph), "specyfikacja.md", "text/markdown")
    if kind == "diagram.mmd":
        return _download(builders.to_mermaid(graph), "diagram.mmd", "text/plain")
    if kind == "proces.bpmn":
        return _download(builders.to_bpmn(graph, project.name), "proces.bpmn", "application/xml")
    if kind == "prompt.md":
        spec = builders.to_markdown(meta, graph)
        return _download(builders.to_prompt(meta, spec, request.args.get("target", "claude_code")),
                         "polecenie.md", "text/markdown")
    if kind == "projekt.json":
        body = json.dumps(builders.to_json(meta, graph, project.spec), ensure_ascii=False, indent=2)
        return _download(body, "projekt.flowmap.json", "application/json")
    if kind == "zadania-jira.csv":
        return _download(tasks.to_jira_csv(tasks.build_tasks(meta, graph)), kind, "text/csv")
    if kind == "zadania-linear.csv":
        return _download(tasks.to_linear_csv(tasks.build_tasks(meta, graph)), kind, "text/csv")
    if kind == "zadania-github.jsonl":
        return _download(tasks.to_github_json(tasks.build_tasks(meta, graph)), kind, "application/x-ndjson")
    return render_template("error.html", code=404, message="Nieznany format eksportu."), 404


def _clean_data(data: dict) -> dict:
    out = {}
    if isinstance(data.get("branches"), list):
        out["branches"] = [str(b)[:100] for b in data["branches"]][:10]
    if isinstance(data.get("tpl"), str):
        out["tpl"] = data["tpl"][:40]
    if isinstance(data.get("asked"), list):
        out["asked"] = [str(a)[:20] for a in data["asked"]][:10]
    return out


@bp.route("/projekty/import", methods=["GET", "POST"])
@login_required
def import_project():
    if request.method == "POST":
        upload = request.files.get("file")
        try:
            if not upload:
                raise ValueError("Wybierz plik JSON.")
            parsed = builders.parse_project_file(json.load(upload.stream))
        except (ValueError, UnicodeDecodeError) as exc:
            flash(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError)
                  else "Plik nie jest poprawnym JSON-em.", "error")
            return redirect(url_for("export.import_project"))
        graph = {
            "nodes": [n.model_dump() | {"data": _clean_data(n.data), "inputs": [str(v)[:100] for v in n.inputs][:30],
                                        "outputs": [str(v)[:100] for v in n.outputs][:30]} for n in parsed.nodes],
            "edges": [e.model_dump() for e in parsed.edges],
        }
        if parsed.spec is not None:
            try:
                graph["spec"] = load_spec(parsed.spec).model_dump(mode="json")
            except ValidationError:
                flash("Specyfikacja w pliku była niepoprawna — odbudowano ją z mapy.", "info")
        p = parsed.project
        project = project_from_graph(current_user, p.name, p.start_sentence, p.mode, p.template, graph,
                                     "Zaimportowano z pliku")
        flash("Projekt zaimportowany.", "success")
        return redirect(url_for("flow.view", project_id=project.id))
    return render_template("export/import.html")


# --- public example ---------------------------------------------------------------

def _example():
    tpl = templates.TEMPLATES[EXAMPLE]
    meta = {"name": "Przykład: " + tpl["name"], "start_sentence": "Klient chce umówić wizytę w salonie",
            "mode": "thorough", "template": EXAMPLE}
    return meta, templates.full_graph(EXAMPLE, meta["start_sentence"])


@bp.get("/przyklad")
def example():
    meta, graph = _example()
    return render_template("export/example.html", meta=meta, spec=builders.to_markdown(meta, graph),
                           mermaid=builders.to_mermaid(graph))


@bp.get("/przyklad/graph.json")
def example_graph():
    _meta_, graph = _example()
    return graph_payload(graph)
