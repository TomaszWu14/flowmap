"""First draft of a process map from free text (notes, a process description).

Without AI: one step per line/sentence, step type guessed from keywords. Questions then fill the gaps
(a decision's "nie" branch stays open, so the panel asks about it).
"""

import re

ROLES = ("Klient", "Pracownik", "Kierownik", "Administrator", "Admin", "Recepcja", "Recepcjonistka", "Kurier",
         "Magazynier", "Serwisant", "Księgowość", "Lekarz", "Pacjent", "Użytkownik", "Sprzedawca", "Kupujący",
         "Dział", "Manager", "Menedżer", "Konsultant", "Dyspozytor", "Kierowca")
MAX_STEPS = 40

RULES = [  # (type, pattern) checked in order; first match wins
    ("decision", re.compile(r"\?\s*$|^czy\b|\bjeśli\b|\bjeżeli\b|\bgdy\b.*\bto\b", re.I)),
    ("end", re.compile(r"\b(koniec|kończy się|zakończ\w*|zamknięci\w* sprawy|proces się kończy)\b", re.I)),
    ("integration", re.compile(r"płat|bramk|\bapi\b|integrac|\bsms\b|kurier\w* zleca|system zewn|\bksef\b|bank", re.I)),
    ("wait", re.compile(r"\bczeka\w*|oczekuj\w*|\bpo \d+ (dni|godz)|\bdni(a|ach)?\b.*\bpóźniej\b", re.I)),
    ("automation", re.compile(r"\bsystem\b|automatycz|wysyła\w* (e-?mail|powiadom)|generuje|nalicza", re.I)),
    ("screen", re.compile(r"\bekran\w*|\bwidzi\b|formularz|strona|\blist[aęy]\b|panel|wyświetla", re.I)),
]


def _lines(text: str) -> list[str]:
    parts = []
    for raw in text.replace("\r", "").split("\n"):
        line = re.sub(r"^\s*(?:[-*•–]|\d+[.)])\s*", "", raw).strip()
        if not line:
            continue
        # long prose lines: split into sentences
        parts += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])", line) if s.strip()]
    return [p.rstrip(".") for p in parts][:MAX_STEPS]


def guess_type(sentence: str) -> str:
    return next((t for t, rx in RULES if rx.search(sentence)), "user_action")


def guess_actor(sentence: str, step_type: str, default: str) -> str:
    first = sentence.split()[0].strip(",:") if sentence.split() else ""
    for role in ROLES:
        if first.lower().startswith(role.lower()[:6]):
            return role
    return "System" if step_type in ("automation", "integration", "wait", "decision") else default


def _title(sentence: str) -> str:
    title = sentence.strip()
    return (title[:1].upper() + title[1:])[:200]


def draft_from_text(text: str, start_sentence: str | None = None) -> dict:
    """Graph dict: start -> one step per line. Decisions keep 'tak' on the main path, 'nie' left open."""
    lines = _lines(text)
    if start_sentence is None:
        start_sentence = lines.pop(0) if lines else "Start procesu"
    main_actor = guess_actor(start_sentence, "user_action", "Użytkownik")
    nodes = [{"key": "s0", "type": "start", "title": _title(start_sentence), "actor": main_actor, "description": "",
              "inputs": [], "outputs": [], "data": {}}]
    edges = []
    prev, prev_label = "s0", ""
    for i, line in enumerate(lines, 1):
        step_type = guess_type(line)
        if step_type == "end" and i < len(lines):
            step_type = "user_action"  # only the last line may close the process
        node = {"key": f"s{i}", "type": step_type, "title": _title(line),
                "actor": guess_actor(line, step_type, main_actor), "description": "", "inputs": [], "outputs": [],
                "data": {"branches": ["tak", "nie"]} if step_type == "decision" else {}}
        nodes.append(node)
        edges.append({"source": prev, "target": node["key"], "label": prev_label, "condition": ""})
        prev, prev_label = node["key"], ("tak" if step_type == "decision" else "")
    return {"nodes": nodes, "edges": edges}
