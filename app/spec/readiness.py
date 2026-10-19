"""How ready the spec is for Claude Code: 0-100 plus issues pinned to items."""

from .schema import SECTIONS, Spec

WEIGHTS = {"no_identifier": 10, "enum_without_values": 3, "bad_relation": 8, "screen_without_role": 5,
           "role_without_permissions": 5, "states_without_initial_or_final": 8,
           "notification_without_recipient": 3, "integration_without_error": 5, "stale_item": 2,
           "open_proposal": 1}


def _i(code, message, key=""):
    return {"code": code, "message": message, "target_key": key}


def readiness(spec: Spec) -> dict:
    issues = []
    entity_keys = {e.key for e in spec.entities}
    for e in spec.entities:
        if not any(f.is_identifier for f in e.fields):
            issues.append(_i("no_identifier", f'Encja „{e.name}” nie ma pola identyfikującego.', e.key))
        for f in e.fields:
            if f.type == "enum" and not f.enum_values:
                issues.append(_i("enum_without_values", f'Pole „{e.name}.{f.name}” nie ma wartości wyboru.', e.key))
            if f.type == "reference" and f.ref_entity not in entity_keys:
                issues.append(_i("bad_relation", f'Pole „{e.name}.{f.name}” wskazuje nieistniejącą encję.', e.key))
        for r in e.relations:
            if r.to_entity not in entity_keys:
                issues.append(_i("bad_relation", f'Relacja z „{e.name}” wskazuje nieistniejącą encję.', e.key))
    for s in spec.screens:
        if not s.role:
            issues.append(_i("screen_without_role", f'Ekran „{s.name}” nie ma roli.', s.key))
    for r in spec.roles:
        if not r.permissions:
            issues.append(_i("role_without_permissions", f'Rola „{r.name}” nie ma uprawnień.', r.key))
    for sm in spec.states:
        if not any(s.initial for s in sm.statuses) or not any(s.final for s in sm.statuses):
            issues.append(_i("states_without_initial_or_final",
                           "Statusy bez stanu początkowego lub końcowego.", sm.key))
    for n in spec.notifications:
        if not n.recipient_role:
            issues.append(_i("notification_without_recipient", f'Powiadomienie „{n.trigger}” nie ma odbiorcy.', n.key))
    for i in spec.integrations:
        if not i.on_error:
            issues.append(_i("integration_without_error", f'Integracja „{i.name}” nie ma obsługi błędu.', i.key))
    for section in SECTIONS:
        for item in getattr(spec, section):
            if item.stale:
                issues.append(_i("stale_item", "Element nie ma już odpowiednika na mapie.", item.key))
    issues += [_i("open_proposal", f"Propozycja AI czeka: {p.summary}", p.target_key) for p in spec.proposals]
    return {"score": max(0, 100 - sum(WEIGHTS[i["code"]] for i in issues)), "issues": issues}
