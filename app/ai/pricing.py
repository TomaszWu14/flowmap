"""Anthropic list prices (USD per million tokens, standard tier) for the cost log; update when prices change."""

PRICES = {  # model: (input, output) — platform.claude.com/docs/en/about-claude/pricing, 2026-10-20
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

FEATURES = {
    "propose_next_steps": "Propozycje kroków", "report_missing_steps": "Przegląd mapy",
    "complete_open_branches": "Uzupełnianie gałęzi", "draft_process_map": "Mapa z dokumentu",
    "propose_spec_changes": "Przegląd specyfikacji", "draft_vision": "Wizja aplikacji",
    "assess_quality": "Ocena AI projektu", "grade_exercise": "Ocena ćwiczenia",
    "recruit_questions": "Pytania rekrutera", "recruit_report": "Raport rekrutera", "trainer_chat": "Czat trenera",
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    return None if price is None else (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
