import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def test_map_js_defines_every_local_helper_it_calls():
    # Regression: a refactor once deleted openNode() while the tap handler still called it,
    # so clicking a step stopped opening its panel (no Python test could notice).
    src = (STATIC / "map.js").read_text(encoding="utf-8")
    for name in ("openNode", "load", "elements", "style", "placeNew", "updateChrome", "iconUri", "inView"):
        if re.search(rf"\b{name}\(", src):
            assert re.search(rf"function {name}\(", src), f"{name}() is called in map.js but never defined"


def test_player_js_defines_its_helpers():
    src = (STATIC / "player.js").read_text(encoding="utf-8")
    for name in ("place", "focus", "render", "travel", "advance", "start", "close"):
        assert re.search(rf"function {name}\(", src), name


def test_design_js_defines_its_helpers():
    src = (STATIC / "design.js").read_text(encoding="utf-8")
    for name in ("render", "theme"):
        assert re.search(rf"function {name}\(", src), name
