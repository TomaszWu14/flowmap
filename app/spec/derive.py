"""Rules: process map (graph dict) -> technical specification. Pure, deterministic, no AI."""

import re
import unicodedata

from ..ai.rules import NEGATIVE_LABEL
from .schema import (
    Entity,
    Field,
    Integration,
    Nfr,
    Notification,
    Relation,
    Role,
    Screen,
    ScreenField,
    Spec,
    StateMachine,
    Status,
    Transition,
    Vision,
)

TYPE_RULES = [  # (regex on lower-cased field name, type) - first match wins
    (r"e-?mail", "email"), (r"telefon|tel\.|komórk", "phone"), (r"godzin|termin.*godz", "datetime"),
    (r"\bdata\b|\bdzień\b", "date"), (r"kwot|cen[ay]|koszt|sum[ay]|opłat", "money"),
    (r"ilość|liczba|sztuk", "integer"), (r"zgod|akceptac|regulamin", "boolean"),
    (r"plik|zdjęci|załącz|skan", "file"), (r"opis|uwag|komentarz|treść", "long_text"),
]
MAIN_NOUNS = [  # start-sentence keyword -> main entity name
    (r"wizyt|rezerw|termin", "Rezerwacja"), (r"zamów|kup|koszyk|sklep", "Zamówienie"),
    (r"zgłosz|usterk|awari|napraw|reklamac", "Zgłoszenie"), (r"wniosek|urlop|delegac", "Wniosek"),
]
NOTIFY = re.compile(r"wysłani|powiadom|sms|e-?mail|przypomn", re.I)
PERSONAL = re.compile(r"imię|nazwisk|e-?mail|telefon|adres|pesel", re.I)


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def guess_field_type(name: str) -> str:
    low = name.lower()
    return next((t for rx, t in TYPE_RULES if re.search(rx, low)), "text")


def _main_name(meta: dict) -> str:
    text = f"{meta.get('start_sentence', '')} {meta.get('name', '')}".lower()
    return next((name for rx, name in MAIN_NOUNS if re.search(rx, text)), (meta.get("name") or "Proces")[:100])


def _field(name: str, **kw) -> Field:
    return Field(key=f"field:{slug(name)}", name=name[:100], type=kw.pop("type", guess_field_type(name)), **kw)


def derive(graph: dict, meta: dict) -> Spec:
    nodes = graph["nodes"]
    by_key = {n["key"]: n for n in nodes}
    start = next((n for n in nodes if n["type"] == "start"), None)
    initiator = (start or {}).get("actor") or ""
    humans = []
    seen_actor_slugs = set()
    for n in nodes:
        actor = n.get("actor")
        if not actor or actor == "System" or slug(actor) in seen_actor_slugs:
            continue
        seen_actor_slugs.add(slug(actor))
        humans.append(actor)

    # --- entities
    main_name = _main_name(meta)
    main = Entity(key=f"entity:{slug(main_name)}", name=main_name, fields=[
        _field("id", type="integer", is_identifier=True, required=True),
        _field("utworzono", type="datetime", required=True),
    ])
    entities = [main]
    for actor in humans:
        inputs = list(dict.fromkeys(
            f for n in nodes if n.get("actor") and slug(n["actor"]) == slug(actor)
            for f in n.get("inputs", [])))
        if not inputs or slug(actor) == slug(main_name):
            continue
        fields = [_field("id", type="integer", is_identifier=True, required=True)]
        fields += [_field(f, required=True) for f in inputs if slug(f) != "id"]
        entities.append(Entity(key=f"entity:{slug(actor)}", name=actor, fields=fields, relations=[
            Relation(key=f"rel:{slug(actor)}-{slug(main_name)}", to_entity=main.key, kind="1-n")]))

    # --- states of the main entity (walk order, decisions give approve/reject)
    from ..design.derive import rejoins_main  # local: design.derive imports this module

    statuses = [Status(name="nowy", initial=True)]
    transitions = []
    current = "nowy"
    for n in _ordered(graph):
        if n["type"] == "decision":
            before = current
            for e in graph["edges"]:
                if e["source"] == n["key"] and e.get("label"):
                    negative = bool(NEGATIVE_LABEL.match(e["label"]))
                    if negative and rejoins_main(graph, e["target"]):
                        continue  # a retry or a skipped step, not a rejection of the record
                    name = "odrzucony" if negative else "zatwierdzony"
                    _add_status(statuses, name, final=negative)
                    if before != name:
                        transitions.append(Transition(from_status=before, to_status=name, node_key=n["key"],
                                                      condition=f"{n['title']} — {e['label']}"[:300]))
                    if not negative:
                        current = name
        elif n["type"] == "end":
            name = n["title"][:60].lower()
            _add_status(statuses, name, final=True)
            transitions.append(Transition(from_status=current, to_status=name, node_key=n["key"],
                                          role=slug(n.get("actor") or "")))
    if not any(s.final for s in statuses):
        _add_status(statuses, "zamknięty", final=True)
    main.fields.append(_field("status", type="enum", enum_values=[s.name for s in statuses], required=True))
    states = [StateMachine(key=f"states:{slug(main_name)}", entity=main.key, statuses=statuses,
                           transitions=transitions)]

    # --- roles
    roles = []
    for actor in humans:
        if slug(actor) == "administrator":
            perms = {e.key: {"read": "all", "create": "all", "update": "all", "delete": "all"} for e in entities}
        elif actor == initiator:
            perms = {main.key: {"read": "own", "create": "own", "update": "own", "delete": "none"}}
            if any(e.key == f"entity:{slug(actor)}" for e in entities):
                perms[f"entity:{slug(actor)}"] = {"read": "own", "create": "own", "update": "own", "delete": "none"}
        else:
            perms = {main.key: {"read": "all", "create": "none", "update": "all", "delete": "none"}}
        roles.append(Role(key=f"role:{slug(actor)}", name=actor, permissions=perms))
    if not any(slug(r.name) == "administrator" for r in roles):
        roles.append(Role(key="role:administrator", name="Administrator", description="Pełny dostęp",
                          permissions={e.key: {"read": "all", "create": "all", "update": "all", "delete": "all"}
                                       for e in entities}))

    # --- screens, integrations, notifications
    screens = [Screen(key=f"screen:{n['key']}", node_key=n["key"], name=n["title"],
                      role=f"role:{slug(n['actor'])}" if n.get("actor") and n["actor"] != "System" else "",
                      fields=[ScreenField(name=f[:100], type=guess_field_type(f))
                              for f in list(n.get("inputs", [])) + list(n.get("outputs", []))])
               for n in nodes if n["type"] == "screen"]
    integrations = []
    for n in nodes:
        if n["type"] != "integration":
            continue
        errors = [by_key[e["target"]]["title"] for e in graph["edges"]
                  if e["source"] == n["key"] and e.get("condition") == "error" and e["target"] in by_key]
        integrations.append(Integration(key=f"integration:{n['key']}", node_key=n["key"], name=n["title"],
                                        data=list(n.get("inputs", [])) + list(n.get("outputs", [])),
                                        on_error="; ".join(errors)))
    notifications = []
    last_human = initiator
    for n in _ordered(graph):
        if n.get("actor") and n["actor"] != "System":
            last_human = n["actor"]
        if n["type"] == "automation" and NOTIFY.search(n["title"]):
            notifications.append(Notification(
                key=f"notification:{n['key']}", node_key=n["key"], trigger=n["title"],
                channel="sms" if re.search(r"sms", n["title"], re.I) else "email",
                recipient_role=f"role:{slug(last_human)}" if last_human else "", summary=n["title"]))

    # --- nfr
    nfr = [Nfr(key="nfr:https", category="security", text="Cała aplikacja działa wyłącznie po HTTPS."),
           Nfr(key="nfr:backup", category="other", text="Codzienna kopia zapasowa bazy danych.")]
    all_fields = [f.name for e in entities for f in e.fields]
    if any(PERSONAL.search(f) for f in all_fields):
        nfr.append(Nfr(key="nfr:rodo", category="privacy",
                       text="RODO: podstawa przetwarzania danych osobowych i usunięcie danych na żądanie."))
    from ..design.derive import rules as derive_rules  # local: design.derive imports this module
    from ..design.derive import sequences as derive_sequences
    from ..design.derive import use_cases as derive_use_cases

    ends = [n["title"] for n in nodes if n["type"] == "end"]
    vision = Vision(problem=f"Proces „{meta.get('start_sentence', '')}” — opisz, kogo dziś boli i co nie działa.",
                    goals=[f"Doprowadzić do: {t}" for t in ends], must=[s.name for s in screens],
                    should=[i.name for i in integrations], could=[n.trigger for n in notifications])
    return Spec(entities=entities, screens=screens, roles=roles, states=states, notifications=notifications,
                integrations=integrations, nfr=nfr, use_cases=derive_use_cases(graph, meta),
                sequences=derive_sequences(graph, meta), rules=derive_rules(graph),
                vision=vision)


def _add_status(statuses: list[Status], name: str, final: bool = False) -> None:
    if not any(s.name == name for s in statuses):
        statuses.append(Status(name=name, final=final))


def _ordered(graph: dict) -> list[dict]:
    from ..export.builders import _ordered as ordered

    return ordered(graph)
