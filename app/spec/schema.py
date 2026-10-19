"""Technical specification document stored as JSON in Project.spec."""

import secrets
import typing
from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PField

FieldType = Literal["text", "long_text", "integer", "decimal", "money", "boolean", "date", "datetime", "email",
                    "phone", "enum", "file", "reference"]
FIELD_TYPES = typing.get_args(FieldType)
FIELD_TYPE_LABELS = {
    "text": "tekst", "long_text": "długi tekst", "integer": "liczba całkowita", "decimal": "liczba dziesiętna",
    "money": "kwota", "boolean": "tak/nie", "date": "data", "datetime": "data i godzina", "email": "e-mail",
    "phone": "telefon", "enum": "lista wyboru", "file": "plik", "reference": "odwołanie",
}
PERM_LABELS = {"all": "wszystkie", "own": "tylko swoje", "none": "—"}
CHANNEL_LABELS = {"email": "e-mail", "sms": "SMS", "push": "push", "in_app": "w aplikacji"}
DIRECTION_LABELS = {"out": "wychodząca", "in": "przychodząca", "both": "dwukierunkowa"}
NFR_LABELS = {"security": "bezpieczeństwo", "performance": "wydajność", "privacy": "prywatność (RODO)",
              "accessibility": "dostępność", "other": "inne"}
KIND_LABELS = {
    "set_field_type": "zmiana typu pola", "add_field": "nowe pole", "add_relation": "nowa relacja",
    "add_status": "nowy status", "add_transition": "nowe przejście", "set_permission": "uprawnienie",
    "add_notification": "powiadomienie", "add_nfr": "wymaganie", "other_note": "uwaga",
    "add_alternative": "scenariusz alternatywny", "add_rule_row": "wiersz reguły", "set_vision": "wizja i zakres",
}
SECTIONS = ("entities", "screens", "roles", "states", "notifications", "integrations", "nfr", "use_cases", "sequences",
            "rules")
Source = Literal["rules", "ai", "manual"]
Perm = Literal["all", "own", "none"]


def new_key(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(3)}"


class Item(BaseModel):
    key: str = PField(min_length=1, max_length=80)
    source: Source = "rules"
    stale: bool = False
    node_key: str = ""


class Field(BaseModel):
    key: str = PField(min_length=1, max_length=80)
    name: str = PField(min_length=1, max_length=100)
    type: FieldType = "text"
    required: bool = False
    validation: str = PField(default="", max_length=200)
    enum_values: list[str] = []
    ref_entity: str = ""
    is_identifier: bool = False


class Relation(BaseModel):
    key: str = PField(min_length=1, max_length=80)
    to_entity: str
    kind: Literal["1-1", "1-n", "n-n"] = "1-n"
    label: str = PField(default="", max_length=100)


class Entity(Item):
    name: str = PField(min_length=1, max_length=100)
    description: str = PField(default="", max_length=1000)
    fields: list[Field] = []
    relations: list[Relation] = []


class ScreenField(BaseModel):
    ref: str = ""  # "entity_key.field_key" or empty for a screen-only field
    name: str = PField(min_length=1, max_length=100)
    type: FieldType = "text"


class Screen(Item):
    name: str = PField(min_length=1, max_length=200)
    role: str = ""  # role key
    fields: list[ScreenField] = []
    actions: list[str] = []


class Role(Item):
    name: str = PField(min_length=1, max_length=100)
    description: str = PField(default="", max_length=500)
    permissions: dict[str, dict[str, Perm]] = {}  # entity key -> {read, create, update, delete}


class Status(BaseModel):
    name: str = PField(min_length=1, max_length=60)
    initial: bool = False
    final: bool = False


class Transition(BaseModel):
    from_status: str
    to_status: str
    condition: str = PField(default="", max_length=300)
    node_key: str = ""
    role: str = ""


class StateMachine(Item):
    entity: str  # entity key
    statuses: list[Status] = []
    transitions: list[Transition] = []


class Notification(Item):
    trigger: str = PField(default="", max_length=200)
    channel: Literal["email", "sms", "push", "in_app"] = "email"
    recipient_role: str = ""
    summary: str = PField(default="", max_length=300)


class Integration(Item):
    name: str = PField(min_length=1, max_length=200)
    direction: Literal["out", "in", "both"] = "out"
    data: list[str] = []
    on_error: str = PField(default="", max_length=300)


class Nfr(Item):
    category: Literal["security", "performance", "privacy", "accessibility", "other"] = "other"
    text: str = PField(min_length=1, max_length=500)


class Alternative(BaseModel):
    condition: str = PField(min_length=1, max_length=300)
    steps: list[str] = []


class UseCase(Item):
    name: str = PField(min_length=1, max_length=200)
    actor: str = ""  # role key; empty = included use case run by the system
    goal: str = PField(default="", max_length=300)
    main: list[str] = []
    alternatives: list[Alternative] = []
    includes: list[str] = []  # keys of other use cases


MESSAGE_KINDS = {"call": "wywołanie", "reply": "odpowiedź", "async": "asynchronicznie", "error": "błąd"}


class Message(BaseModel):
    source: str = PField(min_length=1, max_length=100)
    target: str = PField(min_length=1, max_length=100)
    text: str = PField(min_length=1, max_length=300)
    kind: Literal["call", "reply", "async", "error"] = "call"


class Sequence(Item):
    name: str = PField(min_length=1, max_length=200)
    participants: list[str] = []
    messages: list[Message] = []


class RuleRow(BaseModel):
    condition: str = PField(min_length=1, max_length=200)
    result: str = PField(min_length=1, max_length=200)


class Rule(Item):
    name: str = PField(min_length=1, max_length=200)
    inputs: list[str] = []
    rows: list[RuleRow] = []


VISION_FIELDS = ("problem", "goals", "metrics", "must", "should", "could", "wont")


class Vision(BaseModel):
    problem: str = PField(default="", max_length=1000)
    goals: list[str] = []
    metrics: list[str] = []
    must: list[str] = []
    should: list[str] = []
    could: list[str] = []
    wont: list[str] = []
    manual: list[str] = []  # fields edited by hand or accepted from AI — never overwritten by the draft


class Proposal(BaseModel):
    id: str
    kind: str
    target_key: str = ""
    summary: str = PField(min_length=1, max_length=300)
    patch: dict = {}


class Spec(BaseModel):
    entities: list[Entity] = []
    screens: list[Screen] = []
    roles: list[Role] = []
    states: list[StateMachine] = []
    notifications: list[Notification] = []
    integrations: list[Integration] = []
    nfr: list[Nfr] = []
    use_cases: list[UseCase] = []
    sequences: list[Sequence] = []
    rules: list[Rule] = []
    vision: Vision = Vision()
    stack: str = PField(default="", max_length=200)
    proposals: list[Proposal] = []
    dismissed: list[str] = []

    def find(self, key: str):
        for section in SECTIONS:
            for item in getattr(self, section):
                if item.key == key:
                    return section, item
        return None, None


def load_spec(data: dict | None) -> Spec:
    """Validate stored JSON. Raises pydantic.ValidationError on a broken document."""
    return Spec.model_validate(data or {})
