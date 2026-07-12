from pyapp.services.textual import group_rows_by_line


def test_group_rows_by_line_groups_contiguous_rows():
    rows = [
        {"line": "Central", "current": "One", "time": 60},
        {"line": "Central", "current": "Two", "time": 90},
        {"line": "District", "current": "Three", "time": 120},
        {"line": "", "current": "Four"},
    ]

    assert group_rows_by_line(rows) == [
        {
            "line": "Central",
            "items": [
                {"current": "One", "minutes": 1.0},
                {"current": "Two", "minutes": 1.5},
            ],
        },
        {
            "line": "District",
            "items": [{"current": "Three", "minutes": 2.0}],
        },
        {
            "line": "Unknown",
            "items": [{"current": "Four", "minutes": None}],
        },
    ]