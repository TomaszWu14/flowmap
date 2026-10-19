"""One AI call proposing spec changes; nothing changes until the analyst accepts a proposal."""

import json
import secrets
from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PField

from ..ai.client import _obj, _prompt, call_tool, compact_graph
from .schema import (
    VISION_FIELDS,
    Alternative,
    Field,
    Nfr,
    Notification,
    Proposal,
    Relation,
    RuleRow,
    Spec,
    Status,
    Transition,
    new_key,
)

KINDS = ["set_field_type", "add_field", "add_relation", "add_status", "add_transition", "set_permission",
         "add_notification", "add_nfr", "other_note", "add_alternative", "add_rule_row"]
KIND_SECTIONS = {"add_alternative": ("use_cases",), "add_rule_row": ("rules",),
                 "set_field_type": ("entities",), "add_field": ("entities",), "add_relation": ("entities",),
                 "add_status": ("states",), "add_transition": ("states",), "set_permission": ("roles",)}
PATCH_KEYS = ["field", "type", "name", "required", "to_entity", "kind", "label", "final", "from", "to", "entity",
              "read", "create", "update", "delete", "trigger", "channel", "recipient_role", "category", "text",
              "condition", "result"]
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
                  "add_notification", "add_nfr", "other_note", "add_alternative", "add_rule_row"]
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
    if kind == "set_vision":
        for f in VISION_FIELDS:
            if f in p:
                value = p[f] if f == "problem" else [x.strip() for x in str(p[f]).splitlines() if x.strip()]
                setattr(spec.vision, f, value)
                if f not in spec.vision.manual:
                    spec.vision.manual.append(f)
    elif kind in ("add_nfr", "other_note"):
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
        if kind in KIND_SECTIONS and _sec not in KIND_SECTIONS[kind]:
            raise ValueError("Propozycja AI wskazuje niewłaściwy element — odrzuć ją.")
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
            from_name, to_name = p.get("from", ""), p.get("to", "")
            if from_name not in {s.name for s in item.statuses} or to_name not in {s.name for s in item.statuses}:
                raise ValueError("Propozycja jest nieaktualna — nie ma takiego statusu.")
            item.transitions.append(Transition(from_status=from_name, to_status=to_name))
        elif kind == "add_alternative":
            item.alternatives.append(Alternative(condition=p.get("condition") or proposal.summary,
                                                 steps=[s.strip() for s in p.get("text", "").split(";") if s.strip()]))
        elif kind == "add_rule_row":
            item.rows.append(RuleRow(condition=p.get("condition") or proposal.summary, result=p.get("result") or "—"))
        elif kind == "set_permission":
            entity_key = p.get("entity", "")
            if not any(e.key == entity_key for e in spec.entities):
                raise ValueError("Propozycja jest nieaktualna — nie ma takiej encji.")
            perms = {k: p.get(k, "none") for k in ("read", "create", "update", "delete")}
            if any(v not in ("all", "own", "none") for v in perms.values()):
                raise ValueError("Propozycja jest nieaktualna — niepoprawna wartość uprawnienia.")
            item.permissions[entity_key] = perms
        item.source = "ai"
    spec.proposals = [x for x in spec.proposals if x.id != proposal.id]
    return Spec.model_validate(spec.model_dump(mode="json"))  # re-validate after the patch
