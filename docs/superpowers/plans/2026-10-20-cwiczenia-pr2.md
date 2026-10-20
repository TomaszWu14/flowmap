# Ćwiczenia — PR 2: oddawanie etapów i ocena AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** „Oddaj etap N” (panel Zadanie i strona wyników) → Opus ocenia każde oczekiwanie eksperta
(spełnione/częściowo/niespełnione + komentarz), wynik 0–100, mocne strony, 3 poprawki; zapis w `exercise_attempt`;
pierwsze oddanie etapu 1 otwiera etap 2; strona `/p/<id>/cwiczenie` z historią i odsłoniętymi oczekiwaniami.

**Architecture:** `app/exercises/grading.py` (`grade(project, ex, stage, spec)`, narzędzie strict `grade_exercise`,
walidator Pydantic budowany per liczba oczekiwań — każde dokładnie raz, więc `call_tool` ponawia błędną odpowiedź),
prompt `app/prompts/grade_exercise.md` (etap 1: mapa; etap 2: specyfikacja + diagram klas i przypadków użycia + mapa;
wynik z reguł jako kontekst). Trasy `POST /p/<id>/cwiczenie/oddaj` (`edit`, `spend_ai_request`) i
`GET /p/<id>/cwiczenie` (`view`). Bez migracji.

## Global Constraints

- Gałąź `feat/exercises-grading`; PR → 5 kontroli CI → merge → wdrożenie → `GET /p/1/cwiczenie` z 404 na 302.
- Błąd AI / limit / brak klucza → komunikat, nic nie zapisujemy, etap się nie zmienia.
- Etap spoza `1..exercise_stage` → 400.

## Task 1: Ocena, trasy, szablony

Testy `tests/test_exercise_grading.py` (podrobiony klient): oddanie etapu 1 zapisuje próbę, otwiera etap 2, prompt
zawiera treść i oczekiwania; etap 2 zablokowany (400), potem z diagramem klas; ponowne oddanie etapu 1 nie cofa
etapu; zła odpowiedź AI dwa razy → nic nie zapisano; bez klucza przycisk wyłączony; tryb Praca adnotowany;
widz 403, obcy 404, edytor oddaje.

## Task 2: Weryfikacja i dowóz

Playwright z serwerem z podrobionym klientem: Zadanie → Oddaj etap 1 → wyniki → Oddaj etap 2; oba motywy,
1440/390, 0 błędów JS. PR → CI → merge → wdrożenie.
