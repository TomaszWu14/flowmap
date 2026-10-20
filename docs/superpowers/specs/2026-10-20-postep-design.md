# Postęp — projekt

Data: 2026-10-20 · Status: zatwierdzony (wariant A, „rób do końca”) · Podprojekt 4, część 2 z 4
(poprzednia: `2026-10-19-cwiczenia-design.md`)

## Cel

Jedna strona `/postep`, z której użytkownik w 10 sekund wie: ile ćwiczeń zrobił i jak mu poszło, czy się poprawia,
co mu wychodzi, co nie, i które ćwiczenie zrobić teraz. Bez AI — wszystko liczone deterministycznie z zapisanych
ocen.

## Decyzje

1. **Tematy oczekiwań (wariant A).** Każde oczekiwanie eksperta w `app/exercises/data/*.json` dostaje stały temat,
   dzięki czemu werdykty z różnych ćwiczeń da się zsumować. Format: `{"text": "...", "topic": "wyjatki"}`.
   Tematy (`catalog.TOPICS`, kod → etykieta): przebieg, role, decyzje, wyjatki, terminy, komunikacja, przypadki,
   dane, statusy, reguly, uprawnienia, integracje, wizja. Nieznany temat = błąd startu.
2. Ocena zapisuje temat przy każdym oczekiwaniu (`feedback.expectations[].topic`); dla starszych oddań temat
   ustalany po tekście z katalogu (brak dopasowania → pominięte).
3. Mocne i słabe strony liczone z **ostatniego oddania każdego etapu każdego ćwiczenia** (spełnione = 1,
   częściowo = ½, niespełnione = 0) oraz z **ostatniej oceny z reguł każdego projektu** (punkty / maks. dla kodów
   kryteriów). Temat z ćwiczeń potrzebuje ≥ 2 obserwacji (pojedynczy werdykt AI to za mało); kryterium z reguł
   wystarczy jedno (liczone deterministycznie). Mocne: ≥ 70%, 3 najwyższe; do poprawy: < 70%, 3 najniższe.
4. Trend: średnia 5 ostatnich oddań vs 5 wcześniejszych (gdy jest ≥ 2 oddań: ostatnie vs pierwsze) oraz dla każdego
   ćwiczenia pierwszy → najlepszy wynik etapu.
5. „Co ćwiczyć dalej” (pierwsza pasująca reguła): (1) bez oddań → pierwsze ćwiczenie podstawowe; (2) wszystkie
   podstawowe oddane z wynikiem ≥ 70 i jest nieoddane zaawansowane → zaawansowane (najlepiej pasujące do
   najsłabszego tematu); (3) jest słaby temat → ćwiczenie z oczekiwaniami w tym temacie, kolejno: nieoddane przed
   oddanymi, niższy wynik, więcej oczekiwań w temacie; (4) pierwsze nieoddane, a gdy wszystkie oddane — najniższy
   wynik. Wynik ćwiczenia = średnia najlepszych wyników oddanych etapów.
6. Bez wykresu (YAGNI) — liczby, różnice i paski postępu w CSS.

## Moduły

- `app/exercises/progress.py` — czyste funkcje na prostych danych: `topic_stats(attempts)`,
  `criteria_stats(evaluations)`, `trend(scores)`, `recommend(exercises, best, weak_topics)`.
- Trasa `GET /postep` w `app/exercises/routes.py`; szablon `exercises/progress.html`. Linki: przycisk „Postęp” na
  `/cwiczenia` i `/projekty`.

## Testy

Walidacja tematów (każde oczekiwanie ma znany temat); czyste funkcje (wagi werdyktów, próg 2 obserwacji, trend,
rekomendacja w trzech przypadkach); strona: pusty stan, wyniki ćwiczeń, mocne/słabe, rekomendacja, tylko własne
dane; temat zapisany w nowym oddaniu. Playwright (oba motywy, 1440/390, 0 błędów JS); 5 kontroli CI; wdrożenie
(`/postep` z 404 na 302).

## Poza zakresem

Wykresy, porównanie z innymi użytkownikami, cele i odznaki, eksport postępu, portfolio (część 3).
