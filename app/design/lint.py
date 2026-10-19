"""UML guard: issues in readiness() format plus 'why' — one sentence a learning analyst can act on."""

import re

from ..spec.schema import Spec

WEIGHTS = {"nn_without_join": 5, "island_entity": 3, "reference_without_relation": 3,
           "role_without_use_case": 3, "use_case_without_goal": 3, "use_case_without_alternative": 2,
           "integration_without_error_message": 4, "idle_participant": 2,
           "unreachable_status": 4, "dead_end_status": 3, "rule_gap": 4, "rule_overlap": 4,
           "vision_without_metrics": 3, "vision_without_wont": 1}
SECTION_OF = {"nn_without_join": "classes", "island_entity": "classes", "reference_without_relation": "classes",
              "role_without_use_case": "use_cases", "use_case_without_goal": "use_cases",
              "use_case_without_alternative": "use_cases", "integration_without_error_message": "sequences",
              "idle_participant": "sequences", "unreachable_status": "states", "dead_end_status": "states",
              "rule_gap": "rules", "rule_overlap": "rules", "vision_without_metrics": "vision",
              "vision_without_wont": "vision"}
ELSE = re.compile(r"^(inaczej|w przeciwnym (razie|wypadku)|pozostałe|else|default)\b", re.I)


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
    integrations = {i.name for i in spec.integrations}
    for s in spec.sequences:
        used = {p for m in s.messages for p in (m.source, m.target)}
        for p in s.participants:
            if p not in used:
                issues.append(_i("idle_participant", f"Uczestnik „{p}” w sekwencji „{s.name}” nie ma komunikatów.",
                                 s.key, "Uczestnik bez komunikatów nic nie wnosi do scenariusza — usuń go albo "
                                 "dopisz, z kim się komunikuje."))
            called = any(m.target == p and m.kind == "call" for m in s.messages)
            failed = any(m.source == p and m.kind == "error" for m in s.messages)
            if p in integrations and called and not failed:
                issues.append(_i("integration_without_error_message", f"Wywołanie „{p}” w sekwencji „{s.name}” "
                                 "nie ma ścieżki błędu.", s.key,
                                 "System zewnętrzny może nie odpowiedzieć albo odmówić — pokaż w sekwencji, "
                                 "co wtedy dzieje się z procesem (blok alt)."))
    for sm in spec.states:
        nxt: dict[str, set[str]] = {}
        for t in sm.transitions:
            nxt.setdefault(t.from_status, set()).add(t.to_status)
        reach = {s.name for s in sm.statuses if s.initial}
        todo = list(reach)
        while todo:
            for b in nxt.get(todo.pop(), ()):
                if b not in reach:
                    reach.add(b)
                    todo.append(b)
        for s in sm.statuses:
            if reach and s.name not in reach:
                issues.append(_i("unreachable_status", f"Status „{s.name}” jest nieosiągalny ze stanu początkowego.",
                                 sm.key, "Do statusu nie prowadzi żadne przejście — rekord nigdy go nie osiągnie. "
                                 "Dodaj przejście albo usuń status."))
            elif not s.final and not nxt.get(s.name):
                issues.append(_i("dead_end_status", f"Status „{s.name}” nie ma wyjścia, a nie jest końcowy.", sm.key,
                                 "Rekord utknie w tym statusie na zawsze. Oznacz go jako końcowy albo dodaj "
                                 "przejście dalej."))
    for r in spec.rules:
        conds = [w.condition.strip().lower() for w in r.rows]
        if not (any(ELSE.match(c) for c in conds) or {"tak", "nie"} <= set(conds)):
            issues.append(_i("rule_gap", f"Tabela „{r.name}” nie obejmuje wszystkich przypadków.", r.key,
                             "Gdy żaden warunek nie pasuje, system nie wie, co zrobić. Dodaj wiersz „inaczej” "
                             "albo uzupełnij warunki tak, by pokrywały wszystkie przypadki."))
        if len(set(conds)) < len(conds):
            issues.append(_i("rule_overlap", f"Tabela „{r.name}” ma powtórzony warunek.", r.key,
                             "Dwa wiersze z tym samym warunkiem mogą dać różne wyniki — reguła staje się "
                             "niejednoznaczna. Scal je albo doprecyzuj warunki."))
    v = spec.vision
    if v.problem.strip():
        if not v.metrics:
            issues.append(_i("vision_without_metrics", "Wizja nie ma mierników sukcesu.", "vision",
                             "Bez mierzalnego celu (np. „rezerwacja w mniej niż 2 minuty”) nie da się ocenić, czy "
                             "aplikacja się udała — to pierwsze pytanie sponsora projektu."))
        if not v.wont:
            issues.append(_i("vision_without_wont", "Zakres nie mówi, czego nie robimy (Won't).", "vision",
                             "Jawne „tego nie robimy w MVP” chroni projekt przed rozrostem zakresu i sporami "
                             "przy odbiorze."))
    return issues
