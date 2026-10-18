import io
import zipfile

from app.ai.templates import full_graph
from app.spec.derive import derive
from app.spec.package import PASTE_PROMPT, build_files, build_zip
from tests.test_flow import play_to_end
from tests.test_projects import new_project

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę"}
FILES = {"CLAUDE.md", "SPEC.md", "DATA_MODEL.md", "ACCEPTANCE.md", "OPEN_QUESTIONS.md", "flowmap.json"}


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
