"""Qualitative AI assessment (Opus): four 0–5 criteria with reasons and one top fix; 30% of the mixed score."""

import json
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic import Field as PField

from ..ai.client import _obj, _prompt, call_tool, compact_graph

LABELS = {"naming": "Nazewnictwo", "business": "Sens biznesowy", "exceptions": "Wyjątki branżowe",
          "decisions": "Jakość decyzji"}
TOOL = {"name": "assess_quality", "strict": True, "description": "Jakościowa ocena mapy procesu i projektu aplikacji.",
        "input_schema": _obj({
            "criteria": {"type": "array", "items": _obj({"code": {"type": "string", "enum": list(LABELS)},
                                                          "score": {"type": "integer"},
                                                          "reason": {"type": "string"}})},
            "top_fix": {"type": "string"}})}


class _Criterion(BaseModel):
    code: Literal["naming", "business", "exceptions", "decisions"]
    score: int = PField(ge=0, le=5)
    reason: str = PField(min_length=1, max_length=600)


class _Assessment(BaseModel):
    criteria: list[_Criterion]
    top_fix: str = PField(min_length=1, max_length=600)

    @field_validator("criteria")
    @classmethod
    def each_once(cls, v):
        if sorted(c.code for c in v) != sorted(LABELS):
            raise ValueError("każde kryterium dokładnie raz")
        return v


def assess(project, graph: dict, spec, results: list[dict]) -> dict:
    """One Opus call. Raises AIError (from call_tool) when the model fails twice."""
    spec_json = json.dumps(spec.model_dump(mode="json", exclude={"proposals"}), ensure_ascii=False) if spec else "{}"
    summary = "; ".join(f"{r['label']} {r['score']}/100" for r in results)
    prompt = _prompt("assess", start_sentence=project.start_sentence, graph_json=compact_graph(graph),
                     spec_json=spec_json, rules_summary=summary)
    result: _Assessment = call_tool(prompt, TOOL, _Assessment)
    order = list(LABELS)
    criteria = [{"code": c.code, "label": LABELS[c.code], "score": c.score, "reason": c.reason}
                for c in sorted(result.criteria, key=lambda c: order.index(c.code))]
    return {"criteria": criteria, "top_fix": result.top_fix,
            "pct": round(100 * sum(c.score for c in result.criteria) / 20)}
