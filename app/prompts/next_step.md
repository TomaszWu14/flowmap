Proces: „{start_sentence}”
Tryb: {mode_description}

Aktualna mapa (JSON):
{graph_json}

Pytamy o krok `{node_key}` „{node_title}” (typ: {node_type}){slot_text}.

Zaproponuj 3–5 różnych, realistycznych odpowiedzi na pytanie „co dzieje się dalej?”.
- Każda opcja to 1–{max_steps} kolejnych kroków w kolejności. Decyzja (decision) lub koniec (end) może być
  tylko ostatnim krokiem opcji.
- Jeśli proces wraca do istniejącego kroku (pętla), ustaw `connect_to_key` na jego klucz, inaczej pusty tekst.
- Uwzględnij wyjątki, jeśli pasują (błąd płatności, brak danych, odrzucenie).
- Nie powtarzaj kroków, które już są na mapie (zamiast tego użyj `connect_to_key`).

Wywołaj narzędzie `propose_next_steps`.
