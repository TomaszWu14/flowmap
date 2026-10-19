"""Read-only 'Specyfikacja' tab: sections derived from the map, rebuild on a broken document."""

from flask import Blueprint, Response, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import login_required
from pydantic import ValidationError

from ..ai.client import AIError, ai_enabled, spend_ai_request
from ..extensions import db
from ..flow import graph as g
from ..models import Attachment, Comment
from .forms import form_text, item_from_form
from .package import build_files, build_zip
from .readiness import readiness
from .review import apply_proposal, review_spec
from .schema import (
    CHANNEL_LABELS,
    DIRECTION_LABELS,
    FIELD_TYPE_LABELS,
    KIND_LABELS,
    MESSAGE_KINDS,
    NFR_LABELS,
    PERM_LABELS,
    SECTIONS,
)

bp = Blueprint("spec", __name__)
SECTION_LABELS = {"entities": "Encje", "screens": "Ekrany", "roles": "Role", "states": "Statusy",
                  "notifications": "Powiadomienia", "integrations": "Integracje", "nfr": "Wymagania (NFR)",
                  "use_cases": "Przypadki użycia", "sequences": "Sekwencje",
                  "rules": "Reguły"}
FORM_FIELDS = {
    "entities": [("name", "Nazwa", "input"), ("description", "Opis", "textarea"),
                 ("fields", "Pola: nazwa | typ | wymagane t/n | walidacja | wartości | encja odwołania | id t/n",
                  "textarea"),
                 ("relations", "Relacje: encja docelowa | 1-1/1-n/n-n | etykieta", "textarea")],
    "screens": [("name", "Nazwa", "input"), ("role", "Rola (klucz)", "input"),
                ("fields", "Pola: nazwa | typ | encja.pole", "textarea"),
                ("actions", "Akcje (po jednej w linii)", "textarea")],
    "roles": [("name", "Nazwa", "input"), ("description", "Opis", "textarea"),
              ("permissions", "Uprawnienia: encja | odczyt | tworzenie | edycja | usuwanie "
               "(all = wszystkie, own = tylko swoje, none = brak)",
               "textarea")],
    "states": [("entity", "Encja (klucz)", "input"), ("statuses", "Statusy: nazwa | start/koniec/-", "textarea"),
               ("transitions", "Przejścia: z | do | warunek", "textarea")],
    "notifications": [("trigger", "Zdarzenie", "input"), ("channel", "Kanał", CHANNEL_LABELS),
                      ("recipient_role", "Odbiorca (klucz roli)", "input"), ("summary", "Treść w skrócie", "input")],
    "integrations": [("name", "System", "input"), ("direction", "Kierunek", DIRECTION_LABELS),
                     ("data", "Dane (po przecinku)", "input"), ("on_error", "Co przy błędzie", "input")],
    "nfr": [("category", "Kategoria", NFR_LABELS),
            ("text", "Treść", "textarea")],
    "use_cases": [("name", "Nazwa", "input"), ("actor", "Aktor (klucz roli; puste = system)", "input"),
                  ("goal", "Cel (kiedy scenariusz się udał)", "input"),
                  ("main", "Scenariusz główny (krok w linii)", "textarea"),
                  ("alternatives", "Scenariusze alternatywne: warunek | krok; krok", "textarea"),
                  ("includes", "«include» — klucze przypadków użycia po przecinku", "input")],
    "sequences": [("name", "Nazwa", "input"), ("participants", "Uczestnicy (po jednym w linii)", "textarea"),
                  ("messages", "Komunikaty: od | do | tekst | call/reply/async/error "
                   "(wywołanie, odpowiedź, asynchronicznie, błąd)", "textarea")],
    "rules": [("name", "Decyzja", "input"), ("inputs", "Dane wejściowe (po przecinku)", "input"),
              ("rows", "Wiersze: warunek | wynik (dodaj „inaczej | …” dla pozostałych przypadków)", "textarea")],
}


def _context(project, section: str) -> dict:
    spec = g.project_spec(project)
    names = {}
    ready = None
    issues_by_key = {}
    if spec is not None:
        names = {i.key: getattr(i, "name", i.key) for sec in SECTIONS for i in getattr(spec, sec)}
        ready = readiness(spec)
        for issue in ready["issues"]:
            issues_by_key.setdefault(issue["target_key"], []).append(issue["message"])
    return {"project": project, "spec": spec, "section": section, "sections": SECTION_LABELS,
            "type_labels_f": FIELD_TYPE_LABELS, "perm_labels": PERM_LABELS, "channel_labels": CHANNEL_LABELS,
            "direction_labels": DIRECTION_LABELS, "nfr_labels": NFR_LABELS, "names": names,
            "kind_labels": KIND_LABELS, "message_kinds": MESSAGE_KINDS, "ai": ai_enabled(),
            "can_edit": project.can_edit, "ready": ready, "issues_by_key": issues_by_key,
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


def _load_item(project_id, section, key, allow_new=False):
    """(project, spec, item) for an edit endpoint; 400 bad section, 404 key not in this section, 409 broken spec."""
    project = g.project_for(project_id, "edit")
    if section not in SECTIONS:
        abort(400)
    spec = _spec_or_abort(project)
    if allow_new and key == "nowy":
        return project, spec, None
    found, item = spec.find(key)
    if item is None or found != section:
        abort(404)
    return project, spec, item


def _save(project, spec, description: str) -> None:
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, description)
    db.session.commit()


@bp.get("/p/<int:project_id>/specyfikacja")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
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
    project, _spec, item = _load_item(project_id, section, key, allow_new=True)
    return _section_response(project, section, editing=key, values=form_text(section, item))


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>")
@login_required
def save_item(project_id, section, key):
    project, spec, existing = _load_item(project_id, section, key, allow_new=True)
    try:
        item = item_from_form(section, request.form, existing)
    except ValueError as exc:
        return _section_response(project, section, error=str(exc), editing=key, values=request.form)
    items = [i for i in getattr(spec, section) if i.key != item.key]
    pos = next((n for n, i in enumerate(getattr(spec, section)) if i.key == item.key), len(items))
    items.insert(pos, item)
    setattr(spec, section, items)
    _save(project, spec, f"Specyfikacja: {section} — {getattr(item, 'name', None) or item.key}")
    return _section_response(project, section)


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>/usun")
@login_required
def delete_item(project_id, section, key):
    project, spec, item = _load_item(project_id, section, key)
    if item.source == "rules":
        spec.dismissed = list(dict.fromkeys([*spec.dismissed, key]))
    setattr(spec, section, [i for i in getattr(spec, section) if i.key != key])
    _save(project, spec, f"Specyfikacja: usunięto {key}")
    return _section_response(project, section)


@bp.post("/p/<int:project_id>/specyfikacja/<section>/<key>/zachowaj")
@login_required
def keep_item(project_id, section, key):
    project, spec, item = _load_item(project_id, section, key)
    item.stale, item.source = False, "manual"
    _save(project, spec, f"Specyfikacja: zachowano {key}")
    return _section_response(project, section)


@bp.get("/p/<int:project_id>/eksport/claude-code.zip")
@login_required
def package(project_id):
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
    spec = _spec_or_abort(project)
    comments = [c.body for c in Comment.query.filter_by(project_id=project.id, resolved=False).order_by(Comment.id)]
    images = Attachment.query.filter_by(project_id=project.id).order_by(Attachment.id).all()
    body = build_zip(build_files(project.meta, project.graph(), spec, comments, images))
    return Response(body, mimetype="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="flowmap-claude-code.zip"'})


@bp.post("/p/<int:project_id>/specyfikacja/przeglad")
@login_required
def ai_review(project_id):
    project = g.project_for(project_id, "edit")
    spec = _spec_or_abort(project)
    reason = spend_ai_request()
    if reason:
        flash(f"{reason}.", "error")
    else:
        try:
            new_proposals = review_spec(project.graph(), spec, project.start_sentence)
            spec.proposals = spec.proposals + new_proposals
            project.spec = spec.model_dump(mode="json")
            g.save_version(project, f"Przegląd techniczny AI: {len(new_proposals)} nowych propozycji")
            flash(f"AI zaproponowało {len(new_proposals)} nowych zmian — zatwierdź je w panelu „Do zatwierdzenia”.",
                 "success")
        except AIError as exc:
            flash(f"Przegląd AI nieudany: {exc}.", "error")
    db.session.commit()
    return redirect(url_for("spec.view", project_id=project.id))


def _back(project):
    if request.form.get("back") == "vision":
        return redirect(url_for("design.view", project_id=project.id, sekcja="vision"))
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
            return _back(project)
        except ValueError as exc:
            flash(str(exc), "error")
            return _back(project)
    project.spec = spec.model_dump(mode="json")
    g.save_version(project, f"Propozycja AI {'zatwierdzona' if action == 'accept' else 'odrzucona'}: "
                            f"{proposal.summary}")
    db.session.commit()
    return _back(project)


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
