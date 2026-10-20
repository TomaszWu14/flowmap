# Wdrożenie FlowMap na Coolify

FlowMap wdraża się jako zasób **Docker Compose** (aplikacja + PostgreSQL) z pliku `docker-compose.yml`.
Konfiguracja wyłącznie przez zmienne środowiskowe.

## 1. DNS

Rekord `A` dla domeny (np. `flowmap.twapp.pl`) na adres serwera Coolify. Jeśli istnieje wildcard
`*.twapp.pl` wskazujący na serwer, nic nie trzeba dodawać.

## 2. Zasób w Coolify

1. **Projects → (projekt) → + New → Public Repository** (albo *Private Repository (GitHub App)* dla repo prywatnego).
2. Repozytorium: `https://github.com/TomaszWu14/flowmap`, gałąź `main`.
3. **Build Pack: Docker Compose**, ścieżka pliku: `/docker-compose.yml`.
4. Zapisz — Coolify wczyta usługi `app` i `db`.

## 3. Domena

W ustawieniach usługi **app** w polu *Domains* wpisz:

```
https://flowmap.twapp.pl:8000
```

`:8000` mówi proxy Coolify, na który port kontenera kierować ruch (aplikacja słucha na 8000).
Certyfikat Let's Encrypt wystawi się sam.

## 4. Zmienne środowiskowe

Coolify sam generuje zmienne z prefiksem `SERVICE_` użyte w `docker-compose.yml`:

| Zmienna | Skąd | Uwagi |
|---|---|---|
| `SERVICE_HEX_32_POSTGRES` | generuje Coolify | hasło bazy w hex (znaki `/ + @` psują `DATABASE_URL`) |
| `SERVICE_PASSWORD_64_SECRETKEY` | generuje Coolify | `SECRET_KEY` aplikacji |
| `ALLOW_SIGNUP` | ręcznie, opcjonalnie | `false` = rejestracja wyłączona |
| `ANTHROPIC_API_KEY` | ręcznie, opcjonalnie | bez klucza działa tryb reguł i szablonów |
| `ANTHROPIC_MODEL` | ręcznie, opcjonalnie | domyślnie `claude-sonnet-5-5` (czat trenera: `ANTHROPIC_CHAT_MODEL`, też `claude-sonnet-5-5`) |
| `AI_DAILY_LIMIT` | ręcznie, opcjonalnie | domyślnie 100 zapytań/użytkownika/dzień (można zmienić w panelu admina) |
| `MAIL_SERVER` i reszta `MAIL_*` | ręcznie, opcjonalnie | SMTP do linków „Nie pamiętam hasła”; bez tego admin generuje link w panelu |

Jeśli Coolify nie wygeneruje którejś zmiennej `SERVICE_*`, ustaw ją ręcznie wartością z
`openssl rand -hex 32`. **Nie zmieniaj hasła bazy po pierwszym starcie** — Postgres zapisuje je
w wolumenie przy inicjalizacji.

## 5. Deploy

Kliknij **Deploy**. Kontener aplikacji przy każdym starcie wykonuje `flask db upgrade` (migracje są
idempotentne), potem uruchamia gunicorn. Healthcheck: `GET /healthz` → `{"status": "ok"}`
(sprawdza też połączenie z bazą). Status w Coolify powinien przejść na *Running (healthy)*.

## 6. Pierwsze konto

Jeśli `ALLOW_SIGNUP=true`, zarejestruj się na stronie `/register`. Przy wyłączonej rejestracji
otwórz w Coolify **Terminal** kontenera `app` i wykonaj:

```bash
flask create-user ty@example.com
```

(zapyta o hasło, min. 12 znaków). Zapomniane hasło zmienisz tak samo: `flask set-password ty@example.com`.

## 6a. Konto administratora

1. Zarejestruj się na `/register` (albo `flask create-user ty@example.com --admin` w terminalu).
2. W Coolify → **Terminal** kontenera `app`: `flask set-admin ty@example.com`.
3. Wyloguj się i zaloguj ponownie — w menu pojawi się **Admin** (`/admin`).

Uprawnień nie da się nadać przez zmienną środowiskową z adresem e-mail — przy otwartej rejestracji
ktoś mógłby założyć konto na Twój adres przed Tobą.

## 7. Aktualizacje i kopie

- Nowa wersja: push na `main` → **Redeploy** w Coolify (albo webhook / auto-deploy z GitHub App).
- Dane są w wolumenie `flowmap-db`. Kopia: w Coolify *Backups* dla bazy albo
  `docker exec <db> pg_dump -U flowmap flowmap > kopia.sql`.

## Rozwiązywanie problemów

| Objaw | Przyczyna / naprawa |
|---|---|
| Kontener `app` restartuje się, w logach `SECRET_KEY must be set` | brak `SERVICE_PASSWORD_64_SECRETKEY` — ustaw ręcznie |
| `password authentication failed` | hasło bazy zmienione po inicjalizacji wolumenu — przywróć poprzednie albo usuń wolumen (utrata danych) |
| Logowanie „nie trzyma” sesji | strona po HTTP, a ciasteczka są `Secure` — wejdź przez HTTPS albo ustaw `COOKIE_SECURE=false` (tylko testowo) |
| 502 Bad Gateway | w domenie brak `:8000` albo kontener jeszcze startuje (migracje) |
