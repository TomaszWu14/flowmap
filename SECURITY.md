# Bezpieczeństwo

## Zgłaszanie podatności

Podatności zgłaszaj **prywatnie** — nie przez publiczne issue ani PR (repozytorium jest publiczne):
GitHub *Security → Report a vulnerability* (Private vulnerability reporting):
<https://github.com/TomaszWu14/flowmap/security/advisories/new>.

Podaj: commit (SHA) albo wersję wdrożenia, kroki odtworzenia i skutek. Odpowiedź najczęściej do 7 dni.
Testuj tylko na własnej, lokalnej instancji — bez ataków odmowy usługi i bez prób dostępu do cudzych danych.

## Zakres

Wspierana jest gałąź domyślna (`main`) i wdrożenie zbudowane z jej aktualnego stanu; poprawki nie są
przenoszone do starszych commitów.

## Automatyczne kontrole (CI)

| Narzędzie | Co sprawdza | Gdzie |
|---|---|---|
| gitleaks (wersja przypięta + sha256) | sekrety w historii gita (PR: jego commity; `main`/co tydzień: cała historia) | `.github/workflows/security.yml` |
| Bandit | SAST kodu `app/` (severity i confidence medium+) | `security.yml` |
| Semgrep `p/owasp-top-ten` | reguły OWASP Top 10 dla `app/` (bez `app/static/vendor`) | `security.yml` |
| pip-audit | znane podatności w `requirements.txt` i `requirements-dev.txt` | `security.yml` |
| Trivy `fs` | podatności, sekrety i błędy konfiguracji — HIGH/CRITICAL z dostępną poprawką | `security.yml` |
| Dependabot | cotygodniowe PR-y: pip, Docker, GitHub Actions (grupy minor+patch) | `.github/dependabot.yml` |

Każdy skan jest bramką: czerwony wynik = nie scalać. Fałszywe alarmy oznaczamy jawnie, z powodem:
`.gitleaksignore` (fingerprint), `# nosec BXXX`, `nosemgrep: <id> — powód` (w szablonach Jinja
`{# nosemgrep: … #}`), `.trivyignore` (ID + powód + data przeglądu).

Aplikacja wysyła na każdej odpowiedzi nagłówki: `Content-Security-Policy`, `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`,
`Cross-Origin-Opener-Policy: same-origin`, `Cache-Control: no-store` dla JSON oraz HSTS, gdy działa
za HTTPS (`COOKIE_SECURE`, domyślnie w produkcji) — test `tests/test_security_headers.py`.
