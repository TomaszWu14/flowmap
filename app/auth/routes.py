from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField
from wtforms.validators import DataRequired, EqualTo, Length, Regexp

from .. import settings
from ..extensions import db
from ..models import MIN_PASSWORD_LENGTH, User, utcnow

bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    email = EmailField("E-mail", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Hasło", validators=[DataRequired()])


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
                flash("Konto jest zablokowane. Skontaktuj się z administratorem.", "error")
                return render_template("auth/login.html", form=form)
            user.last_login_at = utcnow()
            db.session.commit()
            login_user(user, remember=True)
            return redirect(_safe_next(request.args.get("next")))
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
            db.session.commit()
            login_user(user, remember=True)
            flash("Konto utworzone. Witaj w FlowMap!", "success")
            return redirect(url_for("projects.index"))
    return render_template("auth/register.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
