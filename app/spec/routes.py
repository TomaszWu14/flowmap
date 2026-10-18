"""Read-only 'Specyfikacja' tab: sections derived from the map, rebuild on a broken document."""

from flask import Blueprint, Response, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pydantic import ValidationError

from .. import settings
from ..ai.client import AIError, ai_enabled
from ..extensions import db
from ..flow import graph as g
from ..models import Comment
from .forms import form_text, item_from_form
from .package import build_files, build_zip
from .readiness import readiness
from .review import apply_proposal, review_spec
from .schema import CHANNEL_LABELS, DIRECTION_LABELS, FIELD_TYPE_LABELS, NFR_LABELS, PERM_LABELS, SECTIONS

bp = Blueprint("spec", __name__)
SECTION_LABELS = {"entities": "Encje", "screens": "Ekrany", "roles": "Role", "states": "Statusy",
                  "notifications": "Powiadomienia", "integrations": "Integracje", "nfr": "Wymagania (NFR)"}
FORM_FIELDS = {
    "entities": [("name", "Nazwa", "input"), ("description", "Opis", "textarea"),
                 ("fields", "Pola: nazwa | typ | wymagane t/n | walidacja | wartości | encja odwołania | id t/n",
                  "textarea"),
                 ("relations", "Relacje: encja docelowa | 1-1/1-n/n-n | etykieta", "textarea")],
    "screens": [("name", "Nazwa", "input"), ("role", "Rola (klucz)", "input"),
                ("fields", "Pola: nazwa | typ | encja.pole", "textarea"),
                ("actions", "Akcje (po jednej w linii)", "textarea")],
    "roles": [("name", "Nazwa", "input"), ("description", "Opis", "textarea"),
              ("permissions", "Uprawnienia: encja | odczyt | tworzenie | edycja | usuwanie (all/own/none)",
               "textarea")],
    "states": [("entity", "Encja (klucz)", "input"), ("statuses", "Statusy: nazwa | start/koniec/-", "textarea"),
               ("transitions", "Przejścia: z | do", "textarea")],
    "notifications": [("trigger", "Zdarzenie", "input"), ("channel", "Kanał (email/sms/push/in_app)", "input"),
                      ("recipient_role", "Odbiorca (klucz roli)", "input"), ("summary", "Treść w skrócie", "input")],
    "integrations": [("name", "System", "input"), ("direction", "Kierunek (out/in/both)", "input"),
                     ("data", "Dane (po przecinku)", "input"), ("on_error", "Co przy błędzie", "input")],
    "nfr": [("category", "Kategoria (security/performance/privacy/accessibility/other)", "input"),
            ("text", "Treść", "textarea")],
}


def _context(project, section: str) -> dict:
    spec = g.project_spec(project)
    names = {}
    ready = None
    issues_by_key = {}
    if spec is not None:
        names = {e.key: e.name for e in spec.entities} | {r.key: r.name for r in spec.roles}
        ready = readiness(spec)
        for issue in ready["issues"]:
            issues_by_key.setdefault(issue["target_key"], []).append(issue["message"])
    return {"project": project, "spec": spec, "section": section, "sections": SECTION_LABELS,
            "type_labels_f": FIELD_TYPE_LABELS, "perm_labels": PERM_LABELS, "channel_labels": CHANNEL_LABELS,
            "direction_labels": DIRECTION_LABELS, "nfr_labels": NFR_LABELS, "names": names,
            "can_edit": project.current_role in ("owner", "editor"), "ready": ready, "issues_by_key": issues_by_key,
            "form_fields": FORM_FIELDS[section], "editing": None, "values": {}, "error": None}


def _section_response(project, section, error=None, editing=None, values=None):
    ctx = _context(project, section)
    ctx.update(error=error, editing=editing, values=values or {})
    return make_response(render_template("spec/_section.html", **ctx))


def _spec_or_abort(project):
    spec = g.project_spec(project)
    if spec is None:
        abort(409)
    return spec


@bp.get("/p/<int:project_id>/specyfikacja")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    if project.spec is None:
        g.refresh_spec(project)
        db.session.commit()
    section = request.args.get("sekcja", "entities")
    if section not in SECTIONS:
        abort(400)
    return render_template("spec/view.html", **_context(project, section))


@bp.post("/p/<int:project_id>/specyfikacja/odbuduj")
@login_required
def rebuild(project_id):
    project = g.project_for(project_id, "edit")
    project.spec = None
    g.save_version(project, "Specyfikacja odbudowana z mapy")
    db.session.commit()
    flash("Specyfikacja odbudowana z mapy.", "success")
    return redirect(url_for("spec.view", project_id=project.id))


@bp.get("/p/<int:project_id>/specyfikacja/<section>/<key>/edytuj")
@login_required
def edit_form(project_id, section, key):
    project = g.project_for(project_id, "edit")
    if section not in SECTIONS:
        abort(400)
    spec = _spec_or_abort(project)
    _sec, item = spec.find(key) if key != "nowy" else (None, None)
    if key != "nowy" and item is None:
        abort(404)
    if item is not None and _sec != section:
        abort(404)
    return _section_response(project, section, editing=key, values=form_text(section, item))


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>")
@login_required
def save_item(project_id, section, key):
    project = g.project_for(project_id, "edit")
    if section not in SECTIONS:
        abort(400)
    spec = _spec_or_abort(project)
    _sec, existing = spec.find(key) if key != "nowy" else (None, None)
    if key != "nowy" and existing is None:
        abort(404)
    if existing is not None and _sec != section:
        abort(404)
    try:
        item = item_from_form(section, request.form, existing)
    except ValueError as exc:
        return _section_response(project, section, error=str(exc), editing=key, values=request.form)
    items = [i for i in getattr(spec, section) if i.key != item.key]
    pos = next((n for n, i in enumerate(getattr(spec, section)) if i.key == item.key), len(items))
    items.insert(pos, item)
    setattr(spec, section, items)
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, f"Specyfikacja: {section} — {getattr(item, 'name', None) or item.key}")
    db.session.commit()
    return _section_response(project, section)


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>/usun")
@login_required
def delete_item(project_id, section, key):
    project = g.project_for(project_id, "edit")
    if section not in SECTIONS:
        abort(400)
    spec = _spec_or_abort(project)
    setattr(spec, section, [i for i in getattr(spec, section) if i.key != key])
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, f"Specyfikacja: usunięto {key}")
    db.session.commit()
    return _section_response(project, section)


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>/zachowaj")
@login_required
def keep_item(project_id, section, key):
    project = g.project_for(project_id, "edit")
    if section not in SECTIONS:
        abort(400)
    spec = _spec_or_abort(project)
    _sec, item = spec.find(key)
    if item is None:
        abort(404)
    if _sec != section:
        abort(404)
    item.stale, item.source = False, "manual"
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, f"Specyfikacja: zachowano {key}")
    db.session.commit()
    return _section_response(project, section)


@bp.get("/p/<int:project_id>/eksport/claude-code.zip")
@login_required
def package(project_id):
    project = g.project_for(project_id, "view")
    spec = g.project_spec(project)
    if spec is None:
        abort(409)
    comments = [c.body for c in Comment.query.filter_by(project_id=project.id, resolved=False).order_by(Comment.id)]
    meta = {"name": project.name, "start_sentence": project.start_sentence}
    body = build_zip(build_files(meta, project.graph(), spec, comments))
    return Response(body, mimetype="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="flowmap-claude-code.zip"'})


@bp.post("/p/<int:project_id>/specyfikacja/przeglad")
@login_required
def ai_review(project_id):
    project = g.project_for(project_id, "edit")
    spec = _spec_or_abort(project)
    if not ai_enabled():
        flash("Przegląd techniczny AI wymaga klucza ANTHROPIC_API_KEY.", "error")
    elif not current_user.consume_ai_request(settings.ai_daily_limit()):
        flash("Dzienny limit zapytań do AI został wyczerpany.", "error")
    else:
        db.session.commit()
        try:
            spec.proposals = review_spec(project.graph(), spec, project.start_sentence)
            project.spec = spec.model_dump(mode="json")
            g.save_version(project, f"Przegląd techniczny AI: {len(spec.proposals)} propozycji")
            flash(f"AI zaproponowało {len(spec.proposals)} zmian — zatwierdź je w panelu „Do zatwierdzenia”.",
                 "success")
        except AIError as exc:
            flash(f"Przegląd AI nieudany: {exc}.", "error")
    db.session.commit()
    return redirect(url_for("spec.view", project_id=project.id))


@bp.post("/p/<int:project_id>/specyfikacja/propozycje/<pid>/<action>")
@login_required
def proposal_action(project_id, pid, action):
    project = g.project_for(project_id, "edit")
    spec = _spec_or_abort(project)
    proposal = next((x for x in spec.proposals if x.id == pid), None)
    if proposal is None or action not in ("accept", "reject"):
        abort(404)
    if action == "reject":
        spec.proposals = [x for x in spec.proposals if x.id != pid]
    else:
        try:
            spec = apply_proposal(spec, proposal)
        except ValidationError:
            flash("Propozycja AI ma niepoprawne dane — odrzuć ją albo popraw element ręcznie.", "error")
            return redirect(url_for("spec.view", project_id=project.id))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("spec.view", project_id=project.id))
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, f"Propozycja AI {'zatwierdzona' if action == 'accept' else 'odrzucona'}: "
                            f"{proposal.summary}")
    db.session.commit()
    return redirect(url_for("spec.view", project_id=project.id))


@bp.post("/p/<int:project_id>/specyfikacja/propozycje/wszystkie")
@login_required
def accept_all(project_id):
    project = g.project_for(project_id, "edit")
    spec = _spec_or_abort(project)
    skipped = 0
    for proposal in list(spec.proposals):
        try:
            spec = apply_proposal(spec, proposal)
        except ValueError:
            skipped += 1
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, "Zatwierdzono wszystkie propozycje AI")
    db.session.commit()
    if skipped:
        flash(f"Pominięto {skipped} nieaktualnych propozycji.", "info")
    return redirect(url_for("spec.view", project_id=project.id))


@bp.post("/p/<int:project_id>/specyfikacja/stos")
@login_required
def save_stack(project_id):
    project = g.project_for(project_id, "edit")
    spec = _spec_or_abort(project)
    spec.stack = (request.form.get("stack") or "").strip()[:200]
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, "Specyfikacja: stos")
    db.session.commit()
    return redirect(url_for("spec.view", project_id=project.id))
