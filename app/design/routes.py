"""'Projekt aplikacji' tab: UML views of the spec with a Mermaid preview and the UML guard."""

from flask import Blueprint, abort, render_template, request
from flask_login import login_required

from ..flow import graph as g
from .lint import SECTION_OF, lint
from .uml import class_diagram, sequence_diagram, state_diagram, use_case_diagram

bp = Blueprint("design", __name__)
DESIGN_SECTIONS = {"classes": "Klasy", "use_cases": "Przypadki użycia", "sequences": "Sekwencje", "states": "Stany",
                   "rules": "Reguły"}
EDIT_SECTION = {"classes": "entities", "use_cases": "use_cases", "sequences": "sequences", "states": "states",
                "rules": "rules"}
HELP = {"classes": "Diagram klas UML: encje (klasy) z polami i relacjami. Krotność „1 → *” czytaj: "
                   "jeden rekord po lewej ma wiele po prawej.",
        "use_cases": "Diagram przypadków użycia UML: kto (aktor) korzysta z systemu i po co. «include» — przypadek "
                     "zawsze wywołuje inny; «extend» — wariant lub wyjątek rozszerzający scenariusz.",
        "sequences": "Diagram sekwencji UML: kto komu i w jakiej kolejności przekazuje sprawę. Pełna strzałka — "
                     "wywołanie, przerywana — odpowiedź, otwarta — komunikat asynchroniczny, krzyżyk — błąd; "
                     "blok alt pokazuje ścieżkę błędu.",
        "states": "Diagram stanów UML: przez jakie statusy przechodzi rekord. Etykieta przejścia to warunek z bramki "
                  "na mapie; [*] — początek i koniec.",
        "rules": "Tabele decyzyjne (reguły biznesowe): dla każdej decyzji — warunek i wynik. Pełna tabela obejmuje "
                 "wszystkie przypadki (np. wiersz „inaczej”)."}


def _diagrams(section, spec, project) -> list[str]:
    if section == "rules":
        return []  # decision tables are tables, rendered in the template
    if section == "states":
        return [state_diagram(sm, spec) for sm in spec.states] or ['flowchart LR\n    EMPTY["Brak statusów"]\n']
    if section == "sequences":
        return [sequence_diagram(s, spec) for s in spec.sequences] or ['flowchart LR\n    EMPTY["Brak sekwencji"]\n']
    if section == "use_cases":
        return [use_case_diagram(spec, project.name)]
    return [class_diagram(spec)]


@bp.get("/p/<int:project_id>/projekt-aplikacji")
@login_required
def view(project_id):
    project = g.project_for(project_id, "view")
    g.ensure_spec(project)
    section = request.args.get("sekcja", "classes")
    if section not in DESIGN_SECTIONS:
        abort(400)
    spec = g.project_spec(project)
    ctx = {"project": project, "spec": spec, "section": section, "sections": DESIGN_SECTIONS,
           "help": HELP[section], "edit_section": EDIT_SECTION[section], "diagrams": [], "issues": []}
    if spec is not None:
        ctx.update(diagrams=_diagrams(section, spec, project),
                   issues=[i for i in lint(spec) if SECTION_OF[i["code"]] == section])
    return render_template("design/view.html", **ctx)
