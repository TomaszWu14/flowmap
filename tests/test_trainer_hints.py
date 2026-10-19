from app.trainer.hints import guide_text, visible_options


def test_visible_options_by_mode_and_level():
    opts = ["a", "b", "c"]
    assert visible_options(opts, learning=False, level=0) == opts
    assert visible_options(opts, learning=True, level=0) == []
    assert visible_options(opts, learning=True, level=1) == []
    assert visible_options(opts, learning=True, level=2) == ["a"]
    assert visible_options(opts, learning=True, level=3) == opts


def test_guide_text_per_question_kind():
    assert "Płatność online" in guide_text("error", "Płatność online", None)
    assert "„nie”" in guide_text("next", "Czy termin jest wolny?", "nie")
    for kind in ("next", "actor", "screen", "data", "error", "branches"):
        assert guide_text(kind, "Krok", None).endswith("?")
