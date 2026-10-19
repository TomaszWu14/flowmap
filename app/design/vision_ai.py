"""AI draft of the vision and MVP scope, returned as one proposal the analyst accepts or rejects."""

import json
import secrets

from pydantic import BaseModel
from pydantic import Field as PField

from ..ai.client import _obj, _prompt, call_tool, compact_graph
from ..spec.schema import VISION_FIELDS, Proposal, Spec

_LIST = {"type": "array", "items": {"type": "string"}}
TOOL = {"name": "draft_vision", "strict": True, "description": "Wizja i zakres MVP aplikacji (MoSCoW).",
        "input_schema": _obj({"problem": {"type": "string"}, **{f: _LIST for f in VISION_FIELDS[1:]}})}


class _AiVision(BaseModel):
    problem: str = PField(min_length=1, max_length=1000)
    goals: list[str] = PField(max_length=8)
    metrics: list[str] = PField(max_length=8)
    must: list[str] = PField(max_length=20)
    should: list[str] = PField(max_length=20)
    could: list[str] = PField(max_length=20)
    wont: list[str] = PField(max_length=10)


def draft_vision(graph: dict, spec: Spec, start_sentence: str) -> Proposal:
    spec_json = json.dumps(spec.model_dump(mode="json", exclude={"proposals", "vision"}), ensure_ascii=False)
    prompt = _prompt("vision", start_sentence=start_sentence, graph_json=compact_graph(graph), spec_json=spec_json)
    result: _AiVision = call_tool(prompt, TOOL, _AiVision)
    patch = {"problem": result.problem} | {f: "\n".join(x.strip()[:300] for x in getattr(result, f) if x.strip())
                                           for f in VISION_FIELDS[1:]}
    return Proposal(id=secrets.token_hex(4), kind="set_vision", target_key="vision",
                    summary="Wizja i zakres MVP (propozycja AI)", patch=patch)
