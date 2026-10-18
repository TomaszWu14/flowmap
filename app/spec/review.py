"""One AI call proposing spec changes; nothing changes until the analyst accepts a proposal."""

import json
import secrets
from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PField

from ..ai.client import _obj, _prompt, call_tool, compact_graph
from .schema import Field, Nfr, Notification, Proposal, Relation, Spec, Status, Transition, new_key

KINDS = ["set_field_type", "add_field", "add_relation", "add_status", "add_transition", "set_permission",
         "add_notification", "add_nfr", "other_note"]
PATCH_KEYS = ["field", "type", "name", "required", "to_entity", "kind", "label", "final", "from", "to", "entity",
              "read", "create", "update", "delete", "trigger", "channel", "recipient_role", "category", "text"]
_PATCH = _obj({k: ({"type": "boolean"} if k in ("required", "final") else {"type": "string"}) for k in PATCH_KEYS})
TOOL = {
    "name": "propose_spec_changes", "strict": True,
    "description": "Lista propozycji poprawek specyfikacji technicznej.",
    "input_schema": _obj({"proposals": {"type": "array", "items": _obj({
        "kind": {"type": "string", "enum": KINDS}, "target_key": {"type": "string"},
        "summary": {"type": "string"}, "patch": _PATCH})}}),
}


class _AiProposal(BaseModel):
    kind: Literal["set_field_type", "add_field", "add_relation", "add_status", "add_transition", "set_permission",
                  "add_notification", "add_nfr", "other_note"]
    target_key: str = ""
    summary: str = PField(min_length=1, max_length=300)
    patch: dict


class _AiReview(BaseModel):
    proposals: list[_AiProposal] = PField(max_length=12)


def review_spec(graph: dict, spec: Spec, start_sentence: str) -> list[Proposal]:
    spec_json = json.dumps(spec.model_dump(mode="json", exclude={"proposals"}), ensure_ascii=False)
    prompt = _prompt("spec_review", start_sentence=start_sentence, graph_json=compact_graph(graph),
                      spec_json=spec_json)
    result: _AiReview = call_tool(prompt, TOOL, _AiReview)
    return [Proposal(id=secrets.token_hex(4), kind=p.kind, target_key=p.target_key, summary=p.summary,
                     patch={k: v for k, v in p.patch.items() if v not in ("", None)}) for p in result.proposals]


def apply_proposal(spec: Spec, proposal: Proposal) -> Spec:
    """Apply an accepted proposal. Raises ValueError (Polish) when its target no longer exists or patch is bad."""
    spec = spec.model_copy(deep=True)
    p, kind = proposal.patch, proposal.kind
    if kind in ("add_nfr", "other_note"):
        spec.nfr.append(Nfr(key=new_key("nfr"), source="ai", category=p.get("category", "other"),
                            text=p.get("text") or proposal.summary))
    elif kind == "add_notification":
        spec.notifications.append(Notification(key=new_key("notification"), source="ai",
                                                trigger=p.get("trigger", proposal.summary),
                                                channel=p.get("channel", "email"),
                                                recipient_role=p.get("recipient_role", ""), summary=proposal.summary))
    else:
        _sec, item = spec.find(proposal.target_key)
        if item is None:
            raise ValueError("Propozycja jest nieaktualna — element, którego dotyczy, już nie istnieje.")
        if kind == "set_field_type":
            field = next((f for f in item.fields if f.name == p.get("field")), None)
            if field is None:
                raise ValueError("Propozycja jest nieaktualna — nie ma takiego pola.")
            field.type = Field(key="x", name="x", type=p.get("type", "text")).type
        elif kind == "add_field":
            item.fields.append(Field(key=f"field:{secrets.token_hex(3)}", name=p.get("name", "pole"),
                                     type=p.get("type", "text"), required=bool(p.get("required"))))
        elif kind == "add_relation":
            item.relations.append(Relation(key=new_key("rel"), to_entity=p.get("to_entity", ""),
                                           kind=p.get("kind", "1-n"), label=p.get("label", "")))
        elif kind == "add_status":
            item.statuses.append(Status(name=p.get("name", "nowy status"), final=bool(p.get("final"))))
        elif kind == "add_transition":
            item.transitions.append(Transition(from_status=p.get("from", ""), to_status=p.get("to", "")))
        elif kind == "set_permission":
            item.permissions[p.get("entity", "")] = {k: p.get(k, "none")
                                                      for k in ("read", "create", "update", "delete")}
        item.source = "ai"
    spec.proposals = [x for x in spec.proposals if x.id != proposal.id]
    return Spec.model_validate(spec.model_dump(mode="json"))  # re-validate after the patch
