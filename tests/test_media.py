import io

from app.media import routes as media
from app.media.routes import sniff
from app.models import Attachment, Project
from tests.test_collaborators import team  # noqa: F401
from tests.test_flow import answer_first_tile
from tests.test_projects import new_project

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def upload(client, p, data=PNG, name="zrzut.png", node_key=""):
    return client.post(f"/p/{p.id}/grafiki", data={"file": (io.BytesIO(data), name), "node_key": node_key},
                       content_type="multipart/form-data")


def test_sniff_accepts_images_only():
    assert sniff(PNG) == "image/png" and sniff(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp" and sniff(b"GIF89a...") == "image/gif"
    assert sniff(b"<svg xmlns='http://www.w3.org/2000/svg'>") is None and sniff(b"<html>") is None


def test_step_image_upload_show_delete_and_map_data(auth_client):
    p = new_project(auth_client)
    answer_first_tile(auth_client, p)
    node = next(n for n in Project.query.get(p.id).nodes if n.type != "start")
    r = upload(auth_client, p, node_key=node.key)
    assert r.status_code == 200 and "gallery-grid" in r.get_data(as_text=True)
    att = Attachment.query.one()
    shown = auth_client.get(f"/p/{p.id}/grafiki/{att.id}")
    assert shown.data == PNG and shown.mimetype == "image/png"
    data = auth_client.get(f"/p/{p.id}/graph.json").get_json()
    step = next(n for n in data["nodes"] if n["key"] == node.key)
    assert step["images"] == 1 and step["image_url"].endswith(f"/grafiki/{att.id}")
    assert "Grafiki" in auth_client.get(f"/p/{p.id}/panel?node={node.key}").get_data(as_text=True)
    auth_client.post(f"/p/{p.id}/grafiki/{att.id}/usun")
    assert Attachment.query.count() == 0


def test_refuses_non_images_too_big_and_over_limit(auth_client, monkeypatch):
    p = new_project(auth_client)
    assert "nie jest obraz" in upload(auth_client, p, b"<svg onload=alert(1)>", "x.svg").get_data(as_text=True)
    monkeypatch.setattr(media, "MAX_BYTES", 32)
    assert "za duży" in upload(auth_client, p).get_data(as_text=True)
    monkeypatch.setattr(media, "MAX_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(media, "MAX_PER_PROJECT", 1)
    upload(auth_client, p)
    assert "usuń niepotrzebne" in upload(auth_client, p).get_data(as_text=True)
    assert Attachment.query.count() == 1


def test_cover_on_project_list_and_share_link(auth_client):
    p = new_project(auth_client)
    upload(auth_client, p)
    att = Attachment.query.one()
    auth_client.post(f"/p/{p.id}/grafiki/{att.id}/okladka")
    assert f"/grafiki/{att.id}" in auth_client.get("/projekty").get_data(as_text=True)
    assert "Materiały projektu" in auth_client.get(f"/p/{p.id}/materialy").get_data(as_text=True)
    auth_client.post(f"/p/{p.id}/udostepnianie/link")
    token = Project.query.get(p.id).share_token
    assert auth_client.get(f"/s/{token}/grafiki/{att.id}").data == PNG
    assert auth_client.get(f"/s/zly-token/grafiki/{att.id}").status_code == 404


def test_viewer_sees_but_cannot_upload(team):  # noqa: F811
    p = team["project"]
    assert upload(team["owner"], p).status_code == 200
    att = Attachment.query.one()
    assert team["viewer"].get(f"/p/{p.id}/grafiki/{att.id}").status_code == 200
    assert upload(team["viewer"], p).status_code == 403
    assert team["viewer"].post(f"/p/{p.id}/grafiki/{att.id}/usun").status_code == 403
