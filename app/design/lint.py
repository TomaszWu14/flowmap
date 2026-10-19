"""UML guard: issues in readiness() format plus 'why' — one sentence a learning analyst can act on."""

from ..spec.schema import Spec

WEIGHTS = {"nn_without_join": 5, "island_entity": 3, "reference_without_relation": 3,
           "role_without_use_case": 3, "use_case_without_goal": 3, "use_case_without_alternative": 2}
SECTION_OF = {"nn_without_join": "classes", "island_entity": "classes", "reference_without_relation": "classes",
              "role_without_use_case": "use_cases", "use_case_without_goal": "use_cases",
              "use_case_without_alternative": "use_cases"}


def _i(code, message, key, why):
    return {"code": code, "message": message, "target_key": key, "why": why}


def _linked(spec: Spec) -> dict[str, set[str]]:
    """entity key -> keys of entities it is connected to (both directions, relations only)."""
    out = {e.key: set() for e in spec.entities}
    for e in spec.entities:
        for r in e.relations:
            if r.to_entity in out:
                out[e.key].add(r.to_entity)
                out[r.to_entity].add(e.key)
    return out


def lint(spec: Spec) -> list[dict]:
    issues = []
    linked = _linked(spec)
    names = {e.key: e.name for e in spec.entities}
    for e in spec.entities:
        for r in e.relations:
            if r.kind == "n-n" and r.to_entity in names and not any(
                    {e.key, r.to_entity} <= linked[j] for j in linked if j not in (e.key, r.to_entity)):
                issues.append(_i("nn_without_join", f"Relacja wiele-do-wielu „{e.name}” – „{names[r.to_entity]}” "
                                 "nie ma encji łączącej.", e.key,
                                 "Baza relacyjna zapisze n-n tylko przez tabelę pośrednią; nazwij ją i dodaj jej "
                                 "pola (np. data, ilość) — zwykle to ważne pojęcie biznesowe."))
        if len(spec.entities) > 1 and not linked[e.key] and not any(f.type == "reference" for f in e.fields):
            issues.append(_i("island_entity", f"Encja „{e.name}” nie jest powiązana z żadną inną.", e.key,
                             "Encja bez relacji to zwykle zapomniane powiązanie albo pojęcie spoza systemu — "
                             "dodaj relację lub usuń encję."))
        for f in e.fields:
            if f.type == "reference" and f.ref_entity in names and f.ref_entity not in linked[e.key]:
                issues.append(_i("reference_without_relation", f"Pole „{e.name}.{f.name}” wskazuje "
                                 f"„{names[f.ref_entity]}”, ale brak relacji.", e.key,
                                 "Pole-odwołanie to klucz obcy; relacja z krotnością mówi, ile rekordów może "
                                 "się wiązać — bez niej model jest niepełny."))
    acting = {u.actor for u in spec.use_cases}
    for r in spec.roles:
        if r.key not in acting and r.name.strip().lower() != "administrator":
            issues.append(_i("role_without_use_case", f"Rola „{r.name}” nie ma przypadku użycia.", r.key,
                             "Każdy aktor korzysta z systemu po coś — rola bez przypadku użycia to zwykle "
                             "zbędna rola albo pominięta funkcja."))
    for u in spec.use_cases:
        if not u.goal.strip():
            issues.append(_i("use_case_without_goal", f"Przypadek użycia „{u.name}” nie ma celu.", u.key,
                             "Cel mówi, kiedy scenariusz się udał (wartość dla aktora) — bez niego nie da się "
                             "napisać testu akceptacyjnego."))
        if u.actor and not u.alternatives:
            issues.append(_i("use_case_without_alternative", f"Przypadek użycia „{u.name}” nie ma scenariusza "
                             "alternatywnego.", u.key,
                             "W prawdziwych procesach coś idzie inaczej (brak danych, odmowa, błąd systemu) — "
                             "opisz co najmniej jeden wyjątek."))
    return issues
