from app.models import AuditEvent, Project
from app.spec.schema import load_spec
from app.text import plural
from tests.test_projects import new_project


def test_plural_forms():
    assert [plural(n, "problem", "problemy", "problemów") for n in (1, 3, 5, 0)] == \
        ["1 problem", "3 problemy", "5 problemów", "0 problemów"]


def test_spec_form_uses_polish_selects(auth_client):
    p = new_project(auth_client)
    html = auth_client.get(f"/p/{p.id}/specyfikacja/nfr/nowy/edytuj").get_data(as_text=True)
    assert '<select name="category">' in html and ">wydajność</option>" in html
    assert "security/performance" not in html


def test_ai_review_button_hidden_without_key(auth_client):
    p = new_project(auth_client)
    assert "Przegląd techniczny AI" not in auth_client.get(f"/p/{p.id}/specyfikacja").get_data(as_text=True)


def test_copy_and_link_off_are_audited(auth_client):
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/kopia")
    auth_client.post(f"/p/{p.id}/udostepnianie/link")
    auth_client.post(f"/p/{p.id}/udostepnianie/link")
    actions = [e.action for e in AuditEvent.query.all()]
    assert actions.count("project_created") == 2 and "share_link_disabled" in actions


def test_irreversible_actions_ask_for_confirmation(auth_client):
    p = new_project(auth_client)
    auth_client.post(f"/p/{p.id}/udostepnianie/link")
    html = auth_client.get(f"/p/{p.id}/udostepnianie").get_data(as_text=True)
    assert html.count("data-confirm=") >= 2
    assert load_spec(Project.query.get(p.id).spec) is not None
