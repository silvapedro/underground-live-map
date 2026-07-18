import json
from pathlib import Path

import fetch

LINE_COLORS_PATH = Path(__file__).resolve().parent.parent / "src" / "data" / "line-colors.json"


def _load():
    return json.loads(LINE_COLORS_PATH.read_text(encoding="utf-8"))


def test_covers_exactly_the_lines_fetch_py_produces():
    """A line added to/removed from fetch.py's LINES dict without a matching update
    here would silently render trains with no colour (or a stale one) on the map."""
    colors = _load()
    assert set(colors) == set(fetch.LINES)


def test_every_value_is_a_hex_colour():
    colors = _load()
    for line_id, value in colors.items():
        assert isinstance(value, str) and len(value) == 7 and value[0] == "#", (
            f"{line_id!r} has a non-hex value: {value!r}"
        )
        int(value[1:], 16)  # raises ValueError if not valid hex digits
