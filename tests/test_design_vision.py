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


VISION_OK = {"problem": "Klienci dzwonią, recepcja gubi zapisy", "goals": ["Rezerwacja online 24/7"],
             "metrics": ["80% rezerwacji online w 3 miesiące"], "must": ["Wybór terminu"], "should": [],
             "could": ["Przypomnienie SMS"], "wont": ["Program lojalnościowy"]}


def test_vision_ai_creates_proposal_then_accept(auth_client, app, monkeypatch):
    from tests.test_spec_review import fake
    calls = fake(monkeypatch, app, VISION_OK)
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/projekt-aplikacji/wizja/ai")
    assert len(calls) == 1 and calls[0]["tools"][0]["name"] == "draft_vision"
    spec = load_spec(Project.query.get(p.id).spec)
    prop = next(x for x in spec.proposals if x.kind == "set_vision")
    html = auth_client.get(f"/p/{p.id}/projekt-aplikacji?sekcja=vision").get_data(as_text=True)
    assert "Program lojalnościowy" in html and "Uzupełnij z AI" in html
    r = auth_client.post(f"/p/{p.id}/specyfikacja/propozycje/{prop.id}/accept", data={"back": "vision"})
    assert r.headers["Location"].endswith("sekcja=vision")
    v = load_spec(Project.query.get(p.id).spec).vision
    assert v.wont == ["Program lojalnościowy"] and set(v.manual) == set(VISION_OK)


def test_review_can_add_alternative_and_rule_row():
    from app.spec.review import apply_proposal
    from app.spec.schema import Proposal
    spec = derive(full_graph("booking"), META)
    alt = Proposal(id="a", kind="add_alternative", target_key="uc:klient", summary="Klient rezygnuje",
                   patch={"condition": "Klient rezygnuje przy płatności", "text": "Anulowanie; Zwolnienie terminu"})
    row = Proposal(id="b", kind="add_rule_row", target_key="rule:prepay", summary="VIP bez przedpłaty",
                   patch={"condition": "klient VIP", "result": "Wysłanie potwierdzenia rezerwacji"})
    spec = apply_proposal(apply_proposal(spec, alt), row)
    uc = next(u for u in spec.use_cases if u.key == "uc:klient")
    assert uc.alternatives[-1].steps == ["Anulowanie", "Zwolnienie terminu"] and uc.source == "ai"
    assert next(r for r in spec.rules if r.key == "rule:prepay").rows[-1].condition == "klient VIP"


def test_vision_md_and_claude_md():
    from app.export.builders import to_markdown
    from app.spec.package import build_files
    g = full_graph("booking")
    f = build_files(META, g, derive(g, META), [])
    assert "# Wizja i zakres MVP: Salon" in f["VISION.md"] and "## Zakres MVP (MoSCoW)" in f["VISION.md"]
    assert "VISION.md" in f["CLAUDE.md"] and "Must" in f["CLAUDE.md"]
    assert "### Zakres MVP" in to_markdown(META, g)
