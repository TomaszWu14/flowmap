import os


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///flowmap.db")
    # Coolify/Heroku style URLs -> SQLAlchemy psycopg3 driver
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    ALLOW_SIGNUP = _bool("ALLOW_SIGNUP", True)
    # Visitor gate in front of the demo: on by default only in production (DEMO_VISITOR_GATE=false turns it off).
    DEMO_VISITOR_GATE = _bool("DEMO_VISITOR_GATE", APP_ENV == "production")
    # Push notification (ntfy) on each new gate visitor; empty = off.
    NTFY_URL = os.environ.get("NTFY_URL", "")
    NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
    # Comma-separated company phrases (env only, never in the repo): a match makes the push urgent.
    NTFY_WATCH_COMPANIES = os.environ.get("NTFY_WATCH_COMPANIES", "")
    # One push when a visitor reaches this many demo screens; 0 = off.
    NTFY_ENGAGED_VIEWS = int(os.environ.get("NTFY_ENGAGED_VIEWS") or "10")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("COOKIE_SECURE", APP_ENV == "production")
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # JSON import limit

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "FlowMap <no-reply@flowmap.local>")
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    RESET_TOKEN_HOURS = int(os.environ.get("RESET_TOKEN_HOURS", "1"))

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")  # grading, questions, reports
    ANTHROPIC_CHAT_MODEL = os.environ.get("ANTHROPIC_CHAT_MODEL", "claude-sonnet-5-5")  # trainer chat
    AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", "60"))
    AI_DAILY_LIMIT = int(os.environ.get("AI_DAILY_LIMIT", "100"))
    AI_MONTHLY_BUDGET_USD = float(os.environ.get("AI_MONTHLY_BUDGET_USD", "0"))  # 0 = no FlowMap cap


class TestConfig(Config):
    TESTING = True
    APP_ENV = "testing"
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    ANTHROPIC_API_KEY = ""
    ALLOW_SIGNUP = True
    DEMO_VISITOR_GATE = False
    NTFY_URL = ""
    NTFY_TOKEN = ""
    NTFY_WATCH_COMPANIES = ""
    NTFY_ENGAGED_VIEWS = 10
    MAIL_SERVER = ""
