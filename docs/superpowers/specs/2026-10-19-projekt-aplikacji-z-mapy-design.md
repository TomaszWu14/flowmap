# Projekt aplikacji z mapy — projekt

Data: 2026-10-19 · Status: zatwierdzony w rozmowie · Podprojekt 2 z 4 (kierunek: `2026-10-19-mapa-obrazowa-bpmn-design.md`)

## Cel

Z mapy procesu i warstwy specyfikacji FlowMap generuje dokumentację projektu aplikacji na poziomie korporacyjnym:
wizja i zakres MVP, UML (klasy, przypadki użycia, sekwencje, stany), reguły biznesowe, C4 kontekst i macierz
śledzenia wymagań. Każdy diagram ma strażnika, który tłumaczy błędy („dlaczego to błąd”) — narzędzie do pracy
jest jednocześnie lekcją UML. Wszystko trafia do paczki ZIP dla Claude Code.

## Decyzje z rozmowy

1. Zakres MVP: tylko generowanie dokumentacji. Ćwiczenia „narysuj sam, potem porównaj” — podprojekt 3.
2. Widok: karta „Projekt aplikacji”; w każdej sekcji edytowalna treść (formularze jak w specyfikacji) + podgląd
   Mermaid. Ten sam tekst Mermaid trafia do `UML.md` w ZIP.
3. Treść: reguły z mapy i specyfikacji (deterministycznie, jak `app/spec/derive.py`) + przycisk „Uzupełnij z AI”
   (Opus 5.5, dzienny limit) tylko tam, gdzie mapa nie wystarcza. Ręczne poprawki przetrwają zmiany mapy.
4. Strażnik UML w MVP: każda sekcja dostaje 2–4 reguły w tym samym PR.
5. Architektura: rozszerzenie istniejącego `Spec` (nie osobny dokument) + moduł `app/design/`.

## Dane — rozszerzenie `Spec` (`app/spec/schema.py`)

Nowe sekcje-listy dziedziczą po `Item` (`key`, `source`, `stale`, `node_key`) i są dopisane do `SECTIONS`, więc
`merge()` chroni elementy `manual`/`ai`, oznacza nieaktualne (`stale`) i respektuje `dismissed` bez nowego kodu.
Każda ma pole `name` (wymagane przez sprawdzanie duplikatów w `readiness()`).

| Sekcja | Pola | Reguła wyliczania z mapy |
|---|---|---|
| `use_cases` | `name`, `actor` (klucz roli), `goal`, `main: list[str]`, `alternatives: list[{condition, steps}]`, `includes: list[str]` | Jeden przypadek na tor (aktora ≠ System): kroki aktora w kolejności `_ordered`. Bramka w ciągu → scenariusz alternatywny (etykieta krawędzi = warunek, kroki gałęzi do powrotu lub końca). Kroki „System”/automatyzacje wywołane w ciągu → `includes` (przypadek `uc:system`). `goal` = tytuł ostatniego kroku toru. Klucz `uc:<slug aktora>`. |
| `sequences` | `name`, `participants: list[str]`, `messages: list[{source, target, text, async, error}]` | Jedna sekwencja dla ścieżki głównej (`_ordered`). Zmiana toru między kolejnymi krokami = komunikat (tekst = tytuł kroku docelowego). Integracja = komunikat do systemu zewnętrznego i odpowiedź; krawędź `condition="error"` = komunikat z `error=True`. Powiadomienie = `async=True`. Klucz `seq:main`. |
| `rules` | `name`, `inputs: list[str]`, `rows: list[{condition, result}]` | Jedna tabela na bramkę XOR (`decision`, nie `parallel`): wiersz = etykieta krawędzi → tytuł celu. `inputs` = wejścia kroku bramki. Klucz `rule:<node_key>`. |
| `vision` (obiekt, nie lista) | `problem`, `goals`, `metrics`, `must`, `should`, `could`, `wont` (listy tekstów) + `manual: list[str]` (nazwy pól poprawionych ręcznie) | Szkic: `problem` = zdanie startowe, `must` = nazwy ekranów, `could` = powiadomienia. Pole z `manual` nigdy nie jest nadpisywane przy odświeżeniu. |

Klasy/ERD (`entities`) i stany (`states`) już są w `Spec` — tylko je rysujemy. C4 i macierz śledzenia są liczone
na bieżąco (nic do ręcznej poprawy, więc nic nie zapisujemy).

## Moduł `app/design/`

- `uml.py` — czyste funkcje `Spec` (+ graf) → tekst Mermaid:
  - klasy: `classDiagram` (pola z typami, krotności z `Relation.kind`);
  - przypadki użycia: `flowchart LR` (aktorzy jako węzły-ludziki, granica systemu jako `subgraph`, `<<include>>`
    i `<<extend>>` na krawędziach) — Mermaid nie ma natywnego diagramu UC;
  - sekwencje: `sequenceDiagram` (`->>` synchroniczne, `-)` asynchroniczne, błąd w bloku `alt`);
  - stany: `stateDiagram-v2` z warunkami bramek na przejściach;
  - C4: `C4Context` (role = osoby, system = FlowMap-projekt, integracje = systemy zewnętrzne).
  Tekst użytkownika przechodzi przez istniejące `_mm` (ucieczka znaków Mermaid).
- `lint.py` — strażnik UML; zwraca listę `{code, message, target_key, why}` w formacie `readiness()`. Jego uwagi
  obniżają wynik gotowości (wagi w `WEIGHTS`) i trafiają do `OPEN_QUESTIONS.md`. `why` = jedno zdanie wyjaśnienia
  dla uczącego się.
- `trace.py` — macierz śledzenia: krok → ekran / automatyzacja → scenariusz testu (z `_test_paths`).

### Reguły strażnika (MVP)

| Obszar | Kod | Kiedy |
|---|---|---|
| Klasy | `nn_without_join` | relacja `n-n` bez encji łączącej |
| Klasy | `island_entity` | encja bez żadnej relacji (gdy encji > 1) |
| Klasy | `reference_without_relation` | pole „odwołanie” bez relacji do tej encji |
| Przypadki użycia | `role_without_use_case` | rola (poza Administratorem) bez przypadku użycia |
| Przypadki użycia | `use_case_without_goal` | pusty `goal` |
| Przypadki użycia | `gateway_without_alternative` | bramka w ciągu aktora, a brak scenariusza alternatywnego |
| Sekwencje | `integration_without_error_message` | komunikat do integracji bez komunikatu błędu |
| Sekwencje | `idle_participant` | uczestnik bez komunikatów |
| Stany | `unreachable_status` | status nieosiągalny ze stanu początkowego |
| Stany | `dead_end_status` | status bez wyjścia, który nie jest końcowy |
| Reguły | `rule_gap` | brak wiersza „w przeciwnym razie” / „inaczej” |
| Reguły | `rule_overlap` | dwa wiersze o tym samym warunku |
| Śledzenie | `screen_without_test` | ekran, którego krok nie występuje w żadnym scenariuszu testu |
| Śledzenie | `step_without_screen` | krok czynności bez ekranu i bez automatyzacji |

## Interfejs

- Karta „Projekt aplikacji” (`/p/<id>/projekt-aplikacji`) obok „Specyfikacji”; sekcje: Wizja i MVP, Przypadki
  użycia, Klasy, Sekwencje, Stany, Reguły, C4, Śledzenie.
- Sekcja: lista + formularze po lewej, podgląd Mermaid po prawej; na 390 px podgląd pod listą. Uwagi strażnika
  przy elemencie, z rozwijanym „dlaczego”.
- Mermaid w `app/static/vendor/mermaid.min.js` (CSP: `script-src 'self'`; `style-src 'unsafe-inline'` już jest),
  ładowany tylko na tej karcie; ponowne rysowanie po `htmx:afterSwap`; motyw Mermaid wg `data-theme`.
- Słownictwo z objaśnieniem w tooltipie (np. „Przypadek użycia (use case)”, „include”, „krotność”).
- Edycja nowych sekcji przez istniejące trasy `app/spec/routes.py` (formularz, zapis, „zachowaj”, „usuń”) —
  rozszerzamy `forms.py` o nowe typy; nowa trasa tylko dla widoku karty i dla wizji.

## Paczka ZIP

- `UML.md` — wszystkie diagramy z krótkim opisem i uwagami strażnika.
- `VISION.md` — problem, cele, mierniki, MoSCoW.
- `CLAUDE.md` — „Kolejność budowy” odsyła do `VISION.md` (zakres) i `UML.md` (przypadki użycia = ekrany, sekwencje
  = integracje); `ACCEPTANCE.md` dostaje macierz śledzenia.

## AI

Przycisk „Uzupełnij z AI” przy wizji, scenariuszach alternatywnych i opisach reguł — przez istniejący mechanizm
propozycji (`app/spec/review.py`: propozycja → akceptuj/odrzuć), Opus 5.5, dzienny limit `spend_ai_request`.
Bez klucza API przycisk jest ukryty. Zaakceptowana propozycja dostaje `source="ai"`.

## Kolejność PR-ów

1. Mermaid w `vendor/`, karta „Projekt aplikacji”, diagram klas z istniejących encji + strażnik klas.
2. Przypadki użycia (schemat, wyliczanie, formularz, diagram, strażnik) + `UML.md` w ZIP.
3. Sekwencje (z integracjami i błędami) + strażnik.
4. Stany z warunkami + tabele decyzyjne z bramek + strażnik.
5. C4 kontekst + macierz śledzenia (`trace.py`, `ACCEPTANCE.md`) + strażnik.
6. Wizja i MVP (formularz, „Uzupełnij z AI”) + `VISION.md`.

## Testy i dowóz

Każdy PR: testy jednostkowe wyliczania, Mermaid i strażnika na szablonach `full_graph(...)`; test trasy i uprawnień
(widz widzi, obcy 404, edytor zapisuje); test scalania (ręczna poprawka przetrwa zmianę mapy); ruff; Playwright —
oba motywy, 1440 i 390 px, 0 błędów JS, Mermaid wyrysował `<svg>` bez „Syntax error”; PR → zielone CI → merge →
wdrożenie Coolify → sprawdzenie na produkcji po nowej trasie.

## Poza zakresem (YAGNI)

Eksport XMI/PlantUML, rysowanie diagramów myszką, osobne wersjonowanie diagramów (pokrywają je wersje mapy),
ćwiczenia z porównaniem (podprojekt 3).
