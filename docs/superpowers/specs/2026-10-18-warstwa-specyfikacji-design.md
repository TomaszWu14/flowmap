# Warstwa specyfikacji i paczka dla Claude Code — projekt

Data: 2026-10-18 · Status: zatwierdzony w rozmowie, czeka na przegląd dokumentu · Podprojekt 1 z 2

## 1. Kontekst i cel

**Kto:** analityk biznesowy i programista (freelancer). **Cykl pracy:** szkic samodzielnie → weryfikacja
z klientem (na żywo albo przez link) → akceptacja → przekazanie do realizacji.
**Najważniejszy rezultat:** gotowe, techniczne wejście dla **Claude Code** (agenta w repozytorium).
**AI:** oszczędnie — w kilku kluczowych momentach; tryb bez AI zostaje.

**Problem:** mapa opisuje *proces*, a agent potrzebuje *techniki*: typów pól, encji i relacji, uprawnień,
stanów, powiadomień. Dziś eksport wyczytuje to z mapy szczątkowo (model danych = lista pól wg aktora).

**Cel podprojektu 1:** dodać do projektu edytowalną **warstwę specyfikacji** wyprowadzaną z mapy regułami,
uzupełnianą jednym przeglądem AI (propozycje do zatwierdzenia) i ręcznie, oraz eksport **paczki dla
Claude Code** (ZIP z plikami Markdown dla repozytorium).

**Podprojekt 2 (osobny dokument, później):** cykl z klientem — etapy projektu (Szkic → Weryfikacja →
Akceptacja → Przekazanie), komentarze bez konta przez link (podpis imieniem), „Akceptuję wersję” zapisujące
wersję, datę i imię. Korzysta z podprojektu 1: akceptuje się wersję mapy **i** specyfikacji.

**Kryteria sukcesu:**
- Dla mapy z każdego z 3 wbudowanych szablonów reguły dają specyfikację z gotowością ≥ 70 bez AI.
- Ręczna zmiana elementu specyfikacji nigdy nie znika po zmianie mapy ani po przeglądzie AI.
- Paczka jest deterministyczna (ta sama specyfikacja → identyczne bajty) i zawiera komplet plików z §6.
- Przegląd AI to dokładnie 1 wywołanie API i 1 zapytanie z dziennego limitu użytkownika.

## 2. Dokument specyfikacji

Jeden dokument JSON na projekt w kolumnie `Project.spec`, walidowany modelami Pydantic (`app/spec/schema.py`).
Uzasadnienie: zawsze czytany i zapisywany w całości; wchodzi do migawki `Version` (cofnij/ponów, historia,
porównanie i późniejsza akceptacja działają bez dodatkowej pracy); prosty eksport/import.

### 2.1 Wspólne pola elementu

Każdy element każdej sekcji ma:
- `key` — stabilny identyfikator (z mapy: wyprowadzony deterministycznie, np. `entity:rezerwacja`,
  `screen:<node_key>`; ręczny: losowy krótki hex),
- `source` — `rules` | `ai` | `manual`,
- `stale` — `true`, gdy element z reguł nie ma już odpowiednika w mapie,
- `node_key` — opcjonalnie: krok mapy, z którego element pochodzi.

### 2.2 Sekcje

| Sekcja | Element | Pola |
|---|---|---|
| `entities` | encja | `name`, `description`, `fields[]`, `relations[]` |
| — `fields[]` | pole | `name`, `type`, `required`, `validation`, `enum_values[]`, `ref_entity` (klucz encji dla typu `reference`), `is_identifier` |
| — `relations[]` | relacja | `to_entity`, `kind` (`1-1` \| `1-n` \| `n-n`), `label` |
| `screens` | ekran | `name`, `node_key`, `role`, `fields[]` (`ref`: `encja.pole` albo `name`+`type` pola tylko na ekranie), `actions[]` |
| `roles` | rola | `name`, `description`, `permissions` = {klucz encji: {`read`,`create`,`update`,`delete`} ∈ `all` \| `own` \| `none`} |
| `states` | maszyna stanów | `entity`, `statuses[]` (`name`, `initial`, `final`), `transitions[]` (`from`, `to`, `node_key`, `role`) |
| `notifications` | powiadomienie | `trigger` (`node_key` albo przejście statusu), `channel` (`email` \| `sms` \| `push` \| `in_app`), `recipient_role`, `summary` |
| `integrations` | integracja | `name`, `node_key`, `direction` (`out` \| `in` \| `both`), `data[]`, `on_error` |
| `nfr` | wymaganie | `category` (`security` \| `performance` \| `privacy` \| `accessibility` \| `other`), `text` |
| `stack` | — | jeden tekst, np. „Flask + PostgreSQL”; może być pusty |
| `proposals` | propozycja AI | patrz §4.2 |

### 2.3 Typy pól (zamknięta lista)

`text`, `long_text`, `integer`, `decimal`, `money`, `boolean`, `date`, `datetime`, `email`, `phone`, `enum`,
`file`, `reference`. Etykiety po polsku w UI (tekst, długi tekst, liczba całkowita, …).

## 3. Wyprowadzanie z mapy (reguły) — `app/spec/derive.py`

Czysta funkcja `derive(graph, meta) -> Spec`, bez bazy i bez AI:

- **Encja główna:** nazwa z rzeczownika zdania startowego/nazwy projektu (np. „Rezerwacja”, „Zamówienie”,
  „Zgłoszenie”; gdy brak — nazwa projektu); pole `id` (identyfikator), `utworzono` (datetime), `status` (enum,
  gdy powstają statusy).
- **Encje osób:** dla każdego aktora-człowieka z polami wejściowymi — encja nazwana rolą (np. „Klient”) z tymi
  polami; relacja `Klient 1-n <encja główna>`.
- **Typ pola z nazwy:** e-mail → `email`; telefon → `phone`; data → `date`; godzina/termin z godziną →
  `datetime`; kwota/cena/koszt/suma → `money`; ilość/liczba → `integer`; zgoda/akceptacja → `boolean`;
  plik/zdjęcie/załącznik → `file`; opis/uwagi → `long_text`; nazwa innej encji → `reference`; reszta `text`.
- **Ekrany:** każdy krok typu `screen` → ekran; rola = aktor kroku; pola z `inputs` i `outputs`.
- **Role:** unikalni aktorzy bez „System”. Uprawnienia domyślne: **aktor kroku startowego** (inicjator
  procesu, np. Klient) → `own` dla `read`/`create`/`update` i `none` dla `delete` na encji głównej i swojej
  encji osoby; **każda inna rola-człowiek** (obsługa, np. Pracownik, Serwisant) → `all` dla `read`/`update`,
  `none` dla `create`/`delete` na encji głównej. Zawsze dodawana rola **Administrator** z `all` na wszystkim.
- **Statusy encji głównej:** `nowy` (początkowy) → status po każdej automatyzacji/decyzji wg ścieżki
  (decyzja: gałąź pozytywna → `zatwierdzony`, negatywna → `odrzucony`), krok `end` → status końcowy
  (nazwa z tytułu kroku, np. „odbyta”); przejścia przypięte do `node_key`.
- **Integracje:** kroki `integration`; `on_error` z etykiety/celu ścieżki błędu (jeśli jest).
- **Powiadomienia:** kroki `automation` z „wysłanie/powiadomienie/SMS/e-mail/przypomnienie” w tytule; kanał
  z tytułu (SMS → `sms`, inaczej `email`); odbiorca = najbliższy wcześniejszy aktor-człowiek.
- **NFR domyślne:** HTTPS; kopie zapasowe; przy polach osobowych (imię/nazwisko/e-mail/telefon/adres) —
  RODO (podstawa przetwarzania, usunięcie danych na żądanie).

## 4. Scalanie i AI

### 4.1 Scalanie — `app/spec/merge.py`

Czysta funkcja `merge(current, derived) -> Spec`, wywoływana **po każdej zmianie mapy** (w tym samym zapisie,
przed migawką `Version`):
- element `rules` w `current`, który nie był edytowany → zastąpiony wersją z `derived`,
- element z `derived`, którego brak w `current` → dodany,
- element `rules` w `current` bez odpowiednika w `derived` → `stale = true` (nie znika),
- element `manual` albo `ai` → nigdy nie zmieniany automatycznie,
- edycja elementu przez użytkownika ustawia `source = "manual"`.

### 4.2 Przegląd techniczny AI — `app/spec/review.py`

- Przycisk „Przegląd techniczny AI” (rola edytor+). Jedno wywołanie (tool use `strict`, `tool_choice: auto`,
  prompt w `app/prompts/spec_review.md`), wejście: mapa (jak dziś, bez danych konta) + specyfikacja.
- Wynik: lista **propozycji** `{id, kind, target_key, summary, patch}`; `kind` ∈ `set_field_type`,
  `add_field`, `add_relation`, `add_status`, `add_transition`, `set_permission`, `add_notification`,
  `add_nfr`, `other_note`. `patch` walidowany per `kind`.
- Propozycje trafiają do `spec.proposals` (panel „Do zatwierdzenia”). Zatwierdź = zastosuj patch, element
  dostaje `source = "ai"`; Odrzuć = usuń propozycję; „Zatwierdź wszystkie”.
- Propozycja, której `target_key` już nie istnieje → oznaczona „nieaktualna”, nie da się jej zatwierdzić.
- Błąd walidacji → 1 ponowienie; błąd API/limit/timeout → komunikat, specyfikacja bez zmian.
- Licznik: 1 zapytanie z dziennego limitu (jak dziś `consume_ai_request`).

## 5. Wskaźnik gotowości — `app/spec/readiness.py`

Czysta funkcja `readiness(spec) -> {score, issues[]}`; każdy problem ma `code`, `message`, `target_key`.
Reguły (wagi w nawiasie): encja bez pola identyfikującego (10); pole bez typu albo `enum` bez wartości (3);
relacja/`reference` do nieistniejącej encji (8); ekran bez roli (5); rola bez żadnych uprawnień (5);
maszyna stanów bez stanu początkowego albo końcowego (8); powiadomienie bez odbiorcy (3); integracja bez
`on_error` (5); element `stale` (2); otwarta propozycja AI (1). Wynik `max(0, 100 − Σ wag)`.

## 6. Paczka dla Claude Code — `app/spec/package.py`

ZIP do rozpakowania w `docs/flowmap/` repozytorium. Generatory deterministyczne (stała kolejność, stała data
wpisów ZIP), bez AI.

| Plik | Zawartość |
|---|---|
| `CLAUDE.md` | kontekst, stos; **kolejność budowy**: model danych → logowanie i role → ekrany w kolejności procesu → statusy → powiadomienia i integracje za interfejsem z atrapą → testy; Definition of Done; zasada „nie wymyślaj poza specyfikacją, wątpliwości do `OPEN_QUESTIONS.md`”; tabela odwzorowania typów na stos, gdy `stack` podany |
| `SPEC.md` | opis procesu; macierz ról × encji × CRUD; ekrany z polami i akcjami; diagram procesu (Mermaid `flowchart`); powiadomienia; integracje; NFR |
| `DATA_MODEL.md` | encje i pola (tabele: typ, wymagane, walidacja); relacje; Mermaid `erDiagram`; maszyny stanów Mermaid `stateDiagram-v2` |
| `ACCEPTANCE.md` | kryteria akceptacji per ekran i rola; scenariusze Zakładając/Gdy/Wtedy ze ścieżek mapy (także ścieżki błędów) |
| `OPEN_QUESTIONS.md` | problemy strażnika mapy + wskaźnika gotowości + otwarte komentarze |
| `flowmap.json` | mapa + specyfikacja (format `flowmap/2`, import zgodny wstecz z `flowmap/1`) |

Na stronie Eksport: sekcja „Paczka dla Claude Code” na górze, przycisk pobrania, gotowość, ostrzeżenie przy
gotowości < 80 (eksport nie jest blokowany) i **polecenie do wklejenia** z przyciskiem „Kopiuj”.
Dotychczasowe eksporty zostają; „Specyfikacja (Markdown)” korzysta z warstwy specyfikacji, gdy istnieje.

## 7. Interfejs — zakładka „Specyfikacja”

- Przełącznik **Mapa | Specyfikacja** przy tytule projektu; trasa `/p/<id>/specyfikacja`.
- Pasek: gotowość 0–100, „Odśwież z mapy”, „Przegląd techniczny AI” (gdy AI włączone), „Do zatwierdzenia: n”.
- Lewa kolumna: sekcje z licznikami (na telefonie zakładki u góry). Prawa: karty elementów w trybie odczytu;
  „Edytuj” otwiera formularz w miejscu (HTMX). Pola encji edytowane w tabelce wierszy (nazwa, typ, wymagane,
  walidacja, wartości wyboru, odwołanie).
- Problemy gotowości jako ⚠ na kartach. Elementy `stale` wyszarzone z „Usuń” / „Zachowaj jako ręczny”.
- Link „pokaż na mapie” przy elementach z `node_key`; w panelu kroku mapy link „specyfikacja tego kroku”.
- Uprawnienia jak dla mapy: `project_for(id, "view")` do oglądania, `"edit"` do zmian i przeglądu AI.
- Treść użytkownika i AI escapowana (Jinja), w Markdown/Mermaid jak dziś (`_md`, `_mm`).

## 8. Zmiany w istniejącym kodzie

- `Project.spec` (JSON, nullable) + migracja.
- `flow/graph.py`: `save_version` zapisuje w migawce `{"graph": …, "spec": …}`; `load_graph`/historia
  odtwarzają oba; stare migawki (sam graf) czytane wstecznie.
- Po każdej mutacji mapy: `project.spec = merge(spec, derive(graph))` przed `save_version` (jedno miejsce:
  helper w `flow/graph.py`, wołany z `_changed`, cofnij/ponów odtwarzają specyfikację z migawki).
- Eksport/import JSON: pole `spec`, format `flowmap/2`.
- `flow/diff.py`: porównanie wersji pokazuje też liczbę zmian w specyfikacji (encje/pola/role dodane, usunięte).

## 9. Obsługa błędów

- Uszkodzony/niezgodny dokument w bazie → komunikat i przycisk „Odbuduj z mapy” (zamiast 500); ręczne elementy,
  które przejdą walidację pojedynczo, są zachowywane.
- Błąd AI/limit/timeout → komunikat, brak zmian.
- Nieaktualna propozycja → nie do zatwierdzenia, opis dlaczego.
- Edycja z nieprawidłowymi danymi (np. `reference` do nieistniejącej encji) → błąd przy polu, brak zapisu.

## 10. Testy

- Jednostkowe: `derive` (3 szablony, mapa z dokumentu, mapa ogólna), `merge` (ochrona `manual`/`ai`,
  `stale`, idempotentność), `readiness` (każda reguła), walidacja `schema`.
- Paczka: komplet plików, sekcje, poprawność składni Mermaid (proste parsowanie nagłówków i krawędzi),
  deterministyczność (dwa eksporty = te same bajty), escapowanie treści użytkownika.
- AI (atrapa SDK): poprawne propozycje, błędne → ponowienie → komunikat, limit; zatwierdzanie/odrzucanie,
  nieaktualna propozycja.
- Uprawnienia: właściciel/edytor/podgląd/obcy.
- Integracja: zmiana mapy aktualizuje specyfikację, ręczna zmiana przetrwa zmianę mapy; cofnij/ponów
  i porównanie wersji obejmują specyfikację; import `flowmap/1` i `flowmap/2`.
- Na koniec: przejście ścieżki w przeglądarce (desktop i 390 px).

## 11. Wdrażanie — 4 PR-y (każdy na produkcję osobno)

1. `schema`, `derive`, `merge`, kolumna i migracja, aktualizacja po zmianie mapy, specyfikacja w wersjach
   i JSON; zakładka tylko do odczytu.
2. Edycja w zakładce, wskaźnik gotowości, ⚠ i elementy nieaktualne.
3. Paczka ZIP dla Claude Code + polecenie do wklejenia; „Specyfikacja (Markdown)” z warstwy specyfikacji.
4. Przegląd techniczny AI i panel „Do zatwierdzenia”.

## 12. Poza zakresem

Generowanie kodu w FlowMap; dobór konkretnych bibliotek per pole; szacowanie pracochłonności i wycena;
cykl z klientem (podprojekt 2).
