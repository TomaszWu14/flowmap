import click
from flask import Flask, render_template

from .config import Config
from .extensions import csrf, db, login_manager, migrate


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config["APP_ENV"] == "production" and app.config["SECRET_KEY"] == "dev-only-insecure-key":
        raise RuntimeError("SECRET_KEY must be set in production")
    if app.config["APP_ENV"] == "production":
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # behind Coolify/Traefik

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (register models for migrations)
    from .auth.routes import bp as auth_bp
    from .export.routes import bp as export_bp
    from .flow.routes import bp as flow_bp
    from .models import NODE_TYPE_LABELS
    from .projects.routes import bp as projects_bp

    app.jinja_env.globals["type_labels"] = NODE_TYPE_LABELS
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(flow_bp)
    app.register_blueprint(export_bp)

    @app.get("/healthz")
    def healthz():
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Nie znaleziono strony."), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", code=400, message=getattr(e, "description", "Błędne żądanie.")), 400

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'",
        )
        return resp

    @app.cli.command("create-user")
    @click.argument("email")
    @click.password_option()
    def create_user(email, password):
        """Create a user account (works even when ALLOW_SIGNUP is off)."""
        from .models import User

        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            raise click.ClickException("Użytkownik o tym adresie już istnieje.")
        user = User(email=email)
        try:
            user.set_password(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        db.session.add(user)
        db.session.commit()
        click.echo(f"Utworzono konto {email}")

    return app
