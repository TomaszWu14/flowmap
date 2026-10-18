"""Deterministic question rules: the no-AI brain of FlowMap.

Pure functions over a graph dict + project settings, so they are easy to unit-test.
"""

import re

from . import templates
from .schemas import Option, Question, StepSpec

ERROR_HINT = re.compile(r"płat|pay|przelew|bramk|karta|blik", re.I)
NEGATIVE_LABEL = re.compile(r"^(nie|no|błąd|brak|odrzu|niepowodz|anul|error|fail)", re.I)
QUICK_CHUNK = 4


def _s(type, title, actor="", **kw) -> StepSpec:
    return StepSpec(type=type, title=title, actor=actor, **kw)


def _end(title="Koniec procesu", actor="") -> StepSpec:
    return _s("end", title, actor)


def generic_next(node: dict, label: str | None, mode: str) -> list[Option]:
    """Fallback tiles by step type when no template step applies."""
    actor = node.get("actor") or "Użytkownik"
    t = node["type"]
    if t == "decision":
        if label and NEGATIVE_LABEL.match(label):
            specs = [
                _s("screen", "Komunikat o błędzie i poprawa danych", actor),
                _s("automation", "Powiadomienie obsługi o problemie", "System"),
                _end("Proces przerwany", actor),
            ]
        else:
            specs = [
                _s("screen", "Ekran potwierdzenia", actor),
                _s("automation", "Zapis danych w systemie", "System"),
                _s("user_action", "Użytkownik kontynuuje", actor),
            ]
    elif t == "start":
        specs = [
            _s("screen", "Ekran startowy z formularzem", actor, outputs=["Formularz"]),
            _s("user_action", "Wypełnienie formularza", actor),
            _s("decision", "Czy użytkownik ma konto?", "System", branches=["tak", "nie"]),
            _s("automation", "Rejestracja zgłoszenia w systemie", "System"),
        ]
    elif t == "screen":
        specs = [
            _s("user_action", "Wypełnienie i zatwierdzenie formularza", actor),
            _s("decision", "Czy dane są poprawne?", "System", branches=["tak", "nie"]),
            _s("user_action", "Wybór opcji na ekranie", actor),
        ]
    elif t == "user_action":
        specs = [
            _s("automation", "Zapis danych w systemie", "System"),
            _s("decision", "Czy dane są kompletne?", "System", branches=["tak", "nie"]),
            _s("screen", "Ekran potwierdzenia", actor),
            _s("integration", "Przekazanie danych do systemu zewnętrznego", "System"),
        ]
    elif t == "automation":
        specs = [
            _s("automation", "Wysłanie powiadomienia e-mail", "System", outputs=["E-mail"]),
            _s("screen", "Ekran z wynikiem", actor if actor != "System" else "Użytkownik"),
            _s("wait", "Oczekiwanie na odpowiedź", "System"),
            _s("decision", "Czy operacja się powiodła?", "System", branches=["tak", "nie"]),
        ]
    elif t == "integration":
        specs = [
            _s("decision", "Czy odpowiedź systemu jest poprawna?", "System", branches=["tak", "nie"]),
            _s("automation", "Zapis wyniku integracji", "System"),
            _s("screen", "Ekran z wynikiem", "Użytkownik"),
        ]
    else:  # wait
        specs = [
            _s("automation", "Automatyczne przypomnienie", "System"),
            _s("user_action", "Użytkownik wraca do procesu", "Użytkownik"),
            _s("decision", "Czy minął termin?", "System", branches=["tak", "nie"]),
        ]
    options = [Option(label=s.title, steps=[s]) for s in specs]
    if mode == "quick":
        options = options[:3]
        options.append(Option(
            label="Domknij proces: potwierdzenie i powiadomienie",
            steps=[_s("screen", "Ekran potwierdzenia", actor if actor != "System" else "Użytkownik"),
                   _s("automation", "Powiadomienie e-mail", "System"), _end()],
        ))
    return options


def _template_chunk(template: str, start_step: str, mode: str, graph_tpl: dict[str, str]):
    """Follow the template from start_step. Returns (specs, connect_to_key)."""
    specs: list[StepSpec] = []
    cur = start_step
    limit = QUICK_CHUNK if mode == "quick" else 1
    while cur and len(specs) < limit:
        if cur in graph_tpl:  # step already on the map -> close the loop instead of duplicating
            return specs, graph_tpl[cur]
        s = templates.step(template, cur)
        specs.append(StepSpec(tpl=cur, **{k: v for k, v in s.items() if k in StepSpec.model_fields}))
        if s["type"] in ("decision", "end", "integration"):
            break
        nxt = [dst for dst, lab in templates.successors(template, cur, None) if not lab]
        cur = nxt[0] if nxt else None
    if cur and len(specs) == limit and specs[-1].type not in ("decision", "end") and cur in graph_tpl:
        return specs, graph_tpl[cur]
    return specs, ""


def next_question(graph: dict, node: dict, label: str | None, mode: str, template: str | None) -> Question:
    graph_tpl = {n["data"]["tpl"]: n["key"] for n in graph["nodes"] if (n.get("data") or {}).get("tpl")}
    by_key = {n["key"]: n for n in graph["nodes"]}
    options: list[Option] = []
    tpl_step = (node.get("data") or {}).get("tpl")
    for target, edge_label in templates.successors(template, tpl_step, label):
        if target in graph_tpl:
            existing = by_key[graph_tpl[target]]
            options.append(Option(label=f"Wróć do: {existing['title']}", kind="connect",
                                  connect_to=existing["key"],
                                  edge_label=edge_label if node["type"] != "decision" else ""))
            continue
        specs, connect_to = _template_chunk(template, target, mode, graph_tpl)
        if not specs:
            continue
        is_error = node["type"] != "decision" and bool(edge_label)
        title = specs[0].title + (f" (+{len(specs) - 1})" if len(specs) > 1 else "")
        options.append(Option(label=title, steps=specs, connect_to=connect_to,
                              edge_label=edge_label if is_error else "",
                              edge_condition="error" if is_error else ""))
    seen = {o.label for o in options}
    generic = generic_next(node, label, mode)
    if options and mode == "quick":
        generic = generic[:-1]  # template already gives a multi-step chunk; skip the generic closer
    for opt in generic:
        if len(options) >= 4:
            break
        if opt.label not in seen:
            options.append(opt)
    options.append(Option(label="Koniec procesu", steps=[_end(actor=node.get("actor", ""))]))

    where = f"„{node['title']}”" + (f" → {label}" if label else "")
    return Question(kind="next", node_key=node["key"], slot=label or "",
                    text=f"Co dzieje się dalej po {where}?",
                    hint="Wybierz kafelek albo opisz własny krok w polu „inne”.", options=options[:5])


ACTOR_CHOICES = ["Klient", "Pracownik", "Administrator", "System"]


def actor_question(graph: dict, node: dict) -> Question:
    known = [n["actor"] for n in graph["nodes"] if n.get("actor")]
    choices = list(dict.fromkeys(known + ACTOR_CHOICES))[:5]
    return Question(kind="actor", node_key=node["key"], text=f"Kto wykonuje krok „{node['title']}”?",
                    options=[Option(label=a, kind="actor", values=[a]) for a in choices])


SCREEN_SETS = [
    ("Formularz z danymi kontaktowymi", ["Imię i nazwisko", "E-mail", "Telefon", "Przycisk Dalej"]),
    ("Lista do wyboru", ["Lista pozycji", "Wyszukiwarka", "Filtry", "Przycisk Wybierz"]),
    ("Podsumowanie", ["Zestawienie danych", "Suma", "Przycisk Potwierdź", "Przycisk Wstecz"]),
    ("Komunikat", ["Treść komunikatu", "Przycisk OK"]),
]
DATA_SETS = [
    ("Dane osobowe", ["Imię i nazwisko", "E-mail", "Telefon"]),
    ("Dane zamówienia", ["Pozycje", "Ilość", "Kwota"]),
    ("Termin", ["Data", "Godzina"]),
    ("Plik / załącznik", ["Plik", "Opis"]),
]


def fields_question(node: dict, kind: str, template: str | None) -> Question:
    tpl_step = (node.get("data") or {}).get("tpl")
    sets = SCREEN_SETS if kind == "screen" else DATA_SETS
    options = []
    if template and tpl_step:
        s = templates.step(template, tpl_step)
        fields = s.get("outputs" if kind == "screen" else "inputs") or []
        if fields:
            options.append(Option(label="Z szablonu: " + ", ".join(fields), kind="fields", values=fields))
    options += [Option(label=f"{name}: {', '.join(f)}", kind="fields", values=f) for name, f in sets]
    text = (f"Co użytkownik widzi na ekranie „{node['title']}”?" if kind == "screen"
            else f"Jakie dane są potrzebne w kroku „{node['title']}”?")
    return Question(kind=kind, node_key=node["key"], text=text, hint="Pola wpisz po przecinku w polu „inne”.",
                    options=options[:4] + [Option(label="Pomiń", kind="skip")])


def error_question(node: dict, template: str | None) -> Question:
    actor = node.get("actor") or "Użytkownik"
    label = "brak płatności" if ERROR_HINT.search(node["title"]) else "błąd"
    options = []
    tpl_step = (node.get("data") or {}).get("tpl")
    for target, lab in templates.successors(template, tpl_step, None):
        if lab:
            s = templates.step(template, target)
            spec = StepSpec(tpl=target, **{k: v for k, v in s.items() if k in StepSpec.model_fields})
            options.append(Option(label=f"{s['title']} i ponowienie", steps=[spec], connect_to="source",
                                  edge_label=lab, edge_condition="error"))
    options += [
        Option(label="Komunikat o błędzie i ponowienie", connect_to="source", edge_label=label,
               edge_condition="error", steps=[_s("screen", f"Błąd: {node['title'][:120]} — spróbuj ponownie", actor)]),
        Option(label="Anulowanie i powiadomienie", edge_label=label, edge_condition="error",
               steps=[_s("automation", "Anulowanie i powiadomienie o błędzie", "System"),
                      _end("Proces przerwany", actor)]),
        Option(label="Przekazanie do obsługi ręcznej", edge_label=label, edge_condition="error",
               steps=[_s("user_action", "Ręczna obsługa problemu", "Pracownik")]),
        Option(label="Pomiń — bez obsługi błędu", kind="skip"),
    ]
    return Question(kind="error", node_key=node["key"],
                    text=f"Co jeśli „{node['title']}” się nie powiedzie?",
                    hint="Ścieżka błędu dostaje etykietę na strzałce.", options=options[:5])


def branches_question(node: dict) -> Question:
    sets = [["tak", "nie"], ["sukces", "błąd"], ["zaakceptowano", "odrzucono", "do poprawy"]]
    return Question(kind="branches", node_key=node["key"], text=f"Jakie są wyjścia z decyzji „{node['title']}”?",
                    hint="Własne etykiety wpisz po przecinku.",
                    options=[Option(label=" / ".join(s), kind="branches", values=s) for s in sets])


def needs_error_path(node: dict) -> bool:
    """Integrations and payment-like actions need a failure branch (screens showing errors do not)."""
    if node["type"] == "integration":
        return True
    return node["type"] in ("user_action", "automation") and bool(ERROR_HINT.search(node["title"]))


def helper_kinds(node: dict, mode: str) -> list[str]:
    """Context questions still to ask about a node (thorough mode asks them all)."""
    asked = set((node.get("data") or {}).get("asked", []))
    kinds = []
    if node["type"] in ("start", "end"):
        return kinds
    if not node.get("actor"):
        kinds.append("actor")
    if mode == "thorough":
        if node["type"] == "screen":
            kinds.append("screen")
        if node["type"] in ("user_action", "integration"):
            kinds.append("data")
        if needs_error_path(node):
            kinds.append("error")
    return [k for k in kinds if k not in asked]


def helper_question(graph: dict, node: dict, kind: str, template: str | None) -> Question:
    if kind == "actor":
        return actor_question(graph, node)
    if kind in ("screen", "data"):
        return fields_question(node, kind, template)
    return error_question(node, template)
