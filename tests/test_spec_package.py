import io
import zipfile

from app.ai.templates import full_graph
from app.spec.derive import derive
from app.spec.package import PASTE_PROMPT, build_files, build_zip
from app.spec.schema import Spec
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import play_to_end
from tests.test_projects import new_project

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}
FILES = {"CLAUDE.md", "SPEC.md", "DATA_MODEL.md", "ACCEPTANCE.md", "OPEN_QUESTIONS.md", "flowmap.json", "UML.md"}


def files_for(graph=None, spec=None):
    graph = graph or full_graph("booking")
    return build_files(META, graph, spec or derive(graph, META), [])


def test_all_files_and_sections():
    f = files_for()
    assert set(f) == FILES
    assert "## Kolejność budowy" in f["CLAUDE.md"] and "OPEN_QUESTIONS.md" in f["CLAUDE.md"]
    assert "| Rola |" in f["SPEC.md"] and "flowchart TD" in f["SPEC.md"]
    assert "erDiagram" in f["DATA_MODEL.md"] and "stateDiagram-v2" in f["DATA_MODEL.md"]
    assert "Zakładając" in f["ACCEPTANCE.md"] and "Wtedy" in f["ACCEPTANCE.md"]
    assert '"format": "flowmap/2"' in f["flowmap.json"]
    assert "UML.md" in f["CLAUDE.md"] and "flowchart LR" in f["UML.md"]


def test_stack_type_mapping_only_when_stack_given():
    spec = derive(full_graph("booking"), META)
    assert "Odwzorowanie typów" not in files_for(spec=spec)["CLAUDE.md"]
    spec.stack = "Flask + PostgreSQL"
    assert "Odwzorowanie typów" in files_for(spec=spec)["CLAUDE.md"]


def test_user_text_is_escaped():
    g = full_graph("booking")
    g["nodes"][1]["title"] = "<script>x</script> | *a*"
    out = files_for(graph=g)
    assert "<script>" not in out["SPEC.md"] and "<script>" not in out["DATA_MODEL.md"]


def test_zip_is_deterministic():
    f = files_for()
    a, b = build_zip(f), build_zip(f)
    assert a == b
    names = zipfile.ZipFile(io.BytesIO(a)).namelist()
    assert names == [f"docs/flowmap/{n}" for n in sorted(FILES)]


def test_download_endpoint(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    r = auth_client.get(f"/p/{p.id}/eksport/claude-code.zip")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    html = auth_client.get(f"/p/{p.id}/eksport").get_data(as_text=True)
    assert "Paczka dla Claude Code" in html and PASTE_PROMPT[:40] in html


def test_broken_stored_spec_returns_409(auth_client, db):
    """Broken spec with missing required field should return 409 on download."""
    p = new_project(auth_client)
    p.spec = {"entities": [{"name": "bez klucza"}]}
    db.session.commit()
    r = auth_client.get(f"/p/{p.id}/eksport/claude-code.zip")
    assert r.status_code == 409


def test_outsider_cannot_download_zip(team):  # noqa: F811
    """Outsider should get 404; viewer should get 200."""
    p = team["project"]
    r = team["outsider"].get(f"/p/{p.id}/eksport/claude-code.zip")
    assert r.status_code == 404
    r = team["viewer"].get(f"/p/{p.id}/eksport/claude-code.zip")
    assert r.status_code == 200 and r.mimetype == "application/zip"


def test_empty_spec_builds_package():
    """Empty spec should still produce all 6 files with ER diagram."""
    from app.export.builders import FORMAT
    meta = {"name": "Test", "start_sentence": "Start"}
    graph = {"nodes": [{"key": "s", "type": "start", "title": "Start", "actor": "", "inputs": [], "outputs": [],
                       "data": {}, "description": ""}], "edges": []}
    f = build_files(meta, graph, Spec(), [])
    assert set(f) == FILES
    assert "erDiagram" in f["DATA_MODEL.md"]
    assert f'"{FORMAT}"' in f["flowmap.json"]


def test_images_packed_and_linked_from_spec():
    from types import SimpleNamespace as NS
    graph = full_graph("booking")
    spec = derive(graph, META)
    screen = spec.screens[0]
    step = next(n for n in graph["nodes"] if n["key"] != screen.node_key and n["type"] != "start")
    images = [NS(id=7, node_key=screen.node_key, mime="image/png", data=b"png", caption="Formularz", filename="a.png"),
              NS(id=8, node_key=step["key"], mime="image/jpeg", data=b"jpg", caption="", filename="stanowisko.jpg"),
              NS(id=9, node_key="", mime="image/webp", data=b"webp", caption="Okładka", filename="c.webp")]
    f = build_files(META, graph, spec, [], images)
    assert f["images/7.png"] == b"png" and f["images/8.jpg"] == b"jpg" and f["images/9.webp"] == b"webp"
    md = f["SPEC.md"]
    assert "- Grafika: ![Formularz](images/7.png)" in md
    assert "### Materiały projektu" in md and "![Okładka](images/9.webp)" in md
    assert f"Krok: {step['title']}" in md and "![stanowisko.jpg](images/8.jpg)" in md
    names = zipfile.ZipFile(io.BytesIO(build_zip(f))).namelist()
    assert "docs/flowmap/images/8.jpg" in names


def test_download_contains_uploaded_image(auth_client):
    from app.models import Attachment
    from tests.test_media import PNG, upload
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    upload(auth_client, p)
    att = Attachment.query.one()
    zf = zipfile.ZipFile(io.BytesIO(auth_client.get(f"/p/{p.id}/eksport/claude-code.zip").data))
    assert zf.read(f"docs/flowmap/images/{att.id}.png") == PNG
    assert f"(images/{att.id}.png)" in zf.read("docs/flowmap/SPEC.md").decode()
