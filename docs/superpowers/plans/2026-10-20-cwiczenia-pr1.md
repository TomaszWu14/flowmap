# Ćwiczenia — PR 1: katalog, start, panel „Zadanie” Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stały katalog ćwiczeń w repozytorium (2 zadania: urlopy, reklamacje) walidowany Pydantic przy starcie,
strona `/cwiczenia` z kartami, „Rozpocznij” tworzy projekt w trybie Nauka ze zdaniem startowym zadania, a na mapie
przycisk „Zadanie” otwiera panel z treścią i etapem.

**Architecture:** `app/exercises/catalog.py` (`Exercise` — model Pydantic, `load(dir) -> dict[str, Exercise]`,
`get(key)`, `all_exercises()`), pliki `app/exercises/data/<key>.json`; `create_app` ładuje katalog (błąd pliku =
błąd startu). Model: `Project.exercise_key`, `Project.exercise_stage` i tabela `exercise_attempt` (używana od PR 2,
tu tylko najlepszy wynik na karcie) w jednej migracji `b9d1f3a5c7e2` (down `a7e9c3d5b1f8`). Trasy w
`app/exercises/routes.py`: `GET /cwiczenia`, `POST /cwiczenia/<key>/start`, `GET /p/<id>/cwiczenie/zadanie`
(fragment HTMX do `#panel-body`, uprawnienie `view`).

## Global Constraints

- Gałąź `feat/exercises`; PR → 5 kontroli CI (jedno `gh pr checks`, bez pętli w tle) → merge → wdrożenie →
  produkcja: `/cwiczenia` z 404 na 302.
- Migracja: `flask db upgrade` na świeżej bazie + `flask db check`.
- Oczekiwania eksperta nie trafiają do HTML przed pierwszym oddaniem etapu (w PR 1 — nigdy).

## Task 1: Katalog i walidacja

Testy `tests/test_exercises.py`: wszystkie pliki z `data/` przechodzą walidację, klucz = nazwa pliku; błędny plik
(brak pola, zły poziom, pusta lista oczekiwań) → `ValueError` z nazwą pliku.

## Task 2: Model, migracja, trasy, szablony

Testy: katalog pokazuje oba zadania (bez oczekiwań eksperta); start tworzy projekt (nazwa = tytuł, zdanie startowe,
`learning`, `exercise_key`, etap 1) i przekierowuje na mapę; nieznany klucz → 404; mapa ćwiczenia ma przycisk
„Zadanie”, zwykła mapa nie; panel pokazuje treść i „Etap 1 z 2”, bez oczekiwań; obcy → 404; najlepszy wynik
z `exercise_attempt` widoczny na karcie; link „Ćwiczenia” w nawigacji.

## Task 3: Weryfikacja i dowóz

Playwright: `/cwiczenia` → „Rozpocznij” → mapa → „Zadanie” → panel; oba motywy, 1440/390, 0 błędów JS; zrzuty.
PR „Ćwiczenia (1/3): katalog, start, panel Zadanie” → CI → merge → wdrożenie → `/cwiczenia` 302.
