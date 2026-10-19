"""Plain-text forms <-> spec items. One list entry per line, columns separated by '|'."""

from pydantic import ValidationError

from .derive import slug
from .schema import (
    FIELD_TYPES,
    Alternative,
    Entity,
    Field,
    Integration,
    Nfr,
    Notification,
    Relation,
    Role,
    Screen,
    ScreenField,
    StateMachine,
    Status,
    Transition,
    UseCase,
    new_key,
)

PREFIX = {"entities": "entity", "screens": "screen", "roles": "role", "states": "states",
          "notifications": "notification", "integrations": "integration", "nfr": "nfr",
          "use_cases": "uc"}


def _rows(text: str | None) -> list[list[str]]:
    return [[c.strip() for c in line.split("|")] for line in (text or "").splitlines() if line.strip()]


def _col(row, i, default=""):
    return row[i] if len(row) > i and row[i] else default


def _yes(v: str) -> bool:
    return v.lower() in ("t", "tak", "y", "yes", "1", "true")


def _type(v: str) -> str:
    v = v or "text"
    if v not in FIELD_TYPES:
        raise ValueError(f"nieznany typ pola „{v}”. Dozwolone: {', '.join(FIELD_TYPES)}.")
    return v


def item_from_form(section: str, form, existing):
    """Build a manual item from the edit form. Raises ValueError with a Polish message."""
    base = {"key": existing.key if existing else new_key(PREFIX[section]), "source": "manual", "stale": False,
            "node_key": existing.node_key if existing else ""}
    f = lambda name: (form.get(name) or "").strip()  # noqa: E731
    try:
        if section == "entities":
            fields = [Field(key=f"field:{slug(_col(r, 0, 'pole'))}-{i}",
                            name=_col(r, 0, "pole"), type=_type(_col(r, 1)),
                            required=_yes(_col(r, 2)), validation=_col(r, 3),
                            enum_values=[v.strip() for v in _col(r, 4).split(",") if v.strip()],
                            ref_entity=_col(r, 5), is_identifier=_yes(_col(r, 6)))
                    for i, r in enumerate(_rows(f("fields")))]
            relations = [Relation(key=f"rel:{slug(_col(r, 0))}-{i}", to_entity=_col(r, 0), kind=_col(r, 1, "1-n"),
                                  label=_col(r, 2)) for i, r in enumerate(_rows(f("relations")))]
            return Entity(**base, name=f("name"), description=f("description"), fields=fields, relations=relations)
        if section == "screens":
            return Screen(**base, name=f("name"), role=f("role"), actions=[a[0] for a in _rows(f("actions"))],
                          fields=[ScreenField(name=_col(r, 0, "pole"), type=_type(_col(r, 1)), ref=_col(r, 2))
                                  for r in _rows(f("fields"))])
        if section == "roles":
            perms = {_col(r, 0): {"read": _col(r, 1, "none"), "create": _col(r, 2, "none"),
                                  "update": _col(r, 3, "none"), "delete": _col(r, 4, "none")}
                     for r in _rows(f("permissions")) if _col(r, 0)}
            return Role(**base, name=f("name"), description=f("description"), permissions=perms)
        if section == "states":
            statuses = [Status(name=_col(r, 0), initial=_col(r, 1) == "start", final=_col(r, 1) == "koniec")
                        for r in _rows(f("statuses"))]
            transitions = [Transition(from_status=_col(r, 0), to_status=_col(r, 1)) for r in _rows(f("transitions"))]
            return StateMachine(**base, entity=f("entity"), statuses=statuses, transitions=transitions)
        if section == "notifications":
            return Notification(**base, trigger=f("trigger"), channel=f("channel") or "email",
                                recipient_role=f("recipient_role"), summary=f("summary"))
        if section == "integrations":
            return Integration(**base, name=f("name"), direction=f("direction") or "out", on_error=f("on_error"),
                               data=[d.strip() for d in f("data").split(",") if d.strip()])
        if section == "nfr":
            return Nfr(**base, category=f("category") or "other", text=f("text"))
        if section == "use_cases":
            alts = [Alternative(condition=_col(r, 0), steps=[s.strip() for s in _col(r, 1).split(";") if s.strip()])
                    for r in _rows(f("alternatives"))]
            return UseCase(**base, name=f("name"), actor=f("actor"), goal=f("goal"),
                           main=[r[0] for r in _rows(f("main"))], alternatives=alts,
                           includes=[k.strip() for k in f("includes").split(",") if k.strip()])
    except ValidationError as exc:
        raise ValueError(f"Niepoprawne dane ({exc.error_count()} błędów): sprawdź wymagane pola i wartości.") from exc
    raise ValueError("Nieznana sekcja.")


def form_text(section: str, item) -> dict:
    """Prefill the edit form from an item (inverse of item_from_form)."""
    if item is None:
        return {}
    if section == "entities":
        fields = "\n".join(" | ".join([x.name, x.type, "t" if x.required else "n", x.validation,
                                       ",".join(x.enum_values), x.ref_entity, "t" if x.is_identifier else "n"])
                           for x in item.fields)
        rel = "\n".join(f"{r.to_entity} | {r.kind} | {r.label}" for r in item.relations)
        return {"name": item.name, "description": item.description, "fields": fields, "relations": rel}
    if section == "screens":
        return {"name": item.name, "role": item.role, "actions": "\n".join(item.actions),
                "fields": "\n".join(f"{x.name} | {x.type} | {x.ref}" for x in item.fields)}
    if section == "roles":
        return {"name": item.name, "description": item.description,
                "permissions": "\n".join(f"{e} | {p['read']} | {p['create']} | {p['update']} | {p['delete']}"
                                         for e, p in item.permissions.items())}
    if section == "states":
        return {"entity": item.entity,
                "statuses": "\n".join(f"{s.name} | {'start' if s.initial else 'koniec' if s.final else '-'}"
                                      for s in item.statuses),
                "transitions": "\n".join(f"{t.from_status} | {t.to_status}" for t in item.transitions)}
    if section == "integrations":
        return {"name": item.name, "direction": item.direction, "data": ", ".join(item.data),
                "on_error": item.on_error}
    if section == "use_cases":
        return {"name": item.name, "actor": item.actor, "goal": item.goal, "main": "\n".join(item.main),
                "alternatives": "\n".join(f"{a.condition} | {'; '.join(a.steps)}" for a in item.alternatives),
                "includes": ", ".join(item.includes)}
    return item.model_dump()
