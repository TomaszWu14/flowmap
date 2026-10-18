"""Anthropic calls. Every answer comes back as a tool call, validated by Pydantic."""

import json
from pathlib import Path

import anthropic
from flask import current_app
from pydantic import BaseModel, ValidationError

from .schemas import AiDraft, AiNextQuestion, AiReview, Option, Question, StepSpec

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
STEP_TYPES = ["user_action", "screen", "automation", "decision", "wait", "integration", "end"]


class AIError(Exception):
    """User-presentable AI failure (Polish message)."""


def ai_enabled() -> bool:
    from .. import settings

    return bool(current_app.config.get("ANTHROPIC_API_KEY")) and bool(settings.get("ai_enabled"))


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=current_app.config["ANTHROPIC_API_KEY"],
        timeout=current_app.config["AI_TIMEOUT_SECONDS"],
        max_retries=1,
    )


def _prompt(name: str, **values) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").format(**values)


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


_STEP = _obj({
    "type": {"type": "string", "enum": STEP_TYPES},
    "title": {"type": "string"},
    "actor": {"type": "string"},
    "description": {"type": "string"},
    "branches": {"type": "array", "items": {"type": "string"}},
})

NEXT_TOOL = {
    "name": "propose_next_steps",
    "description": "Zwraca pytanie 'co dalej?' i 3-5 proponowanych odpowiedzi (kafelków).",
    "strict": True,
    "input_schema": _obj({
        "question": {"type": "string"},
        "options": {"type": "array", "items": _obj({
            "label": {"type": "string"},
            "steps": {"type": "array", "items": _STEP},
            "connect_to_key": {"type": "string"},
        })},
    }),
}

REVIEW_TOOL = {
    "name": "report_missing_steps",
    "description": "Zwraca listę brakujących wyjątków z propozycjami kroków do dodania.",
    "strict": True,
    "input_schema": _obj({
        "suggestions": {"type": "array", "items": _obj({
            "problem": {"type": "string"},
            "node_key": {"type": "string"},
            "edge_label": {"type": "string"},
            "steps": {"type": "array", "items": _STEP},
        })},
    }),
}


DRAFT_TOOL = {
    "name": "draft_process_map",
    "description": "Zwraca pierwszą wersję mapy procesu: kroki i połączenia.",
    "strict": True,
    "input_schema": _obj({
        "steps": {"type": "array", "items": _obj({
            "key": {"type": "string"},
            "type": {"type": "string", "enum": ["start", *STEP_TYPES]},
            "title": {"type": "string"},
            "actor": {"type": "string"},
            "description": {"type": "string"},
            "branches": {"type": "array", "items": {"type": "string"}},
        })},
        "edges": {"type": "array", "items": _obj({
            "source": {"type": "string"},
            "target": {"type": "string"},
            "label": {"type": "string"},
        })},
    }),
}


def compact_graph(graph: dict) -> str:
    """Only the map goes to the model: no account data, no positions."""
    nodes = [
        {k: n[k] for k in ("key", "type", "title", "actor")} | (
            {"branches": n["data"]["branches"]} if n.get("data", {}).get("branches") else {})
        for n in graph["nodes"]
    ]
    edges = [{k: e[k] for k in ("source", "target", "label") if e.get(k)} for e in graph["edges"]]
    return json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)


def call_tool(prompt: str, tool: dict, model_cls: type[BaseModel]) -> BaseModel:
    """One request + one retry when the tool payload fails validation."""
    client = _client()
    system = _prompt("system")
    last_error = "brak wywołania narzędzia"
    for _attempt in range(2):
        try:
            response = client.messages.create(
                model=current_app.config["ANTHROPIC_MODEL"],
                max_tokens=8000,
                system=system,
                tools=[tool],
                tool_choice={"type": "auto"},
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APITimeoutError as exc:
            raise AIError("przekroczono czas odpowiedzi") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("limit zapytań API, spróbuj za chwilę") from exc
        except anthropic.AuthenticationError as exc:
            raise AIError("nieprawidłowy klucz API") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"błąd API {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("brak połączenia z API") from exc
        if response.stop_reason == "refusal":
            raise AIError("model odmówił odpowiedzi")
        block = next((b for b in response.content if b.type == "tool_use" and b.name == tool["name"]), None)
        if block is None:
            continue
        try:
            return model_cls.model_validate(block.input)
        except ValidationError as exc:
            last_error = f"niepoprawna odpowiedź ({exc.error_count()} błędów walidacji)"
            current_app.logger.warning("AI payload invalid: %s", exc)
    raise AIError(last_error)


def _spec(step) -> StepSpec:
    data = step.model_dump()
    if step.type != "decision":
        data["branches"] = []
    elif len(step.branches) < 2:
        data["branches"] = ["tak", "nie"]
    return StepSpec(**data)


def ask_next_step(project, graph: dict, node: dict, slot: str | None) -> Question:
    keys = {n["key"] for n in graph["nodes"]}
    prompt = _prompt(
        "next_step",
        start_sentence=project.start_sentence,
        mode_description=("szybki: opcje mogą zawierać kilka kroków naraz" if project.mode == "quick"
                          else "dokładny: jeden krok na opcję, uwzględnij wyjątki"),
        graph_json=compact_graph(graph),
        node_key=node["key"], node_title=node["title"], node_type=node["type"],
        slot_text=f", gałąź „{slot}”" if slot else "",
        max_steps=4 if project.mode == "quick" else 1,
    )
    result: AiNextQuestion = call_tool(prompt, NEXT_TOOL, AiNextQuestion)
    options = []
    for opt in result.options:
        steps = []
        for s in opt.steps:
            steps.append(_spec(s))
            if s.type in ("decision", "end"):
                break
        connect = opt.connect_to_key if opt.connect_to_key in keys else ""
        options.append(Option(label=opt.label, steps=steps, connect_to=connect))
    return Question(kind="next", node_key=node["key"], slot=slot or "", text=result.question,
                    hint="Propozycje AI. Możesz też wpisać własny krok.", options=options, source="ai")


def draft_map(text: str) -> dict:
    """Graph dict drafted by the model from free text. Raises AIError."""
    result: AiDraft = call_tool(_prompt("draft", text=text), DRAFT_TOOL, AiDraft)
    nodes = []
    for s in result.steps:
        data = {}
        if s.type == "decision":
            data["branches"] = list(dict.fromkeys(b.strip()[:100] for b in s.branches if b.strip())) or ["tak", "nie"]
        nodes.append({"key": s.key, "type": s.type, "title": s.title, "actor": s.actor, "description": s.description,
                      "inputs": [], "outputs": [], "data": data})
    edges = [{"source": e.source, "target": e.target, "label": e.label, "condition": ""} for e in result.edges]
    return {"nodes": nodes, "edges": edges}


def review_map(project, graph: dict, issues: list[dict]) -> list[dict]:
    prompt = _prompt(
        "review",
        start_sentence=project.start_sentence,
        graph_json=compact_graph(graph),
        issues="\n".join(f"- {i['message']}" for i in issues) or "- brak",
    )
    result: AiReview = call_tool(prompt, REVIEW_TOOL, AiReview)
    keys = {n["key"] for n in graph["nodes"]}
    return [
        {"problem": s.problem, "node_key": s.node_key, "edge_label": s.edge_label,
         "steps": [_spec(st).model_dump() for st in s.steps]}
        for s in result.suggestions if s.node_key in keys
    ]
