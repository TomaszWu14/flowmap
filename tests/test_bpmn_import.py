import io

import pytest

from app.ai.templates import full_graph
from app.export import builders
from app.models import Project

CAMUNDA = b"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D1">
  <bpmn:process id="P1" name="Obsluga zamowienia">
    <bpmn:laneSet><bpmn:lane id="L1" name="Sprzedawca"><bpmn:flowNodeRef>S</bpmn:flowNodeRef>
      <bpmn:flowNodeRef>T1</bpmn:flowNodeRef><bpmn:flowNodeRef>G</bpmn:flowNodeRef></bpmn:lane>
      <bpmn:lane id="L2" name="Magazyn"><bpmn:flowNodeRef>T2</bpmn:flowNodeRef><bpmn:flowNodeRef>E</bpmn:flowNodeRef>
      </bpmn:lane></bpmn:laneSet>
    <bpmn:startEvent id="S" name="Zamowienie wplynelo"/>
    <bpmn:task id="T1" name="Sprawdz   zamowienie"/>
    <bpmn:exclusiveGateway id="G" name="Czy towar jest?"/>
    <bpmn:serviceTask id="T2" name="Wydanie"/>
    <bpmn:endEvent id="E"/>
    <bpmn:sequenceFlow id="F1" sourceRef="S" targetRef="T1"/>
    <bpmn:sequenceFlow id="F2" sourceRef="T1" targetRef="G"/>
    <bpmn:sequenceFlow id="F3" sourceRef="G" targetRef="T2" name="tak"/>
    <bpmn:sequenceFlow id="F4" sourceRef="G" targetRef="E"/>
    <bpmn:sequenceFlow id="F5" sourceRef="T2" targetRef="E"/>
  </bpmn:process>
</bpmn:definitions>"""


def test_parse_camunda_style_file():
    name, graph = builders.parse_bpmn(CAMUNDA)
    by_title = {n["title"]: n for n in graph["nodes"]}
    assert name == "Obsluga zamowienia"
    assert by_title["Sprawdz zamowienie"]["type"] == "user_action" and by_title["Wydanie"]["type"] == "automation"
    assert by_title["Wydanie"]["actor"] == "Magazyn" and by_title["Zamowienie wplynelo"]["type"] == "start"
    gate = by_title["Czy towar jest?"]
    assert gate["data"]["branches"] == ["tak", "wariant 2"]  # unlabelled branch gets a name
    assert by_title["Koniec"]["type"] == "end" and len(graph["edges"]) == 5


def test_own_bpmn_export_round_trips_with_pools():
    graph = full_graph("booking")
    _name, back = builders.parse_bpmn(builders.to_bpmn(graph, "Salon").encode())
    assert len(back["nodes"]) == len(graph["nodes"]) and len(back["edges"]) == len(graph["edges"])
    assert {n["actor"] for n in graph["nodes"] if n["actor"]} <= {n["actor"] for n in back["nodes"]}
    exact = ("start", "end", "decision", "parallel", "wait")  # tasks are lossy: screen and user action are one userTask

    def kinds(g):
        return sorted(n["type"] for n in g["nodes"] if n["type"] in exact)

    assert kinds(back) == kinds(graph)


@pytest.mark.parametrize(("data", "message"), [
    (b"<nie xml", "poprawnym XML"), (b"<root/>", "BPMN 2.0"),
    (b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>', "nie zawiera procesu"),
])
def test_bad_files_get_polish_errors(data, message):
    with pytest.raises(ValueError, match=message):
        builders.parse_bpmn(data)


def test_import_route_creates_project(auth_client):
    r = auth_client.post("/projekty/import", data={"file": (io.BytesIO(CAMUNDA), "proces.bpmn")},
                         content_type="multipart/form-data")
    assert r.status_code == 302
    p = Project.query.order_by(Project.id.desc()).first()
    assert p.name == "Obsluga zamowienia" and p.start_sentence == "Zamowienie wplynelo" and len(p.nodes) == 5
    r = auth_client.post("/projekty/import", data={"file": (io.BytesIO(b"<x/>"), "zly.bpmn")},
                         content_type="multipart/form-data", follow_redirects=True)
    assert "BPMN 2.0" in r.get_data(as_text=True)
