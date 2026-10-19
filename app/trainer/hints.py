"""Learning mode: hints revealed step by step (guiding question → one tile → all tiles). No AI needed."""

HINT_LEVELS = 3
GUIDES = {
    "next": "Co realnie dzieje się zaraz po kroku „{title}”{slot}? Kto wykonuje następną czynność i co musi mieć, "
            "żeby ją wykonać?",
    "actor": "Kto w firmie odpowiada za krok „{title}”? Pomyśl o stanowisku, nie o konkretnej osobie — "
             "kto by to robił, gdyby jutro przyszedł nowy pracownik?",
    "screen": "Co użytkownik musi zobaczyć na ekranie „{title}”, żeby podjąć decyzję albo przejść dalej?",
    "data": "Jakie dane trzeba zebrać lub zapisać w kroku „{title}”? Co byłoby potrzebne później w procesie?",
    "error": "Co może pójść nie tak w kroku „{title}”? Kto się o tym dowiaduje i co dzieje się z procesem?",
    "branches": "Jakie są możliwe wyniki decyzji „{title}”? Czy obejmują wszystkie przypadki, także „inne”?",
}


def guide_text(kind: str, node_title: str, slot: str | None) -> str:
    slot_part = f" przy odpowiedzi „{slot}”" if slot else ""
    return GUIDES.get(kind, GUIDES["next"]).format(title=node_title, slot=slot_part)


def visible_options(options: list, learning: bool, level: int) -> list:
    if not learning or level >= HINT_LEVELS:
        return list(options)
    return list(options[:1]) if level == 2 else []
