"""Polish plurals for UI text."""


def plural_word(n: int, one: str, few: str, many: str) -> str:
    """1 krok, 2-4 kroki (but 12-14 kroków), 0 and 5+ kroków."""
    if n == 1:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many


def plural(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {plural_word(n, one, few, many)}"


def steps_label(n: int) -> str:
    return plural(n, "krok", "kroki", "kroków")
