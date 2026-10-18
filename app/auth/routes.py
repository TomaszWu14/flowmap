from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField
from wtforms.validators import DataRequired, EqualTo, Length, Regexp

from .. import audit, settings
from ..extensions import db
from ..mail import mail_enabled, send_mail
from ..models import MIN_PASSWORD_LENGTH, User, utcnow
from .tokens import make_reset_token, user_from_token

bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    email = EmailField("E-mail", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Hasło", validators=[DataRequired()])


class ForgotForm(FlaskForm):
    email = EmailField("E-mail", validators=[DataRequired(), Length(max=255)])


class ResetForm(FlaskForm):
    password = PasswordField(
        "Nowe hasło",
        validators=[
            DataRequired(),
            Length(min=MIN_PASSWORD_LENGTH, message=f"Hasło musi mieć co najmniej {MIN_PASSWORD_LENGTH} znaków."),
        ],
    )
    password2 = PasswordField(
        "Powtórz hasło", validators=[DataRequired(), EqualTo("password", message="Hasła się różnią.")]
    )


class RegisterForm(FlaskForm):
    email = EmailField("E-mail", validators=[
            DataRequired(),
            Length(max=255),
            Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Podaj poprawny adres e-mail."),
        ])
    password = PasswordField(
        "Hasło",
        validators=[
            DataRequired(),
            Length(min=MIN_PASSWORD_LENGTH, message=f"Hasło musi mieć co najmniej {MIN_PASSWORD_LENGTH} znaków."),
        ],
    )
    password2 = PasswordField(
        "Powtórz hasło", validators=[DataRequired(), EqualTo("password", message="Hasła się różnią.")]
    )


def _safe_next(target: str | None) -> str:
    if target and not urlsplit(target).netloc and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("projects.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("projects.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            if user.is_blocked:
                audit.log("login_blocked", actor=user)
                db.session.commit()
                flash("Konto jest zablokowane. Skontaktuj się z administratorem.", "error")
                return render_template("auth/login.html", form=form)
            user.last_login_at = utcnow()
            audit.log("login", actor=user)
            db.session.commit()
            login_user(user, remember=True)
            return redirect(_safe_next(request.args.get("next")))
        audit.log("login_failed", email=form.email.data.strip().lower())
        db.session.commit()
        flash("Nieprawidłowy e-mail lub hasło.", "error")
    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not settings.signup_open():
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("projects.index"))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Konto z tym adresem już istnieje.", "error")
        else:
            user = User(email=email)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            audit.log("register", actor=user)
            db.session.commit()
            login_user(user, remember=True)
            flash("Konto utworzone. Witaj w FlowMap!", "success")
            return redirect(url_for("projects.index"))
    return render_template("auth/register.html", form=form)


@bp.route("/nie-pamietam-hasla", methods=["GET", "POST"])
def forgot_password():
    if not mail_enabled():
        return render_template("auth/forgot.html", form=None)
    form = ForgotForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and not user.is_blocked:
            hours = current_app.config["RESET_TOKEN_HOURS"]
            link = url_for("auth.reset_password", token=make_reset_token(user, hours), _external=True)
            try:
                send_mail(user.email, "FlowMap: ustaw nowe hasło",
                          "Ktoś poprosił o reset hasła do FlowMap dla tego adresu.\n\n"
                          f"Ustaw nowe hasło (link ważny {hours} h, jednorazowy):\n{link}\n\n"
                          "Jeśli to nie Ty, zignoruj tę wiadomość.")
            except OSError:
                current_app.logger.exception("password reset mail failed")
        audit.log("password_reset_requested", email, email=email)
        db.session.commit()
        # Same answer whether the account exists or not (no account enumeration).
        flash("Jeśli konto istnieje, wysłaliśmy na nie link do ustawienia nowego hasła.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html", form=form)


@bp.route("/reset-hasla/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = user_from_token(token)
    if user is None:
        flash("Link wygasł albo został już użyty. Poproś o nowy.", "error")
        return redirect(url_for("auth.login"))
    form = ResetForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        audit.log("password_reset", user.email, actor=user)
        db.session.commit()
        flash("Hasło zmienione. Zaloguj się nowym hasłem.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form, email=user.email)


@bp.post("/logout")
@login_required
def logout():
    audit.log("logout")
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
