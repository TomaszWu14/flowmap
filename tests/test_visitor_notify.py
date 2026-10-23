import pytest

from app.models import DemoVisitor
from app.visitor_gate import notify

DATA = {"first_name": "Jan", "last_name": "Kowalski", "company": "ACME", "consent": "y"}
URL = "https://ntfy.example/tajny-temat"


@pytest.fixture
def sent(app, monkeypatch):
    """Gate on, ntfy configured, thread run synchronously, HTTP mocked."""
    app.config.update(DEMO_VISITOR_GATE=True, NTFY_URL=URL, NTFY_TOKEN="")
    calls = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return _Resp()

    monkeypatch.setattr(notify, "_start", notify._send)
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_valid_form_sends_one_notification(client, sent):
    r = client.post("/wejscie", data=DATA)
    assert r.status_code == 302
    assert len(sent) == 1
    req, timeout = sent[0]
    assert timeout == 5 and req.full_url == URL and req.get_method() == "POST"
    assert req.data.decode("utf-8") == "Jan Kowalski (ACME) wszedł do FlowMap"
    headers = {k.lower(): v for k, v in req.header_items()}
    assert headers["title"] == "Nowy gosc: FlowMap"
    assert headers["tags"] == "bell" and headers["priority"] == "high"
    assert "authorization" not in headers
    assert all(v.isascii() for v in headers.values())


def test_token_adds_authorization(client, app, sent):
    app.config["NTFY_TOKEN"] = "tk_sekret"
    client.post("/wejscie", data=DATA)
    headers = {k.lower(): v for k, v in sent[0][0].header_items()}
    assert headers["authorization"] == "Bearer tk_sekret"


def test_honeypot_and_invalid_send_nothing(client, sent):
    assert client.post("/wejscie", data={**DATA, "website": "http://spam"}).status_code == 400
    assert client.post("/wejscie", data={**DATA, "first_name": "J"}).status_code == 200
    assert client.post("/wejscie", data={**DATA, "consent": ""}).status_code == 200
    assert sent == []


def test_no_url_no_traffic(client, app, sent):
    app.config["NTFY_URL"] = ""
    assert client.post("/wejscie", data=DATA).status_code == 302
    assert sent == [] and DemoVisitor.query.count() == 1


def test_send_failure_does_not_affect_visitor(client, monkeypatch, sent):
    def boom(req, timeout):
        raise OSError("network down")

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    r = client.post("/wejscie?next=/przyklad", data={**DATA, "next": "/przyklad"})
    assert r.status_code == 302 and r.headers["Location"] == "/przyklad"
    assert DemoVisitor.query.count() == 1
    assert client.get("/przyklad").status_code == 200


def test_body_trimmed_to_300_chars():
    req = notify.build_request(URL, "", "A" * 100, "B" * 100, "C" * 200)
    assert len(req.data.decode("utf-8")) == 300


def test_runs_in_daemon_thread(app, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, args, daemon, name):
            started.append(daemon)

        def start(self):
            pass

    app.config["NTFY_URL"] = URL
    monkeypatch.setattr(notify.threading, "Thread", FakeThread)
    with app.test_request_context():
        notify.notify_visitor("Jan", "Kowalski", "ACME")
    assert started == [True]


def test_clause_mentions_ntfy(client, app):
    app.config["DEMO_VISITOR_GATE"] = True
    page = client.get("/wejscie").get_data(as_text=True)
    assert "przez usługę powiadomień push ntfy; poza tym nikomu danych nie przekazuję." in page
    assert "i nikomu ich nie przekazuję" not in page


def test_non_http_url_is_ignored(app, monkeypatch):
    from app.visitor_gate import notify

    started = []
    monkeypatch.setattr(notify, "_start", lambda req: started.append(req))
    app.config["NTFY_URL"] = "file:///etc/passwd"
    with app.app_context():
        notify.notify_visitor("Jan", "Kowalski", "ACME")
    assert started == []
