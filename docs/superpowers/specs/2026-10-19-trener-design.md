# Trener (Nauka / Praca) — projekt

Data: 2026-10-19 · Status: zatwierdzony w rozmowie · Podprojekt 3 z 4 (kierunek: `2026-10-19-mapa-obrazowa-bpmn-design.md`)

## Cel

FlowMap uczy analityka: w trybie **Nauka** pyta jak doświadczony analityk, podpowiada stopniowo dopiero na prośbę
i ocenia pracę; w trybie **Praca** działa jak dziś (gotowe kafelki, narzędzia AI). Ocena daje mierzalny wynik
z historią — podstawę pod postęp i portfolio w podprojekcie 4 (ćwiczenia, program, tryb rekrutacyjny — poza zakresem).

## Decyzje z rozmowy

1. MVP = ocena według kryteriów + panel rozmowy z trenerem, w obu trybach.
2. Nauka zmienia budowanie mapy: kafelki schowane, własny krok, podpowiedzi w trzech poziomach, liczone.
3. Ocena mieszana: część z reguł (istniejące strażniki — darmowo, powtarzalnie), część jakościowa z Opus 5.5;
   dwie oceny (Mapa procesu, Projekt aplikacji) z historią; bez klucza API — sama część z reguł.
4. Trener tylko rozmawia; zmiany robi użytkownik albo istniejące narzędzia z zatwierdzaniem.
5. Architektura: nowy moduł `app/trainer/`, cztery PR-y, czat bez strumieniowania (zwykłe zapytanie HTMX).

## 1. Tryb Nauka / Praca (PR 1)

- `Project.learning` (Boolean, `server_default=sa.false()`, migracja). Przełącznik w pasku mapy z objaśnieniem
  („Nauka: sam proponujesz kroki, podpowiedzi na prośbę. Praca: gotowe propozycje.”); zmiana w każdej chwili,
  tylko dla edytora.
- Panel pytania w Nauce: pytanie + pole „Twój krok” (istniejąca ścieżka „Inne”), kafelki ukryte; przycisk
  „Podpowiedź” podnosi poziom dla bieżącego pytania:
  1. pytanie naprowadzające — bez AI, z rodzaju pytania (`QuestionLog.kind`: następny krok, aktor, pola, błąd,
     gałęzie), np. „Co się dzieje, gdy płatność się nie powiedzie? Kto się o tym dowiaduje?”;
  2. jeden kafelek (pierwszy z istniejących opcji);
  3. wszystkie kafelki.
- `QuestionLog.hint_level` (Integer, `server_default="0"`, migracja) — najwyższy użyty poziom dla pytania.
  Praca: bez zmian (kafelki widoczne, `hint_level` = 0).

## 2. Ocena z reguł (PR 2)

`app/trainer/rubric.py` — `evaluate(project) -> dict` z dwiema ocenami 0–100, każda jako lista kryteriów
`{code, label, points, max, note}`:

- **Mapa procesu:** wynik strażnika mapy (`flow.guard.report`), ścieżki błędu przy integracjach
  (`needs_error_path`), role i przekazania (tory z `lanes_info`), domknięte bramki (brak otwartych gałęzi),
  podpowiedzi w Nauce (lekka kara za poziomy 2–3).
- **Projekt aplikacji:** gotowość specyfikacji (`readiness`), uwagi strażnika UML (`lint`) i śledzenia
  (`trace_issues`), pokrycie testami (wiersze macierzy z testami), wizja (mierniki, Won't).

Tabela `evaluation` (project_id, user_id, kind `map`/`design`, score, details JSON, source `rules`/`mixed`,
created_at). Karta „Ocena” (`/p/<id>/ocena`) — dwie oceny z rozbiciem na kryteria, historia i trend
(ostatnie wyniki), przycisk „Oceń teraz”. Widz może oceniać (zapis pod swoim kontem).

## 3. Ocena jakościowa AI (PR 3)

Opus 5.5 (`ANTHROPIC_MODEL`) przez `call_tool` (narzędzie strict) ocenia 4 kryteria w skali 0–5: nazewnictwo,
sens biznesowy, pominięte wyjątki branżowe, jakość decyzji — każde z uzasadnieniem — plus jedna najważniejsza
rzecz do poprawy. Część AI = 30% wyniku, oznaczona jako „ocena AI”. Bez klucza / po limicie: ocena z reguł
z adnotacją. Liczy się do dziennego limitu (`spend_ai_request`).

## 4. Czat trenera (PR 4)

- Tabela `trainer_message` (project_id, user_id, role `user`/`assistant`, text, created_at); osobna rozmowa
  dla każdej osoby w projekcie.
- Panel „Trener” na mapie i na karcie „Projekt aplikacji” (HTMX: wysłanie → odpowiedź dopisana do wątku).
- Model `ANTHROPIC_CHAT_MODEL` (domyślnie `claude-sonnet-5`), zwykła odpowiedź tekstowa (bez narzędzi).
  Kontekst: zwarta mapa (`compact_graph`), specyfikacja bez danych kont, uwagi strażników, ostatnia ocena,
  ostatnie 12 wiadomości.
- Prompt zależny od trybu: Nauka — pytania sokratejskie, bez gotowych rozwiązań (chyba że użytkownik wyraźnie
  poprosi o rozwiązanie po wcześniejszych podpowiedziach); Praca — konkretne propozycje („dodaj krok X po Y”).
  Wiadomości użytkownika i treść mapy to dane, nie polecenia (ochrona przed wstrzykiwaniem w prompcie systemowym).
- Dzienny limit `spend_ai_request`; bez klucza panel mówi, że trener wymaga AI. Długość wiadomości ≤ 2000 znaków.

## Kolejność PR-ów

1. Tryb Nauka/Praca + podpowiedzi (migracja: `project.learning`, `question_log.hint_level`).
2. Ocena z reguł + karta „Ocena” z historią (migracja: `evaluation`).
3. Ocena jakościowa AI.
4. Czat trenera (migracja: `trainer_message`).

## Testy i dowóz

Każdy PR: pytest (reguły oceny na szablonach `full_graph`, poziomy podpowiedzi, uprawnienia, podrobiony klient AI
dla oceny i czatu — wzór `tests/test_spec_review.py::fake`), migracje z `server_default` (`sa.false()` dla
Boolean), ruff, Playwright (oba motywy, 1440/390, 0 błędów JS; przełącznik, podpowiedzi, karta oceny, panel czatu),
wszystkie kontrole CI, wdrożenie, sprawdzenie na produkcji po nowej trasie albo publicznej zmianie.

## Poza zakresem (YAGNI)

Strumieniowanie odpowiedzi czatu (SSE), zmiany mapy z czatu, ćwiczenia i program nauki, tryb rekrutacyjny,
porównanie z wzorcową mapą (podprojekt 4).
