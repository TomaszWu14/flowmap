import io
import json

from app.flow import graph as g
from app.models import Project
from app.spec.schema import load_spec
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project


def spec_of(p):
    return load_spec(Project.query.get(p.id).spec)


def test_new_project_has_spec_and_it_follows_the_map(auth_client):
    p = new_project(auth_client)
    assert spec_of(p).entities[0].name == "Rezerwacja"
    answer_first_tile(auth_client, p)  # adds service/slot screens
    assert len(spec_of(p).screens) == len([n for n in Project.query.get(p.id).nodes if n.type == "screen"])


def test_manual_edit_survives_map_change(auth_client, db):
    p = new_project(auth_client)
    spec = spec_of(p)
    spec.entities[0] = spec.entities[0].model_copy(update={"name": "Wizyta", "source": "manual"})
    p.spec = spec.model_dump(mode="json")
    g.save_version(p, "ręczna zmiana")
    db.session.commit()
    answer_first_tile(auth_client, p)
    assert spec_of(p).entities[0].name == "Wizyta"


def test_undo_restores_spec_and_old_snapshots_still_load(auth_client, db):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    assert "spec" in Project.query.get(p.id).versions[-1].snapshot
    auth_client.post(f"/p/{p.id}/undo")
    assert spec_of(p).screens == []  # back to the start-only map
    v = Project.query.get(p.id).versions[0]
    v.snapshot = {k: v.snapshot[k] for k in ("nodes", "edges")}  # simulate a pre-spec snapshot
    db.session.commit()
    g.load_graph(Project.query.get(p.id), v.snapshot)
    assert spec_of(p).entities  # recomputed from the map


def test_json_export_v2_and_import_v1(auth_client):
    p = new_project(auth_client)
    data = json.loads(auth_client.get(f"/p/{p.id}/eksport/projekt.json").data)
    assert data["format"] == "flowmap/2" and data["spec"]["entities"]
    data["spec"]["stack"] = "Django"
    auth_client.post("/projekty/import", data={"file": (io.BytesIO(json.dumps(data).encode()), "p.json")},
                     content_type="multipart/form-data")
    assert spec_of(Project.query.order_by(Project.id.desc()).first()).stack == "Django"
    data["format"] = "flowmap/1"
    data.pop("spec")
    auth_client.post("/projekty/import", data={"file": (io.BytesIO(json.dumps(data).encode()), "p.json")},
                     content_type="multipart/form-data")
    assert spec_of(Project.query.order_by(Project.id.desc()).first()).entities
