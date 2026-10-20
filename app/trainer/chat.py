"""Trainer chat: a private conversation per user and project, aware of the map, guards and last score."""

from flask import current_app

from ..ai import client as ai  # module reference: tests replace ai._client
from ..design.lint import lint
from ..design.trace import trace_issues
from ..extensions import db
from ..flow import graph as g
from ..flow.guard import report
from ..models import Evaluation, TrainerMessage

HISTORY = 12
MODES = {
    True: ("Nauka", "Prowadź metodą sokratejską: zadawaj pytania naprowadzające, wskazuj, gdzie szukać problemu, ale "
                    "nie podawaj gotowych rozwiązań (kroków, nazw, struktur). Gotowe rozwiązanie podaj dopiero, gdy "
                    "użytkownik wprost o nie poprosi po wcześniejszych podpowiedziach."),
    False: ("Praca", "Dawaj konkretne propozycje: co dodać lub zmienić i gdzie (np. „dodaj krok X po Y w torze Z”), "
                     "z krótkim uzasadnieniem."),
}


def _issues(items: list[dict], limit: int = 8) -> str:
    return "; ".join(i["message"] for i in items[:limit]) or "brak"


def system_prompt(project, user) -> str:
    graph = project.graph()
    spec = g.project_spec(project)
    design = (lint(spec) + trace_issues(graph, spec)) if spec else []
    last = (Evaluation.query.filter_by(project_id=project.id, user_id=user.id)
            .order_by(Evaluation.id.desc()).limit(2).all())
    score = ", ".join(f"{e.details.get('label', e.kind)} {e.score}/100" for e in last) or "jeszcze nie oceniano"
    mode, rules = MODES[bool(project.learning)]
    return ai._prompt("trainer", mode=mode, mode_rules=rules, start_sentence=project.start_sentence,
                   graph_json=ai.compact_graph(graph), guard_issues=_issues(report(graph)["issues"]),
                   design_issues=_issues(design), last_score=score)


def history(project, user, limit: int = 50) -> list[TrainerMessage]:
    rows = (TrainerMessage.query.filter_by(project_id=project.id, user_id=user.id)
            .order_by(TrainerMessage.id.desc()).limit(limit).all())
    return rows[::-1]


def reply(project, user, text: str) -> str:
    """Ask the trainer; on success store the question and the answer. Raises AIError, storing nothing."""
    messages = [{"role": m.role, "content": m.text} for m in history(project, user, HISTORY)]
    messages.append({"role": "user", "content": text})
    response = ai._api_call(ai._client(), "trainer_chat", model=current_app.config["ANTHROPIC_CHAT_MODEL"],
                            max_tokens=1500, system=system_prompt(project, user), messages=messages)
    answer = "".join(b.text for b in response.content if b.type == "text").strip() or "(brak odpowiedzi)"
    db.session.add_all([TrainerMessage(project_id=project.id, user_id=user.id, role="user", text=text),
                        TrainerMessage(project_id=project.id, user_id=user.id, role="assistant", text=answer)])
    db.session.commit()
    return answer
