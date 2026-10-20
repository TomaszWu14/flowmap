from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "app" / "prompts"


def test_ai_texts_use_step_titles_not_internal_ids():
    # real Opus/Sonnet answers leaked step keys and English type names ("accept", "automation") into user texts
    for name in ("system.md", "trainer.md"):
        assert "Nigdy nie pokazuj kluczy kroków" in (PROMPTS / name).read_text(encoding="utf-8"), name
