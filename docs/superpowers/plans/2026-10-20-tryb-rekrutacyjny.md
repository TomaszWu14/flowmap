# Tryb rekrutacyjny — Implementation Plan (2 PR-y)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** mapa ćwiczenia na czas (30/45/60 min) z blokadą po terminie, potem 5 pytań rekrutera AI o decyzje
na mapie i raport z rekomendacją. Projekt: `specs/2026-10-20-tryb-rekrutacyjny-design.md`.

## Global Constraints

- PR 1 (`feat/recruit-session`) scalony bez wdrożenia; wdrożenie po PR 2 (sesja bez rozmowy to ślepa uliczka).
- Migracja `c3e5a7b9d1f4` (down `b9d1f3a5c7e2`): `flask db upgrade` + `flask db check`.
- Blokada w jednym miejscu: `graph.project_for` (`need == "edit"` przy zakończonej sesji → 403, `can_edit=False`).

## PR 1: sesja, licznik, blokada

`RecruitSession` (+ `ended`), `Project.recruit`; `app/exercises/recruit.py` (`start`, `view`, `finish`);
`new_exercise_project(ex)` wspólne z `exercises.start`; pasek mapy: licznik `data-deadline` (app.js), link
„Rekrutacja”, bez trenera i przełącznika trybu; panel bez podpowiedzi; panel Zadanie: „Oddaję”.
Testy `tests/test_recruit.py`: start i termin, zły czas 400 / nieznany klucz 404, bez AI brak sesji, blokada po
terminie i po „Oddaję” (idempotentne), podpowiedź/trener/tryb wyłączone, obcy 404.

## PR 2: rozmowa i raport

`app/exercises/interview.py`: `questions(project, ex, grade)` (strict `recruit_questions`, dokładnie 5) i
`report(project, ex, grade, questions, answers)` (strict `recruit_report`, oceny 0–5 dla 5 odpowiedzi,
mocne strony, ryzyka, `invite`/`not_yet`); wynik końcowy liczony w kodzie. Trasy: `POST /p/<id>/rekrutacja/start-rozmowy`
(limit AI ×3, ocena mapy → `ExerciseAttempt` + pytania), `POST /p/<id>/rekrutacja/odpowiedz`, `POST
/p/<id>/rekrutacja/raport`. Testy z podrobionym klientem; Playwright całego przebiegu; PR → CI → merge →
wdrożenie → `/p/1/rekrutacja` z 404 na 302.
