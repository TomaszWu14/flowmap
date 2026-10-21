from datetime import datetime

from app.text import local_time


def test_naive_utc_shown_in_polish_time_winter_and_summer():
    assert local_time(datetime(2026, 1, 15, 23, 30)) == "16.01.2026 00:30"  # CET, +1, crosses midnight
    assert local_time(datetime(2026, 7, 1, 10, 0), "%H:%M") == "12:00"  # CEST, +2


def test_filter_registered_in_templates(app):
    assert app.jinja_env.filters["local"] is local_time
