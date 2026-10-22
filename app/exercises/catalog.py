"""Fixed exercise catalogue: one JSON file per task in data/, validated when the app starts."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DATA_DIR = Path(__file__).parent / "data"
STAGES = 2
LEVELS = {"podstawowy": "Podstawowy", "zaawansowany": "Zaawansowany"}
TOPICS = {  # shared across exercises so verdicts add up on the progress page
    "przebieg": "Przebieg i kroki", "role": "Role w procesie", "decyzje": "Decyzje i rozgałęzienia",
    "wyjatki": "Wyjątki i błędy", "terminy": "Terminy i eskalacje", "komunikacja": "Powiadomienia i komunikacja",
    "przypadki": "Przypadki użycia", "dane": "Model danych", "statusy": "Statusy i przejścia",
    "reguly": "Reguły biznesowe", "uprawnienia": "Role i uprawnienia w aplikacji", "integracje": "Integracje",
    "wizja": "Wizja i korzyść",
}
Topic = Literal[tuple(TOPICS)]


class Expectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=500)
    topic: Topic


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    title: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=60)
    level: Literal["podstawowy", "zaawansowany"]
    brief: str = Field(min_length=1, max_length=3000)
    start_sentence: str = Field(min_length=1, max_length=500)
    stage1: list[Expectation] = Field(min_length=1)  # expert expectations for the map
    stage2: list[Expectation] = Field(min_length=1)  # expert expectations for the app design
    # Expert map shown after the first graded attempt, one step per line: "key|type|title|actor|target:label;..."
    solution: list[str] = []

    def expectations(self, stage: int) -> list[Expectation]:
        return self.stage1 if stage == 1 else self.stage2

    @field_validator("solution")
    @classmethod
    def _valid_solution(cls, lines: list[str]) -> list[str]:
        if lines:
            solution_graph(lines)
        return lines

    def solution_graph(self) -> dict | None:
        return solution_graph(self.solution) if self.solution else None


def solution_graph(lines: list[str]) -> dict:
    """Graph dict (same shape as Project.graph()) from the compact solution lines. Raises ValueError."""
    from ..models import NODE_TYPES

    nodes, edges = [], []
    for line in lines:
        parts = line.split("|")
        if len(parts) != 5 or parts[1] not in NODE_TYPES or not parts[2].strip():
            raise ValueError(f"zły krok rozwiązania: {line!r}")
        key, type_, title, actor, nxt = parts
        targets = [p.partition(":") for p in nxt.split(";") if p]
        branches = [label for _, _, label in targets] if type_ == "decision" else []
        nodes.append({"key": key, "type": type_, "title": title, "actor": actor, "description": "",
                      "data": {"branches": branches} if branches else {}})
        edges += [{"source": key, "target": t, "label": label, "condition": ""} for t, _, label in targets]
    keys = [n["key"] for n in nodes]
    if len(set(keys)) != len(keys) or [n["type"] for n in nodes].count("start") != 1:
        raise ValueError("rozwiązanie musi mieć unikalne klucze i dokładnie jeden start")
    if missing := {e["target"] for e in edges} - set(keys):
        raise ValueError(f"rozwiązanie wskazuje nieistniejące kroki: {sorted(missing)}")
    return {"nodes": nodes, "edges": edges}


def load(directory: Path) -> dict[str, Exercise]:
    exercises = {}
    for path in sorted(Path(directory).glob("*.json")):
        try:
            ex = Exercise.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise ValueError(f"Błędny plik ćwiczenia {path.name}: {exc}") from exc
        if ex.key != path.stem:
            raise ValueError(f"Błędny plik ćwiczenia {path.name}: klucz „{ex.key}” różni się od nazwy pliku")
        exercises[ex.key] = ex
    return exercises


_catalog: dict[str, Exercise] = {}


def init() -> None:
    _catalog.clear()
    _catalog.update(load(DATA_DIR))


def get(key: str | None) -> Exercise | None:
    return _catalog.get(key) if key else None


def all_exercises() -> list[Exercise]:
    return sorted(_catalog.values(), key=lambda e: (e.level != "podstawowy", e.title))  # basics first
