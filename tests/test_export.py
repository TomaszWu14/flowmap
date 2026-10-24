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
    graph = full_graph("booking")
    root = ET.fromstring(xml.split("\n", 1)[1])
    procs = root.findall("b:process", BPMN_NS)
    main = procs[0]
    assert main.get("name") == "Salon & <SPA>" and [p.get("name") for p in procs[1:]] == ["Klient"]  # own pool

    def all_(tag):
        return [el for p in procs for el in p.findall(tag, BPMN_NS)]

    assert len(all_("b:startEvent")) == 1 and len(all_("b:endEvent")) == 1
    assert len(all_("b:exclusiveGateway")) == 2
    assert main.find("b:intermediateCatchEvent/b:timerEventDefinition", BPMN_NS) is not None
    flows = all_("b:sequenceFlow")
    messages = root.findall("b:collaboration/b:messageFlow", BPMN_NS)
    assert messages and len(flows) + len(messages) == len(graph["edges"])  # crossing a pool = message flow
    for p in procs:  # sequence flows never leave their pool
        ids = {el.get("id") for el in p}
        seq = p.findall("b:sequenceFlow", BPMN_NS)
        assert all(f.get("sourceRef") in ids and f.get("targetRef") in ids for f in seq)
    node_ids = {el.get("id") for p in procs for el in p if el.get("id", "").startswith("Node_")}
    assert len(node_ids) == len(graph["nodes"])
    assert all(m.get("sourceRef") in node_ids and m.get("targetRef") in node_ids for m in messages)
    lanes = main.findall("b:laneSet/b:lane", BPMN_NS)
    refs = [r.text for lane in lanes for r in lane.findall("b:flowNodeRef", BPMN_NS)]
    assert "Klient" not in [lane.get("name") for lane in lanes] and len(set(refs)) == len(refs)
    participants = root.findall("b:collaboration/b:participant", BPMN_NS)
    assert [x.get("processRef") for x in participants] == [p.get("id") for p in procs]
    assert len(root.findall(".//di:BPMNShape", BPMN_NS)) == len(graph["nodes"]) + len(lanes) + len(participants)
    assert len(root.findall(".//di:BPMNEdge", BPMN_NS)) == len(graph["edges"])


def test_bpmn_without_external_roles_is_one_pool():
    graph = {"nodes": [{"key": "s", "type": "start", "title": "Start", "actor": "Biuro", "data": {}},
                       {"key": "e", "type": "end", "title": "Koniec", "actor": "Magazyn", "data": {}}],
             "edges": [{"source": "s", "target": "e", "label": "", "condition": ""}]}
    root = ET.fromstring(builders.to_bpmn(graph, "T").split("\n", 1)[1])
    assert len(root.findall("b:process", BPMN_NS)) == 1 and not root.findall(".//b:messageFlow", BPMN_NS)
    assert builders.is_external("Klient") and builders.is_external("Dostawca") and not builders.is_external("Kadry")


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


def test_bpmn_task_types_follow_pictograms():
    import xml.etree.ElementTree as ET
    graph = {"nodes": [
        {"key": "s", "type": "start", "title": "Start", "actor": "Klient", "data": {}},
        {"key": "m", "type": "automation", "title": "Wysłanie e-maila", "actor": "System", "data": {}},
        {"key": "k", "type": "user_action", "title": "Wprowadza dane do SAP ręcznie", "actor": "Biuro", "data": {}},
        {"key": "p", "type": "user_action", "title": "Pakuje towar", "actor": "Magazynier", "data": {}},
        {"key": "g", "type": "parallel", "title": "Razem", "actor": "", "data": {"branches": ["a", "b"]}},
        {"key": "e", "type": "end", "title": "Koniec", "actor": "", "data": {}}],
        "edges": [{"source": a, "target": b, "label": "", "condition": ""}
                  for a, b in (("s", "m"), ("m", "k"), ("k", "g"), ("g", "p"), ("p", "e"))]}
    procs = ET.fromstring(builders.to_bpmn(graph, "T")).findall("b:process", BPMN_NS)
    tag = {el.get("id"): el.tag.split("}")[1] for p in procs for el in p if el.get("id", "").startswith("Node_")}
    assert tag == {"Node_s": "startEvent", "Node_m": "sendTask", "Node_k": "userTask", "Node_p": "manualTask",
                   "Node_g": "parallelGateway", "Node_e": "endEvent"}


def test_printable_report(auth_client):
    from tests.test_projects import new_project

    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/raport").get_data(as_text=True)
    assert "Raport procesu" in html and "data-print" in html and 'class="mermaid"' in html
    assert "strażnik kompletności" in html and p.name in html
    assert f"/p/{p.id}/raport" in auth_client.get(f"/p/{p.id}/eksport").get_data(as_text=True)
    assert "data-export-png" in auth_client.get(f"/p/{p.id}").get_data(as_text=True)


def test_report_needs_view_access(auth_client, client):
    from tests.conftest import PASSWORD, make_user
    from tests.test_projects import new_project

    p = new_project(auth_client)
    other = client.application.test_client()
    make_user("obcy@example.com")
    other.post("/login", data={"email": "obcy@example.com", "password": PASSWORD})
    assert other.get(f"/p/{p.id}/raport").status_code == 404
