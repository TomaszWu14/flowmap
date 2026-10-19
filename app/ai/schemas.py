from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

StepType = Literal["user_action", "screen", "automation", "decision", "parallel", "wait", "integration", "end"]
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
    version: int | None = None  # map version the options were computed for


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


class AiFillItem(BaseModel):
    node_key: str
    slot: str = Field(default="", max_length=100)
    summary: str = Field(min_length=3, max_length=300)
    steps: list[AiStep] = Field(min_length=1, max_length=4)


class AiFill(BaseModel):
    items: list[AiFillItem] = Field(max_length=12)


class AiSuggestion(BaseModel):
    problem: str = Field(min_length=3, max_length=300)
    node_key: str
    edge_label: str = Field(default="", max_length=100)
    steps: list[AiStep] = Field(min_length=1, max_length=3)


class AiDraftStep(BaseModel):
    key: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["start", "user_action", "screen", "automation", "decision", "wait", "integration", "end"]
    title: str = Field(min_length=1, max_length=200)
    actor: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)
    branches: list[str] = []


class AiDraftEdge(BaseModel):
    source: str
    target: str
    label: str = Field(default="", max_length=100)


class AiDraft(BaseModel):
    steps: list[AiDraftStep] = Field(min_length=2, max_length=40)
    edges: list[AiDraftEdge] = Field(max_length=80)

    @model_validator(mode="after")
    def _consistent(self):
        keys = [s.key for s in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("powtórzone klucze kroków")
        if sum(s.type == "start" for s in self.steps) != 1:
            raise ValueError("wymagany dokładnie jeden krok start")
        known = set(keys)
        if any(e.source not in known or e.target not in known for e in self.edges):
            raise ValueError("krawędź do nieistniejącego kroku")
        return self


class AiReview(BaseModel):
    suggestions: list[AiSuggestion] = Field(max_length=10)
