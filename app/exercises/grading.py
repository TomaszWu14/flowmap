"""Exercise grading (Opus): each expert expectation judged met / partial / missed, a 0–100 score, strengths, fixes."""

import json
from typing import Literal

from pydantic import BaseModel, model_validator
from pydantic import Field as PField

from ..ai.client import _obj, _prompt, call_tool, compact_graph
from ..design.uml import class_diagram, use_case_diagram
from ..trainer.rubric import evaluate
from .catalog import Exercise

VERDICTS = {"met": "spełnione", "partial": "częściowo", "missed": "niespełnione"}
TOOL = {"name": "grade_exercise", "strict": True, "description": "Ocena etapu ćwiczenia według oczekiwań eksperta.",
        "input_schema": _obj({
            "expectations": {"type": "array", "items": _obj({"index": {"type": "integer"},
                                                             "verdict": {"type": "string", "enum": list(VERDICTS)},
                                                             "comment": {"type": "string"}})},
            "score": {"type": "integer"},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "fixes": {"type": "array", "items": {"type": "string"}}})}

Text = PField(min_length=1, max_length=600)


class _Verdict(BaseModel):
    index: int
    verdict: Literal["met", "partial", "missed"]
    comment: str = Text


class _Grade(BaseModel):
    expectations: list[_Verdict]
    score: int = PField(ge=0, le=100)
    strengths: list[str] = PField(min_length=1, max_length=3)
    fixes: list[str] = PField(min_length=1, max_length=3)


def _grade_model(count: int) -> type[_Grade]:
    class Graded(_Grade):
        @model_validator(mode="after")
        def each_once(self):
            if sorted(v.index for v in self.expectations) != list(range(count)):
                raise ValueError("każde oczekiwanie dokładnie raz")
            return self

    return Graded


def grade(project, ex: Exercise, stage: int, spec) -> dict:
    """One Opus call. Raises AIError (from call_tool) when the model fails twice; the result is the stored feedback."""
    expected = ex.expectations(stage)
    graph = project.graph()
    rules = evaluate(project)[stage - 1]  # [map, design] — the same order as the stages
    if stage == 1:
        work = f"Mapa procesu (JSON):\n{compact_graph(graph)}"
    else:
        spec_json = json.dumps(spec.model_dump(mode="json", exclude={"proposals"}), ensure_ascii=False)
        work = (f"Specyfikacja (JSON):\n{spec_json}\n\nDiagram klas (Mermaid):\n{class_diagram(spec)}\n"
                f"Diagram przypadków użycia (Mermaid):\n{use_case_diagram(spec, project.name)}\n"
                f"Mapa procesu, z której powstał projekt (JSON):\n{compact_graph(graph)}")
    prompt = _prompt("grade_exercise", title=ex.title, brief=ex.brief, start_sentence=ex.start_sentence,
                     stage_name="mapa procesu" if stage == 1 else "projekt aplikacji",
                     expectations="\n".join(f"{i}. {text}" for i, text in enumerate(expected)),
                     count=len(expected), work=work, rules_summary=f"{rules['label']} {rules['score']}/100")
    result = call_tool(prompt, TOOL, _grade_model(len(expected)))
    by_index = {v.index: v for v in result.expectations}
    return {"score": result.score, "rules_score": rules["score"],
            "mode": "learning" if project.learning else "work",
            "expectations": [{"text": text, "verdict": by_index[i].verdict, "comment": by_index[i].comment}
                             for i, text in enumerate(expected)],
            "strengths": result.strengths, "fixes": result.fixes}
