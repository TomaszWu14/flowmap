# Tryb rekrutacyjny — projekt

Data: 2026-10-20 · Status: zrealizowany (PR #64, PR 2) · Podprojekt 4, część 4 z 4

Część 3 „Portfolio” **pominięta** — portfolio autora istnieje poza FlowMap (portfolio.twapp.pl).

## Cel

Symulacja zadania rekrutacyjnego analityka: mapa procesu na czas, potem rozmowa z rekruterem AI o decyzjach na tej
mapie i raport z rekomendacją.

## Przebieg

1. Na karcie ćwiczenia (`/cwiczenia`) przycisk „Tryb rekrutacyjny” z wyborem czasu 30 / 45 / 60 min (tylko z
   włączonym AI). Tworzy nowy projekt ćwiczenia (tryb Nauka) i sesję `recruit_session`.
2. W czasie sesji: licznik w pasku mapy (`data-deadline`, odliczanie w JS, bez sekund w HTML); podpowiedzi, czat
   trenera i przełącznik trybu wyłączone; panel „Zadanie” zamiast „Oddaj etap” pokazuje „Oddaję”.
3. Koniec: „Oddaję” albo upływ czasu. Serwer pilnuje: `project_for(..., "edit")` dla projektu z zakończoną
   (lub przeterminowaną) sesją → 403 „Czas minął — mapa jest zablokowana”; `can_edit = False` w szablonach.
4. Rozmowa (`/p/<id>/rekrutacja`): przy pierwszym wejściu po zakończeniu — `spend_ai_request` ×3, ocena mapy
   (`grade_exercise`, etap 1, zapis jako `ExerciseAttempt` — widać w „Postępie”) i jedno wywołanie Opus tworzące
   5 pytań o decyzje na tej mapie (celuje w braki z oceny). Pytania po kolei; odpowiedź 1–1500 znaków, bez edycji.
5. Raport po 5. odpowiedzi (Opus, strict `recruit_report`): każda odpowiedź 0–5 + komentarz, wynik rozmowy
   (średnia × 20), wynik końcowy = 0,6 × mapa + 0,4 × rozmowa, 2–3 mocne strony, 2–3 ryzyka, rekomendacja
   `invite` / `not_yet` z uzasadnieniem. Błąd AI → komunikat i ponowienie przyciskiem, odpowiedzi zostają.

## Model

`recruit_session`: id, project_id (FK CASCADE, unique), user_id (FK SET NULL), minutes, started_at, deadline,
finished_at (nullable), grade (JSON, nullable — feedback oceny mapy), questions (JSON, nullable),
answers (JSON, lista tekstów, `server_default='[]'`), report (JSON, nullable). Relacja `Project.recruit`
(uselist=False). Sesja zakończona = `finished_at` lub `utcnow() > deadline`.

## PR-y

1. Sesja: model + migracja, start z wyborem czasu, licznik, blokada edycji, wyłączone podpowiedzi/trener/tryb,
   „Oddaję”, strona `/p/<id>/rekrutacja` ze stanem sesji.
2. Rozmowa i raport: ocena mapy + pytania (Opus), odpowiedzi po kolei, raport, historia na stronie wyników.

## Testy

Start (projekt, sesja, termin), blokada po terminie i po „Oddaję” (403 na edycję mapy, podgląd działa),
podpowiedzi/trener/tryb wyłączone w sesji, bez klucza przycisk wyłączony, uprawnienia (obcy 404); PR 2 z
podrobionym klientem: pytania, kolejność odpowiedzi, limit długości, raport i wyliczenie wyniku, błąd AI.
Playwright (oba motywy, 1440/390, 0 błędów JS), 5 kontroli CI, wdrożenie.

## Poza zakresem

Etap 2 w trybie rekrutacyjnym, rozmowa głosowa, adaptacyjne dopytywanie, pauza licznika.
