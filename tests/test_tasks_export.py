import csv
import io
import json

from app.ai.templates import full_graph
from app.export import tasks
from tests.test_flow import play_to_end
from tests.test_projects import new_project

META = {"name": "Salon", "start_sentence": "Klient chce umówić wizytę", "mode": "quick"}


def test_build_tasks_from_booking_template():
    items = tasks.build_tasks(META, full_graph("booking"))
    titles = [t["title"] for t in items]
    assert "Klient: Wybór usługi" in titles and "Decyzja: Czy termin jest wolny?" in titles
    assert not any(t.startswith(("Start", "Koniec")) for t in titles)
    service = next(t for t in items if t["title"] == "Klient: Wybór usługi")
    assert service["type"] == "Story" and "Jako Klient chcę: wybór usługi." in service["body"]
    assert "- [ ] Pole „Usługa” jest wymagane i walidowane" in service["body"]
    payment = next(t for t in items if t["title"].endswith("Płatność online"))
    assert payment["type"] == "Task" and "Błąd jest obsłużony" in payment["body"]
    decision = next(t for t in items if t["title"].startswith("Decyzja"))
    assert "Obsłużona gałąź „nie”" in decision["body"]


def test_csv_formats_and_formula_injection():
    g = full_graph("booking")
    g["nodes"][1]["title"] = "=HYPERLINK(\"http://zly.example\")"
    items = tasks.build_tasks(META, g)
    jira = list(csv.reader(io.StringIO(tasks.to_jira_csv(items))))
    assert jira[0] == ["Summary", "Description", "Issue Type", "Labels", "Labels"] and len(jira) == len(items) + 1
    assert all(not cell.startswith("=") for row in jira for cell in row)
    linear = list(csv.reader(io.StringIO(tasks.to_linear_csv(items))))
    assert linear[0] == ["Title", "Description", "Labels"] and linear[1][2].startswith("flowmap,")


def test_github_jsonl_is_one_valid_payload_per_line():
    items = tasks.build_tasks(META, full_graph("service"))
    lines = tasks.to_github_json(items).splitlines()
    assert len(lines) == len(items)
    first = json.loads(lines[0])
    assert set(first) == {"title", "body", "labels"} and "flowmap" in first["labels"]
    assert "gh api repos/OWNER/REPO/issues --input -" in tasks.GITHUB_COMMAND


def test_task_downloads(auth_client):
    p = new_project(auth_client)
    play_to_end(auth_client, p)
    html = auth_client.get(f"/p/{p.id}/eksport").get_data(as_text=True)
    assert "Zadania do Jiry, Linear, GitHuba" in html
    for kind, mime in [("zadania-jira.csv", "text/csv"), ("zadania-linear.csv", "text/csv"),
                       ("zadania-github.jsonl", "application/x-ndjson")]:
        r = auth_client.get(f"/p/{p.id}/eksport/{kind}")
        assert r.status_code == 200 and r.mimetype == mime and kind in r.headers["Content-Disposition"]
