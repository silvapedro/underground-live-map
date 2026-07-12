from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_textual_rows(data_file: Path) -> list[dict[str, Any]]:
    if not data_file.exists():
        return []
    with data_file.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def group_rows_by_line(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    current_line = ""
    current_items: list[dict[str, Any]] = []

    for row in rows:
        line = str(row.get("line", "")).strip() or "Unknown"
        if line != current_line:
            if current_items:
                grouped.append({"line": current_line, "items": current_items})
            current_line = line
            current_items = []

        time_seconds = row.get("time")
        minutes: float | None = None
        if isinstance(time_seconds, (int, float)):
            minutes = float(time_seconds) / 60.0

        current_items.append(
            {
                "current": str(row.get("current", "")).strip(),
                "minutes": minutes,
            }
        )

    if current_items:
        grouped.append({"line": current_line, "items": current_items})

    return grouped
