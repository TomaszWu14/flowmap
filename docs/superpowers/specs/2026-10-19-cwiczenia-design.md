# Ćwiczenia — projekt

Data: 2026-10-19 · Status: zatwierdzony w rozmowie · Podprojekt 4, część 1 z 4 (kierunek:
`2026-10-19-mapa-obrazowa-bpmn-design.md`)

## Podział podprojektu 4

1. **Ćwiczenia** — ten dokument (fundament pod resztę).
2. **Postęp** — pulpit z wynikami ćwiczeń i projektów, trend, mocne i słabe kryteria, co ćwiczyć dalej.
3. **Portfolio** — publiczna strona z wybranymi projektami (mapa, UML, ocena) do linkowania w CV.
4. **Tryb rekrutacyjny** — case study na czas z rekruterem AI pytającym o decyzje i oceną na końcu.

Każda część: osobny projekt → plan → PR-y.

## Decyzje z rozmowy

1. Ocena ćwiczenia: **AI (Opus) na podstawie zadania** — ze stałą listą oczekiwań eksperta, żeby wyniki były
   porównywalne. Bez klucza API: oddanie niemożliwe (przycisk wyłączony z wyjaśnieniem), zostaje ocena z reguł.
2. Źródło ćwiczeń: **stały katalog w repozytorium** (~7 zadań).
3. Ćwiczenie ma **dwa etapy**: 1 — mapa procesu, 2 — projekt aplikacji (przypadki użycia, klasy, reguły, wizja);
   etap 2 otwiera się po pierwszym oddaniu etapu 1.
4. Oddawanie wielokrotne (historia, najlepszy wynik + ostatnia informacja zwrotna); oczekiwania eksperta
   odsłonięte dopiero po pierwszym oddaniu etapu; ćwiczenie startuje w trybie Nauka (przełączenie na Pracę —
   adnotacja przy wyniku).

## Dane

`app/exercises/data/<key>.json`, walidowane Pydantic przy starcie aplikacji (błędny plik = błąd startu i testu):

```json
{
  "key": "urlopy", "title": "Wniosek urlopowy", "domain": "HR", "level": "podstawowy",
  "brief": "5–8 zdań: sytuacja w firmie, kim jesteś, co masz dostarczyć.",
  "start_sentence": "Pracownik chce wziąć urlop",
  "stage1": ["Oczekiwanie eksperta wobec mapy — jedno zdanie", "..."],
  "stage2": ["Oczekiwanie eksperta wobec projektu aplikacji — jedno zdanie", "..."]
}
```

Katalog: urlopy (HR), reklamacje (obsługa klienta), P2P (zakupy), O2C (sprzedaż), onboarding (HR/IT),
incydenty IT (ITSM), logistyka (przyjęcie dostawy do magazynu). Poziomy: podstawowy / zaawansowany.

## Model

- `Project.exercise_key` (String(40), nullable) i `Project.exercise_stage` (Integer, `server_default="1"`).
- Tabela `exercise_attempt`: id, project_id (FK CASCADE), user_id (FK SET NULL), stage, score (0–100),
  feedback (JSON: oczekiwania z oceną spełnione/częściowo/nie + komentarz, mocne strony, 3 poprawki, tryb),
  created_at. Migracja z `server_default` dla nowych kolumn.

## Przepływ

1. `/cwiczenia` — katalog kart (dziedzina, poziom, najlepszy wynik użytkownika); „Rozpocznij” tworzy projekt
   (nazwa = tytuł, zdanie startowe z zadania, `learning=True`) i przenosi na mapę.
2. Mapa ćwiczenia: przycisk „Zadanie” w pasku → panel z treścią, etapem i „Oddaj etap N”.
3. Oddanie (`POST /p/<id>/cwiczenie/oddaj`, edytor, `spend_ai_request`): Opus przez `call_tool` (narzędzie
   strict `grade_exercise`, prompt `app/prompts/grade_exercise.md`) dostaje treść zadania, oczekiwania etapu,
   mapę (etap 1) albo specyfikację z UML (etap 2) i wynik z reguł; zwraca ocenę każdego oczekiwania, wynik 0–100,
   2–3 mocne strony, 3 najważniejsze poprawki. Zapis w `exercise_attempt`; po pierwszym oddaniu etapu 1 →
   `exercise_stage = 2`. Błąd AI → komunikat, nic nie zapisujemy.
4. `/p/<id>/cwiczenie` — treść, historia oddań obu etapów, ostatnia informacja zwrotna, odsłonięte oczekiwania.

## PR-y

1. Format i walidacja ćwiczeń + 2 zadania (urlopy, reklamacje) + migracja + katalog + start + panel „Zadanie”.
2. Oddawanie i ocena AI obu etapów + strona wyników.
3. Pozostałe 5 zadań.

## Testy i dowóz

Walidacja wszystkich plików ćwiczeń; start ćwiczenia (projekt w Nauce, zdanie startowe); oddanie z podrobionym
klientem AI (wzór `tests/test_spec_review.py::fake`; moduł woła `ai._client` przez referencję modułu); odblokowanie
etapu 2; uprawnienia (widz nie oddaje, obcy 404); brak klucza → przycisk wyłączony; migracja (`flask db upgrade`
+ `flask db check`); Playwright (oba motywy, 1440/390, 0 błędów JS); 5 kontroli CI; wdrożenie i sprawdzenie
`/cwiczenia` na produkcji (z 404 na 302).

## Poza zakresem (YAGNI)

Generowanie ćwiczeń przez AI, edytor ćwiczeń, mapa wzorcowa, limit czasu (część 4), pulpit postępu (część 2),
publikacja (część 3).
