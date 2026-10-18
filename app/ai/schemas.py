from typing import Literal

from pydantic import BaseModel, Field, field_validator

StepType = Literal["user_action", "screen", "automation", "decision", "wait", "integration", "end"]
QuestionKind = Literal["next", "actor", "screen", "data", "error", "branches"]
OptionKind = Literal["steps", "connect", "skip", "actor", "fields", "branches"]


def _clean_list(values: list[str]) -> list[str]:
    return [v.strip()[:100] for v in values if v and v.strip()][:20]


class StepSpec(BaseModel):
    type: StepType
    title: str = Field(min_length=1, max_length=200)
    actor: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)
    inputs: list[str] = []
    outputs: list[str] = []
    branches: list[str] = []
    tpl: str = ""  # template step key (rules mode only)

    _clean = field_validator("inputs", "outputs", "branches")(_clean_list)


class Option(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    kind: OptionKind = "steps"
    steps: list[StepSpec] = []
    edge_label: str = Field(default="", max_length=100)
    edge_condition: str = Field(default="", max_length=300)
    connect_to: str = ""  # node key, or "source" = loop back to the asked node
    values: list[str] = []
    hint: str = ""


class Question(BaseModel):
    kind: QuestionKind
    node_key: str
    slot: str = ""  # decision branch label this question fills
    text: str
    hint: str = ""
    options: list[Option]
    source: Literal["rules", "ai"] = "rules"
    notice: str = ""


# --- AI tool payloads -------------------------------------------------------

class AiStep(BaseModel):
    type: StepType
    title: str = Field(min_length=1, max_length=200)
    actor: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)
    branches: list[str] = []


class AiOption(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    steps: list[AiStep] = Field(min_length=1, max_length=4)
    connect_to_key: str = ""


class AiNextQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    options: list[AiOption] = Field(min_length=3, max_length=5)


class AiSuggestion(BaseModel):
    problem: str = Field(min_length=3, max_length=300)
    node_key: str
    edge_label: str = Field(default="", max_length=100)
    steps: list[AiStep] = Field(min_length=1, max_length=3)


class AiReview(BaseModel):
    suggestions: list[AiSuggestion] = Field(max_length=10)
