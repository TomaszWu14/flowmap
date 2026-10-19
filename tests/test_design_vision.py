from app.ai.templates import full_graph
from app.design.lint import lint
from app.models import Project
from app.spec.derive import derive
from app.spec.merge import merge
from app.spec.schema import Spec, Vision, load_spec
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import play_to_end
from tests.test_projects import new_project

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}


def test_vision_draft_from_spec():
    v = derive(full_graph("booking"), META).vision
    assert "Klient chce umówić wizytę" in v.problem
    assert "Wybór usługi" in v.must and "Płatność online" in v.should
    assert "Wysłanie potwierdzenia rezerwacji" in v.could and v.goals == ["Doprowadzić do: Wizyta odbyta"]


def test_manual_vision_fields_survive_refresh():
    derived = derive(full_graph("booking"), META)
    current = derived.model_copy(deep=True)
    current.vision.metrics, current.vision.manual = ["Rezerwacja w < 2 min"], ["metrics"]
    current.vision.must = ["stare"]  # not manual -> replaced by the fresh draft
    out = merge(current, derived)
    assert out.vision.metrics == ["Rezerwacja w < 2 min"] and out.vision.must == derived.vision.must


def test_vision_guard_only_when_vision_started():
    assert lint(Spec()) == []
    codes = {i["code"] for i in lint(Spec(vision=Vision(problem="P")))}
    assert codes == {"vision_without_metrics", "vision_without_wont"}
    assert lint(Spec(vision=Vision(problem="P", metrics=["m"], wont=["w"]))) == []


def test_vision_section_edit_marks_manual(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=vision").get_data(as_text=True)
    assert "Wizja i MVP" in html and 'name="metrics"' in html
    v = load_spec(Project.query.get(p.id).spec).vision
    form = {f: "\n".join(getattr(v, f)) if f != "problem" else v.problem
            for f in ("problem", "goals", "metrics", "must", "should", "could", "wont")}
    form["metrics"] = "Rezerwacja w < 2 min\nMniej niż 5% nieodebranych wizyt"
    r = auth_client.post(f"/p/{p.id}/projekt-aplikacji/wizja", data=form)
    assert r.status_code == 302
    v = load_spec(Project.query.get(p.id).spec).vision
    assert v.metrics == ["Rezerwacja w < 2 min", "Mniej niż 5% nieodebranych wizyt"] and v.manual == ["metrics"]


def test_viewer_cannot_edit_vision(team):  # noqa: F811
    p = team["project"]
    assert team["viewer"].post(f"/p/{p.id}/projekt-aplikacji/wizja", data={"problem": "x"}).status_code in (403, 404)
