import secrets
from datetime import UTC, date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

NODE_TYPES = ("start", "user_action", "screen", "automation", "decision", "parallel", "wait", "integration", "end")
NODE_TYPE_LABELS = {  # BPMN vocabulary, so every click teaches the right term
    "start": "Zdarzenie startowe",
    "user_action": "Zadanie użytkownika",
    "screen": "Ekran (zadanie użytkownika)",
    "automation": "Zadanie systemowe",
    "parallel": "Bramka AND (równolegle)",
    "decision": "Bramka XOR (decyzja)",
    "wait": "Zdarzenie czasowe",
    "integration": "Zadanie systemowe (integracja)",
    "end": "Zdarzenie końcowe",
}
NODE_TYPE_HELP = {
    "start": "Zdarzenie startowe (BPMN: start event) — co uruchamia proces.",
    "user_action": "Zadanie użytkownika (BPMN: user task) — człowiek wykonuje czynność, zwykle w systemie.",
    "screen": "Zadanie użytkownika na ekranie — co osoba widzi i wypełnia; staje się widokiem aplikacji.",
    "automation": "Zadanie systemowe (BPMN: service task) — system robi to sam, bez człowieka.",
    "integration": "Zadanie systemowe z systemem zewnętrznym (np. SAP, płatności, kurier) — wymiana danych.",
    "wait": "Zdarzenie czasowe (BPMN: timer event) — proces czeka na termin albo upływ czasu.",
    "decision": "Bramka XOR (BPMN: exclusive gateway) — proces idzie dokładnie jedną z gałęzi.",
    "parallel": "Bramka AND (BPMN: parallel gateway) — wszystkie ścieżki naraz; bramka łącząca czeka na każdą.",
    "end": "Zdarzenie końcowe (BPMN: end event) — tu proces (albo jego gałąź) się kończy.",
}
MIN_PASSWORD_LENGTH = 12


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_key() -> str:
    return secrets.token_hex(4)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ai_usage_date = db.Column(db.Date)
    ai_usage_count = db.Column(db.Integer, default=0, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    is_blocked = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    last_login_at = db.Column(db.DateTime)

    projects = db.relationship("Project", back_populates="owner", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Hasło musi mieć co najmniej {MIN_PASSWORD_LENGTH} znaków.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def consume_ai_request(self, daily_limit: int) -> bool:
        """Increment today's AI counter; False when the limit is reached."""
        today = date.today()
        if self.ai_usage_date != today:
            self.ai_usage_date = today
            self.ai_usage_count = 0
        if self.ai_usage_count >= daily_limit:
            return False
        self.ai_usage_count += 1
        return True


@login_manager.user_loader
def load_user(user_id: str):
    user = db.session.get(User, int(user_id))
    return None if user is None or user.is_blocked else user  # blocking ends existing sessions too


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    start_sentence = db.Column(db.String(500), nullable=False)
    mode = db.Column(db.String(20), nullable=False, default="quick")
    template = db.Column(db.String(40))
    status = db.Column(db.String(20), nullable=False, default="draft")  # draft | complete
    version_cursor_id = db.Column(db.Integer)
    share_token = db.Column(db.String(40), unique=True, index=True)  # public read-only link; None = off
    spec = db.Column(db.JSON)  # technical specification document (app/spec/schema.py)
    display = db.Column(db.JSON)  # map display settings: swimlane order and workstation icons (flow/lanes.py)
    learning = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())  # Nauka vs Praca
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    owner = db.relationship("User", back_populates="projects")
    nodes = db.relationship("Node", back_populates="project", cascade="all, delete-orphan", order_by="Node.id")
    edges = db.relationship("Edge", back_populates="project", cascade="all, delete-orphan", order_by="Edge.id")
    questions = db.relationship("QuestionLog", cascade="all, delete-orphan", order_by="QuestionLog.id")
    versions = db.relationship("Version", cascade="all, delete-orphan", order_by="Version.id")
    members = db.relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan",
                              order_by="ProjectMember.id")
    comments = db.relationship("Comment", cascade="all, delete-orphan")

    def node_by_key(self, key: str):
        return next((n for n in self.nodes if n.key == key), None)

    @property
    def meta(self) -> dict:
        """Project settings shared by exports, the spec and the AI prompts."""
        return {"name": self.name, "start_sentence": self.start_sentence, "mode": self.mode,
                "template": self.template}

    def graph(self) -> dict:
        """Plain-dict snapshot of the map; the shared format for guard, export, simulation and versions."""
        keys = {n.id: n.key for n in self.nodes}
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [
                {
                    "source": keys[e.source_id],
                    "target": keys[e.target_id],
                    "label": e.label or "",
                    "condition": e.condition or "",
                }
                for e in self.edges
            ],
        }


class Node(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False, index=True)
    key = db.Column(db.String(16), nullable=False, default=new_key)
    type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    actor = db.Column(db.String(100), default="")
    inputs = db.Column(db.JSON, default=list)
    outputs = db.Column(db.JSON, default=list)
    data = db.Column(db.JSON, default=dict)  # branches, template step key, asked helper questions
    pos_x = db.Column(db.Float)
    pos_y = db.Column(db.Float)

    project = db.relationship("Project", back_populates="nodes")

    __table_args__ = (db.UniqueConstraint("project_id", "key"),)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "type": self.type,
            "title": self.title,
            "description": self.description or "",
            "actor": self.actor or "",
            "inputs": list(self.inputs or []),
            "outputs": list(self.outputs or []),
            "data": dict(self.data or {}),
            "x": self.pos_x,
            "y": self.pos_y,
        }


class Edge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("node.id", ondelete="CASCADE"), nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey("node.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.String(100), default="")
    condition = db.Column(db.String(300), default="")

    project = db.relationship("Project", back_populates="edges")
    source = db.relationship("Node", foreign_keys=[source_id])
    target = db.relationship("Node", foreign_keys=[target_id])


class ProjectMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(10), nullable=False, default="viewer")  # viewer | editor
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User")
    project = db.relationship("Project", back_populates="members")

    __table_args__ = (db.UniqueConstraint("project_id", "user_id"),)


class Attachment(db.Model):
    """An image attached to a project (node_key empty = project material) or to one step."""

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = db.Column(db.String(16), nullable=False, default="", server_default="")
    author_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    filename = db.Column(db.String(200), nullable=False, default="")
    mime = db.Column(db.String(30), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    caption = db.Column(db.String(200), nullable=False, default="", server_default="")
    is_cover = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Evaluation(db.Model):
    """One trainer score (map or app design) for one user, kept as history."""

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    kind = db.Column(db.String(10), nullable=False)  # map | design
    score = db.Column(db.Integer, nullable=False)
    details = db.Column(db.JSON, nullable=False, default=dict)
    source = db.Column(db.String(10), nullable=False, default="rules", server_default="rules")  # rules | mixed
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = db.Column(db.String(16), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    body = db.Column(db.Text, nullable=False)
    resolved = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    author = db.relationship("User")


class QuestionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False, index=True)
    node_key = db.Column(db.String(16))
    kind = db.Column(db.String(20), nullable=False)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, default=list)
    answer = db.Column(db.Text, default="")
    source = db.Column(db.String(10), default="rules")  # rules | ai
    hint_level = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # learning-mode hints used
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class UserTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    keywords = db.Column(db.JSON, default=list)  # words in a start sentence that pick this template
    graph = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    action = db.Column(db.String(40), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    actor_email = db.Column(db.String(255), default="")  # snapshot: survives account changes
    target = db.Column(db.String(300), default="")
    ip = db.Column(db.String(64), default="")


class AppSetting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.JSON, nullable=False)


class Version(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
