from app.ai.templates import full_graph
from app.design.lint import lint
from app.spec.derive import derive
from app.spec.merge import merge
from app.spec.schema import Spec, Vision

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
