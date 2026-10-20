"""Fixed exercise catalogue: one JSON file per task in data/, validated when the app starts."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DATA_DIR = Path(__file__).parent / "data"
STAGES = 2
LEVELS = {"podstawowy": "Podstawowy", "zaawansowany": "Zaawansowany"}


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    title: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=60)
    level: Literal["podstawowy", "zaawansowany"]
    brief: str = Field(min_length=1, max_length=3000)
    start_sentence: str = Field(min_length=1, max_length=500)
    stage1: list[str] = Field(min_length=1)  # expert expectations for the map
    stage2: list[str] = Field(min_length=1)  # expert expectations for the app design

    def expectations(self, stage: int) -> list[str]:
        return self.stage1 if stage == 1 else self.stage2


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
    return list(_catalog.values())
