# FlowMap

Aplikacja webowa do projektowania nowych aplikacji przez **interaktywną mapę procesu**.

Wpisujesz jedno zdanie, np. „Klient chce umówić wizytę w salonie”. FlowMap pyta krok po kroku
„co dzieje się dalej?”, podsuwa 3–5 gotowych odpowiedzi (kafelki) i opcję „inne”, a mapa procesu
rysuje się na żywo aż do końca. Z gotowej mapy powstaje specyfikacja, diagram (Mermaid, BPMN 2.0)
i gotowe polecenie dla generatora kodu (Claude Code, Lovable, Bolt).

## Co potrafi

- **Prowadzenie pytaniami** — tryb szybki (ok. 5 pytań, kroki „paczkami”) i dokładny (ok. 20 pytań:
  aktor, pola ekranu, dane, ścieżki błędów). Decyzje tworzą gałęzie, każda gałąź to otwarte pytanie.
- **Edycja mapy** — kliknij krok: zmień, usuń, dodaj krok po nim, połącz z istniejącym (pętla),
  oznacz jako koniec. Cofnij / ponów i pełna historia wersji z przywracaniem.
- **Strażnik kompletności** — wynik 0–100 na mapie, problemy podświetlone na węzłach: gałąź bez końca,
  decyzja z < 2 wyjściami, krok bez aktora, brak ścieżki błędu przy płatności/integracji, krok
  nieosiągalny, brak końca. Opcjonalny przegląd AI z dodawaniem kroków jednym kliknięciem.
- **Przejdź proces** — symulacja z perspektywy wybranej roli, jak klikalna makieta, z podsumowaniem
  (kroki, ekrany, ślepe zaułki).
- **Eksport** — specyfikacja Markdown (proces, role, ekrany, model danych, powiadomienia, historyjki
  z kryteriami akceptacji, scenariusze testów, otwarte pytania), Mermaid, BPMN 2.0 XML, prompt dla
  generatora kodu, eksport/import projektu w JSON.
- **Specyfikacja techniczna** — zakładka „Specyfikacja” wyprowadzana z mapy: encje z polami i relacjami,
  ekrany, role z uprawnieniami, statusy, powiadomienia, integracje, wymagania niefunkcjonalne. Ręczne
  zmiany przetrwają zmiany mapy, wskaźnik „Gotowość dla Claude Code” pokazuje braki. Opcjonalny przegląd
  techniczny AI tworzy propozycje do zatwierdzenia (AI niczego nie zmienia samo).
- **Paczka dla Claude Code** — ZIP ze specyfikacją, modelem danych i poleceniem do wklejenia
  (`/p/<id>/eksport/claude-code.zip`).
- **Tryb bez AI** — bez klucza API aplikacja działa na regułach i 3 szablonach procesów
  (rezerwacja wizyty, zamówienie w sklepie, zgłoszenie serwisowe).
- **Mapa z dokumentu** — wklejasz opis procesu, powstaje szkic mapy (AI albo reguły), pytania uzupełniają gałęzie.
- **Wspólna praca** — współpracownicy z rolą edytor lub podgląd; **link do podglądu** bez logowania (mapa,
  specyfikacja, symulacja); **komentarze** przy krokach (otwarte liczy strażnik).
- **Historia** — porównanie dwóch wersji mapy (dodane, usunięte i zmienione kroki z podświetleniem).
- **Własne szablony** — gotową mapę zapisujesz jako szablon; tryb bez AI podpowiada z niej kroki.
- **Eksport zadań** — Jira (CSV), Linear (CSV), GitHub Issues (JSONL + polecenie `gh`).
- **Konto** — „Nie pamiętam hasła” (link e-mailem przez SMTP albo jednorazowy link od admina).
- Publiczna strona z przykładowym projektem: `/przyklad`.
- **Panel administratora** `/admin`: statystyki; ustawienia bez redeployu (rejestracja, wyłącznik AI, limit AI);
  lista kont z blokowaniem, nadawaniem uprawnień i linkiem do ustawienia hasła; dziennik zdarzeń
  (`/admin/zdarzenia`). Treści cudzych projektów nie widać. Uprawnienia nadaje tylko `flask set-admin`
  (albo `flask create-user --admin`).

## Stos

Python 3.12, Flask (app factory, blueprinty), Flask-SQLAlchemy + Flask-Migrate (Alembic), Flask-Login,
Flask-WTF (CSRF), Jinja2 + HTMX, Cytoscape.js + dagre (w `app/static/vendor`, bez kroku budowania),
SQLite w dev / PostgreSQL w produkcji, SDK `anthropic` (tool use + Pydantic), pytest, ruff, gunicorn.

## Uruchomienie lokalnie

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # opcjonalnie: ANTHROPIC_API_KEY

export FLASK_APP=app:create_app      # Windows PowerShell: $env:FLASK_APP="app:create_app"
flask db upgrade                     # tworzy instance/flowmap.db (SQLite)
flask create-user ty@example.com     # zapyta o hasło (min. 12 znaków)
flask set-password ty@example.com    # zmiana hasła istniejącego konta
flask set-admin ty@example.com       # uprawnienia administratora (--revoke odbiera)
flask run                            # http://127.0.0.1:5000
```

Testy i lint:

```bash
pytest
ruff check .
```

Docker (app + PostgreSQL):

```bash
cp .env.example .env   # uzupełnij SERVICE_HEX_32_POSTGRES i SERVICE_PASSWORD_64_SECRETKEY (openssl rand -hex 32)
docker compose up --build
docker compose exec app flask create-user ty@example.com
```

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `APP_ENV` | `development` | `production` włącza bezpieczne ciasteczka, ProxyFix i wymaga `SECRET_KEY` |
| `SECRET_KEY` | (dev) | klucz sesji — w produkcji obowiązkowy |
| `DATABASE_URL` | `sqlite:///flowmap.db` | `postgresql://…` w produkcji (hasło w hex!) |
| `ALLOW_SIGNUP` | `true` | `false` wyłącza rejestrację (konta tylko przez `flask create-user`) |
| `COOKIE_SECURE` | `true` w produkcji | flaga `Secure` ciasteczek |
| `ANTHROPIC_API_KEY` | — | bez klucza działa tryb reguł i szablonów |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | model do pytań i przeglądu |
| `AI_TIMEOUT_SECONDS` | `60` | timeout jednego zapytania |
| `AI_DAILY_LIMIT` | `100` | limit zapytań AI na użytkownika na dzień (nadpisywany w panelu admina) |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_USE_TLS` | — | SMTP; włącza „Nie pamiętam hasła” |
| `RESET_TOKEN_HOURS` | `1` | ważność linku resetu wysyłanego e-mailem |

W `docker-compose.yml` hasło bazy i `SECRET_KEY` pochodzą ze zmiennych `SERVICE_HEX_32_POSTGRES`
i `SERVICE_PASSWORD_64_SECRETKEY` — Coolify generuje je sam. Hasło bazy jest w hex, bo znaki `/ + @`
psują `DATABASE_URL`.

## Bezpieczeństwo

CSRF na formularzach i żądaniach HTMX (nagłówek `X-CSRFToken`), każdy endpoint projektu sprawdza
właściciela (cudzy projekt → 404), treść użytkownika i AI escapowana w szablonach i eksportach,
etykiety Cytoscape jako tekst, nagłówki CSP/X-Frame-Options/nosniff/Permissions-Policy/COOP (HSTS za HTTPS).
Do AI trafia tylko mapa (klucze, typy, tytuły, aktorzy, etykiety) — bez danych konta. Prompty w `app/prompts/*.md`.

W CI (`.github/workflows/security.yml`) każdy PR przechodzi skany: gitleaks (sekrety), Bandit i Semgrep
`p/owasp-top-ten` (SAST), pip-audit (zależności) i Trivy (HIGH/CRITICAL z poprawką); Dependabot co tydzień
proponuje aktualizacje. Zgłaszanie podatności i szczegóły: [SECURITY.md](SECURITY.md).

## Struktura

```
app/
  __init__.py  config.py  models.py  extensions.py
  auth/      logowanie, rejestracja
  projects/  lista, tworzenie, kopia, wersje
  flow/      mapa, pytania (questions.py), strażnik (guard.py), symulacja, historia (graph.py)
  export/    Markdown, Mermaid, BPMN, prompt, JSON, przykład publiczny
  ai/        client.py (SDK), schemas.py (Pydantic), rules.py (pytania bez AI), templates.py (szablony)
  prompts/   system.md, next_step.md, review.md
migrations/  tests/  Dockerfile  docker-compose.yml  docs/WDROZENIE.md
```

Wdrożenie na Coolify: [docs/WDROZENIE.md](docs/WDROZENIE.md).
