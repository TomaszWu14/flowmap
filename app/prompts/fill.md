Proces: „{start_sentence}”

Mapa procesu (JSON):
{graph_json}

Otwarte miejsca na mapie — po tych krokach brakuje dalszego ciągu (`slot` to etykieta gałęzi decyzji,
pusty `slot` oznacza zwykłe „co dalej”):
{slots}

Dokończ mapę jak doświadczony analityk. Dla KAŻDEGO otwartego miejsca zaproponuj 1–4 kroki, które je domykają:
kończą się krokiem typu `end` albo decyzją, której gałęzie zostaną kolejnymi pytaniami. Trzymaj się ról i słownictwa
z mapy, nie powtarzaj kroków, które już są na ścieżce. Ścieżki negatywne („nie”, „błąd”, „odrzucono”) domykaj
komunikatem dla użytkownika i końcem. `node_key` i `slot` przepisz dokładnie z listy. `summary` to jedno zdanie po polsku.

Wywołaj narzędzie `complete_open_branches`.
