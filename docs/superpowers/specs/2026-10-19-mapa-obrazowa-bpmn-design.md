# Mapa obrazowa BPMN — projekt

Data: 2026-10-19 · Status: zatwierdzony w rozmowie · Podprojekt 1 z 4

## Kierunek (mapa drogowa)

FlowMap ma być trenażerem analityka na poziomie korporacyjnym (praca w dużej firmie + rekrutacje) i narzędziem
do realnych map procesów oraz projektowania aplikacji od zera. Ustalenia z rozmowy:

- notacje: najpierw BPMN 2.0, potem UML;
- trener w dwóch trybach: **Nauka** (pyta jak doświadczony analityk, podpowiada dopiero gdy utkniesz, ocenia mapę)
  i **Praca** (szybkie propozycje, jak dziś);
- AI: Claude — Sonnet 5 do rozmowy, Opus 5.5 do oceny i trudnych pytań, z dziennym limitem;
- ćwiczenia: klasyki korporacyjne (P2P, O2C, reklamacje, onboarding, incydenty IT, urlopy) + ścieżka logistyki.

Podprojekty (w tej kolejności):

1. **Mapa obrazowa BPMN** — ten dokument.
2. **Projekt aplikacji z mapy** — wizja i zakres MVP, UML (przypadki użycia, klasy/ERD, sekwencje, stany),
   C4 kontekst, reguły biznesowe, bogatsza paczka dla Claude Code (dane w dużej części są już w warstwie specyfikacji).
3. **Trener** (Nauka/Praca) dla ścieżki procesowej i projektowej.
4. **Program, ćwiczenia, postęp, portfolio, tryb rekrutacyjny.**

## Podprojekt 1: mapa obrazowa BPMN

Cel: z samego spojrzenia widać, co się dzieje w kroku i na którym stanowisku, a mapa jest zgodna z BPMN 2.0.

### Część 1 — piktogramy czynności (PR 1)

- `app/flow/pictograms.py`: katalog ok. 25 piktogramów (klucz → polska nazwa, element BPMN), reguły słów kluczowych
  z polskimi rdzeniami (pierwsze dopasowanie wygrywa, od szczegółowych do ogólnych), domyślna ikona dla typu kroku.
  Bramki nie mają ikony (mówią kształtem), start i koniec zawsze mają ikonę zdarzenia.
- Ręczna zmiana w „Edytuj krok” (siatka ikon + „Auto”) → `node.data["icon"]`, ma pierwszeństwo przed automatem.
- Ikony Lucide (ISC) w `app/static/icons.json`; mapa barwi je kolorem typu/roli, w obu motywach. Ikona także
  w panelu kroku, dymku i karcie odtwarzania. Emoji w etykietach usunięte (bez czcionki emoji były pustymi kwadratami).
- Piktogram wyznacza typ zadania BPMN w eksporcie (koperta = `sendTask`, klawiatura = `userTask`, …) — w części 4.

### Część 2 — tory stanowisk pracy (PR 2)

- Widok „tory”: poziome pasy na role, nagłówek z ikoną stanowiska i nazwą; kroki od lewej do prawej, każdy w pasie
  swojej roli; przekazania między stanowiskami widać jako strzałki między pasami.
- Przełącznik „Widok: przepływ ⇄ tory” (zapamiętywany; przy ≥ 2 rolach domyślnie tory).
- Ikona stanowiska z nazwy roli (magazyn, transport, klient, system, biuro), zmiana klikiem w nagłówek; kolejność
  pasów według pierwszego wystąpienia, zmiana ↑↓; zapis w nowym polu JSON projektu.
- Pas „Bez przypisanej roli”; liczba przekazań między stanowiskami w strażniku/podsumowaniu.
- Działa: panel kroku, budowanie pytaniami, odtwarzanie, szukanie, dymek, pełny ekran, udostępnianie, Przykład.
- Technicznie: złożone węzły Cytoscape (pasy) o równej szerokości, kolejność kroków z dagre LR.
- Opcja na później: klient i systemy zewnętrzne jako osobne pule z przepływem wiadomości.

### Część 3 — bramka równoległa AND (PR 3)

- Nowy typ „Bramka AND (równolegle)” (romb z „+”): rozgałęzienie i zbieganie ścieżek.
- Pytania: nazwy ścieżek → otwarte gałęzie; kafelek „Zbiegnij ścieżki” dodaje bramkę łączącą.
- Strażnik: < 2 wyjścia; ścieżki równoległe, które się nie łączą.
- Symulacja i odtwarzanie przechodzą wszystkie ścieżki („ścieżka równoległa 1 z 2”) i czekają na bramce łączącej.

### Część 4 — eksport BPMN i słownictwo (PR 4)

- Eksport BPMN 2.0: `laneSet` z torami, typy zadań z piktogramu (`userTask`, `serviceTask`, `sendTask`,
  `receiveTask`, `manualTask`), bramki XOR/AND, zdarzenia czasowe i wiadomości, współrzędne DI z widoku torów —
  plik otwiera się w Camunda Modeler / bpmn.io.
- Słownictwo BPMN w UI z objaśnieniem: Zadanie użytkownika, Zadanie systemowe, Zdarzenie czasowe, Bramka XOR
  (decyzja), Bramka AND, Zdarzenie startowe/końcowe.
- Test parsuje XML i sprawdza odwołania; jednorazowa ręczna kontrola pliku w bpmn.io.

## Testy i dowóz

Każda część to osobny PR: testy jednostkowe i tras, przejście Playwright (jasny i ciemny motyw, 1440 i 390 px),
CI (ruff + pytest), merge, wdrożenie przez API Coolify.
