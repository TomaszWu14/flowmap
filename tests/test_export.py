import io
import json
import re
import xml.etree.ElementTree as ET

import pytest

from app.ai.templates import full_graph
from app.export import builders
from app.models import Project
from tests.test_flow import play_to_end
from tests.test_projects import new_project

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę", "mode": "quick", "template": "booking"}
BPMN_NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL", "di": "http://www.omg.org/spec/BPMN/20100524/DI"}


def test_mermaid_shapes_labels_and_escaping():
    g = full_graph("booking")
    g["nodes"][1]["title"] = 'Wybór "usługi" <script>'
    mm = builders.to_mermaid(g)
    assert mm.startswith("flowchart TD")
    assert '{"Czy termin jest wolny?' in mm  # decision = rhombus
    assert '-->|"nie"|' in mm
    assert "<script>" not in mm and "#quot;usługi#quot;" in mm and "#lt;script#gt;" in mm
    assert mm.count("-->") == len(g["edges"])


def test_bpmn_is_valid_xml_with_mapped_types():
    xml = builders.to_bpmn(full_graph("booking"), "Salon & <SPA>")
    root = ET.fromstring(xml.split("\n", 1)[1])
    proc = root.find("b:process", BPMN_NS)
    assert proc.get("name") == "Salon & <SPA>"
    assert len(proc.findall("b:startEvent", BPMN_NS)) == 1
    assert len(proc.findall("b:endEvent", BPMN_NS)) == 1
    assert len(proc.findall("b:exclusiveGateway", BPMN_NS)) == 2
    assert proc.find("b:intermediateCatchEvent/b:timerEventDefinition", BPMN_NS) is not None
    flows = proc.findall("b:sequenceFlow", BPMN_NS)
    assert len(flows) == len(full_graph("booking")["edges"])
    ids = {el.get("id") for el in proc}
    assert all(f.get("sourceRef") in ids and f.get("targetRef") in ids for f in flows)
    assert len(root.findall(".//di:BPMNShape", BPMN_NS)) == len(full_graph("booking")["nodes"])


def test_markdown_has_all_sections():
    md = builders.to_markdown(META, full_graph("booking"))
    for heading in ["## 1. Opis procesu", "## 2. Role i uprawnienia", "## 3. Ekrany", "## 4. Model danych",
                    "## 5. Powiadomienia i integracje", "## 6. Historyjki użytkownika", "## 7. Scenariusze testów",
                    "## 8. Otwarte pytania"]:
        assert heading in md
    assert "### Wybór usługi" in md and "**Klient**" in md
    assert "Kryteria akceptacji" in md and "- [ ]" in md
    assert "Test błędu: „Płatność online”" in md
    assert "mapa jest kompletna" in md


def test_markdown_escapes_user_text_and_lists_open_questions():
    g = full_graph("booking")
    g["nodes"][1]["title"] = "<img src=x onerror=alert(1)> *bold*"
    g["edges"] = [e for e in g["edges"] if e["source"] != "remind"]
    md = builders.to_markdown(META, g)
    assert re.search(r"(?<!\\)<", md) is None  # every "<" escaped
    assert r"\<img" in md and r"\*bold\*" in md
    assert "Przypomnienie dzień przed wizytą" in md.split("## 8. Otwarte pytania")[1]


def test_data_model_comes_from_spec_layer(auth_client):
    from app.models import Project
    from app.spec.schema import load_spec
    from tests.test_projects import new_project
    p = new_project(auth_client)
    key = load_spec(Project.query.get(p.id).spec).entities[0].key
    auth_client.post(f"/p/{p.id}/specyfikacja/entities/{key}",
                     data={"name": "Właściciel", "description": "", "fields": "Kwota | money | t", "relations": ""})
    for url in (f"/p/{p.id}/eksport/spec.md", f"/p/{p.id}/eksport/prompt.md"):
        md = auth_client.get(url).get_data(as_text=True).split("## 4. Model danych")[1].split("## 5.")[0]
        assert "**Właściciel**: Kwota (kwota)" in md, url


def test_example_data_model_derived_without_spec():
    md = builders.to_markdown(META, full_graph("booking"))
    assert "Telefon (telefon)" in md.split("## 4. Model danych")[1].split("## 5.")[0]


def test_prompt_embeds_spec():
    spec = builders.to_markdown(META, full_graph("booking"))
    prompt = builders.to_prompt(META, spec, "lovable")
    assert "Lovable" in prompt and spec in prompt


def test_json_roundtrip_validation():
    data = builders.to_json(META, full_graph("service"))
    parsed = builders.parse_project_file(json.loads(json.dumps(data)))
    assert len(parsed.nodes) == len(data["nodes"])
    bad = dict(data, edges=data["edges"] + [{"source": "start", "target": "ghost"}])
    with pytest.raises(ValueError, match="nieistniejący"):
        builders.parse_project_file(bad)
    with pytest.raises(ValueError, match="format"):
        builders.parse_project_file(dict(data, format="other/9"))
    with pytest.raises(ValueError):
        builders.parse_project_file({"format": "flowmap/1"})


def test_export_endpoints_and_import(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/eksport").get_data(as_text=True)
    assert "Polecenie dla generatora kodu" in html and "flowchart TD" in html
    for kind, ctype in [("spec.md", "text/markdown"), ("diagram.mmd", "text/plain"), ("proces.bpmn", "application/xml"),
                        ("prompt.md", "text/markdown"), ("projekt.json", "application/json")]:
        r = auth_client.get(f"/p/{p.id}/eksport/{kind}")
        assert r.status_code == 200 and r.mimetype == ctype and "attachment" in r.headers["Content-Disposition"]
    assert auth_client.get(f"/p/{p.id}/eksport/zly.exe").status_code == 404

    body = auth_client.get(f"/p/{p.id}/eksport/projekt.json").data
    r = auth_client.post("/projekty/import", data={"file": (io.BytesIO(body), "p.json")},
                         content_type="multipart/form-data")
    assert r.status_code == 302
    imported = Project.query.order_by(Project.id.desc()).first()
    assert imported.id != p.id and len(imported.nodes) == len(p.nodes) and len(imported.edges) == len(p.edges)
    assert imported.graph()["edges"] == p.graph()["edges"]


def test_import_rejects_garbage(auth_client):
    r = auth_client.post("/projekty/import", data={"file": (io.BytesIO(b"{nie json"), "p.json")},
                         content_type="multipart/form-data", follow_redirects=True)
    assert "nie jest poprawnym JSON" in r.get_data(as_text=True)


def test_public_example_page(client, db):
    html = client.get("/przyklad").get_data(as_text=True)
    assert "Przykład: Rezerwacja wizyty" in html and "## 1. Opis procesu" in html
    data = client.get("/przyklad/graph.json").json
    assert data["score"] == 100 and len(data["nodes"]) > 5
