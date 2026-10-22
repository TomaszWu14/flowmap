"""Browser smoke tests: the JS on key screens (map, panel, player, diagrams) — what pytest on views cannot see.

Run: python -m playwright install chromium && pytest e2e -p no:warnings
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "e2e-haslo-testowe-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    db = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "APP_ENV": "development",
           "ANTHROPIC_API_KEY": "", "ALLOW_SIGNUP": "true", "FLASK_APP": "app"}
    subprocess.run([sys.executable, "-m", "flask", "db", "upgrade"], cwd=ROOT, env=env, check=True)
    port = _free_port()
    server = subprocess.Popen([sys.executable, "-m", "flask", "run", "--port", str(port)], cwd=ROOT, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        server.kill()
        pytest.fail("serwer testowy nie wstał")
    yield url
    server.terminate()
    server.wait(10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900},
                                  bypass_csp=True)  # Playwright evaluates strings; the app CSP forbids eval
    pg = context.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    yield pg
    context.close()


_counter = iter(range(1, 10_000))


def register_and_new_map(page: Page) -> int:
    page.goto("/register")
    page.fill("input[name=email]", f"e2e{next(_counter)}-{time.time_ns()}@example.com")
    page.fill("input[name=password]", PASSWORD)
    page.fill("input[name=password2]", PASSWORD)
    page.click("button[type=submit]")
    page.goto("/projekty/nowy")
    page.fill("input[name=name]", "E2E rezerwacje")
    page.fill("input[name=start_sentence]", "Klient chce umówić wizytę w salonie")
    page.select_option("select[name=template]", "booking")
    page.click("button[type=submit]:has-text('Utwórz')")
    page.wait_for_url("**/p/*")
    page.wait_for_function("window.flowMap && window.flowMap.cy.nodes().length > 0")
    return page.evaluate("window.flowMap.cy.nodes().length")


def test_map_renders_and_answering_a_tile_adds_steps(page):
    before = register_and_new_map(page)
    page.goto(page.url)  # fresh load: the panel asks about an open step
    page.wait_for_function("window.flowMap && window.flowMap.cy.nodes().length > 0")
    page.locator("#panel-body button.tile").first.click()
    page.wait_for_function(f"window.flowMap.cy.nodes().length > {before}")
    page.evaluate("window.flowMap.cy.nodes()[0].emit('tap')")
    expect(page.locator("#panel-body")).not_to_be_empty()
    page.get_by_role("button", name="Strażnik").first.click()
    expect(page.locator("#panel-body")).to_contain_text("Wynik")
    assert page.errors == []


def test_player_opens_card_and_closes(page):
    register_and_new_map(page)
    page.get_by_role("button", name="▶ Odtwórz").click()
    page.wait_for_function("window.flowMap.cy.$('.play-current').length === 1")
    page.keyboard.press("Escape")
    page.wait_for_function("window.flowMap.cy.$('.play-current').length === 0")
    assert page.errors == []


def test_design_diagrams_render(page):
    register_and_new_map(page)
    project = page.url.rstrip("/").split("/")[-1]
    page.goto(f"/p/{project}/projekt-aplikacji?sekcja=classes")
    page.wait_for_selector("pre.mermaid svg")
    assert page.locator("text=Syntax error").count() == 0
    page.goto(f"/p/{project}/specyfikacja")
    expect(page.locator("main")).to_contain_text("Gotowość")
    assert page.errors == []


def test_png_download_and_report_page(page):
    register_and_new_map(page)
    with page.expect_download() as dl:
        page.get_by_role("button", name="⇩ PNG").click()
    assert dl.value.suggested_filename == "E2E rezerwacje.png"
    project = page.url.rstrip("/").split("/")[-1]
    page.goto(f"/p/{project}/raport")
    page.wait_for_selector("pre.mermaid svg")
    assert page.locator("text=Syntax error").count() == 0  # Mermaid draws its errors as an SVG too
    page.emulate_media(media="print")
    assert not page.locator(".topbar").is_visible()
    assert page.errors == []
