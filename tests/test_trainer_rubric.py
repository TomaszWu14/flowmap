from app.ai.templates import full_graph
from app.extensions import db
from app.flow import graph as g
from app.models import Project, QuestionLog
from app.trainer.rubric import design_score, evaluate, map_score
from tests.test_projects import new_project


def booking_project(client):
    p = new_project(client)
    g.load_graph(p, full_graph("booking"))
    g.refresh_spec(p)
    db.session.commit()
    return Project.query.get(p.id)


def crit(result, code):
    return next(c for c in result["criteria"] if c["code"] == code)


def test_scores_are_sums_of_bounded_criteria(auth_client):
    p = booking_project(auth_client)
    for r in evaluate(p):
        assert r["score"] == sum(c["points"] for c in r["criteria"]) and 0 <= r["score"] <= 100
        assert sum(c["max"] for c in r["criteria"]) == 100
        assert all(0 <= c["points"] <= c["max"] and c["note"] for c in r["criteria"])


def test_map_criteria_on_booking(auth_client):
    p = booking_project(auth_client)
    r = map_score(p, p.graph())
    assert crit(r, "guard")["points"] == 40 and crit(r, "errors")["points"] == 20
    assert crit(r, "hints")["points"] == 10 and "Praca" in crit(r, "hints")["note"]


def test_learning_hints_cost_points(auth_client):
    p = booking_project(auth_client)
    p.learning = True
    for _ in range(2):
        db.session.add(QuestionLog(project_id=p.id, node_key="start", kind="next", question="q", options={},
                                   hint_level=3))
    db.session.commit()
    assert crit(map_score(p, p.graph()), "hints")["points"] == 10 - 2 * 2 * 2


def test_design_vision_and_broken_spec(auth_client):
    p = booking_project(auth_client)
    spec = g.project_spec(p)
    assert crit(design_score(p.graph(), spec), "vision")["points"] == 0  # draft only: no metrics, no Won't
    spec.vision.metrics, spec.vision.wont, spec.vision.manual = ["m"], ["w"], ["problem"]
    assert crit(design_score(p.graph(), spec), "vision")["points"] == 20
    broken = design_score(p.graph(), None)
    assert broken["score"] == 0 and "Odbuduj" in broken["criteria"][0]["note"]


def test_empty_map_earns_no_free_points(auth_client):
    p = new_project(auth_client)  # only the start event
    m, d = evaluate(Project.query.get(p.id))
    assert crit(m, "errors")["points"] == 0 and crit(d, "trace")["points"] == 0
    assert m["score"] < 50
