from datetime import UTC, date, datetime

import pytest

from src.playlist.weekly import (
    _derive_weekly_prefix,
    _find_weekly_playlists,
    _parse_week_date_from_title,
    _parse_week_start,
    _prune_old_weeklies,
    _start_of_week,
    _weekly_playlist_name,
)


class _FakeYTM:
    def __init__(self, playlists):
        self._playlists = playlists

    def get_library_playlists(self, limit=1000):  # noqa: ARG002
        return self._playlists


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("MON", 0),
        ("tue", 1),
        ("Wed", 2),
        ("THU", 3),
        ("FRI", 4),
        ("SAT", 5),
        ("SUN", 6),
        ("garbage", 0),
        (3, 3),
        (99, 0),
        (-1, 0),
    ],
)
def test_parse_week_start(value, expected):
    assert _parse_week_start(value) == expected


def test_start_of_week_monday():
    dt = datetime(2024, 1, 10, 15, 30, tzinfo=UTC)
    sow = _start_of_week(dt, week_start=0)
    assert sow.date() == date(2024, 1, 8)
    assert (sow.hour, sow.minute, sow.second) == (0, 0, 0)


def test_start_of_week_sunday():
    dt = datetime(2024, 1, 10, tzinfo=UTC)
    sow = _start_of_week(dt, week_start=6)
    assert sow.date() == date(2024, 1, 7)


def test_start_of_week_when_already_start_day():
    dt = datetime(2024, 1, 8, 12, tzinfo=UTC)
    assert _start_of_week(dt, week_start=0).date() == date(2024, 1, 8)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("My Mix (auto)", "My Mix"),
        ("My Mix(auto)", "My Mix"),
        ("My Mix", "My Mix"),
        ("  Padded (auto)  ", "Padded"),
    ],
)
def test_derive_weekly_prefix(name, expected):
    assert _derive_weekly_prefix(name) == expected


def test_weekly_playlist_name_format():
    name = _weekly_playlist_name("My Mix", date(2024, 1, 8))
    assert name == "My Mix week of 2024-01-08"


def test_parse_week_date_roundtrip():
    title = _weekly_playlist_name("My Mix", date(2024, 1, 8))
    assert _parse_week_date_from_title(title, "My Mix") == date(2024, 1, 8)


def test_parse_week_date_wrong_prefix():
    assert _parse_week_date_from_title("Other week of 2024-01-08", "My Mix") is None


def test_parse_week_date_invalid_date():
    assert _parse_week_date_from_title("My Mix week of not-a-date", "My Mix") is None


def test_find_weekly_playlists_filters_by_prefix_and_valid_date():
    ytm = _FakeYTM(
        [
            {"title": "My Mix week of 2024-01-08", "playlistId": "p1"},
            {"title": "My Mix week of 2024-01-15", "playlistId": "p2"},
            {"title": "My Mix week of bad-date", "playlistId": "p3"},
            {"title": "Other Playlist", "playlistId": "p4"},
        ]
    )
    found = _find_weekly_playlists(ytm, "My Mix")
    assert {p["playlistId"] for p in found} == {"p1", "p2"}


def test_find_weekly_playlists_handles_empty_library():
    assert _find_weekly_playlists(_FakeYTM([]), "My Mix") == []


def test_prune_old_weeklies_keeps_newest():
    ytm = _FakeYTM(
        [
            {"title": "My Mix week of 2024-01-01", "playlistId": "old"},
            {"title": "My Mix week of 2024-01-08", "playlistId": "mid"},
            {"title": "My Mix week of 2024-01-15", "playlistId": "new"},
        ]
    )
    to_delete = _prune_old_weeklies(ytm, "My Mix", keep_weeks=2)
    assert [pid for _title, pid in to_delete] == ["old"]


def test_prune_old_weeklies_keep_zero_returns_empty():
    ytm = _FakeYTM([{"title": "My Mix week of 2024-01-01", "playlistId": "old"}])
    assert _prune_old_weeklies(ytm, "My Mix", keep_weeks=0) == []


def test_prune_old_weeklies_nothing_to_prune():
    ytm = _FakeYTM([{"title": "My Mix week of 2024-01-15", "playlistId": "new"}])
    assert _prune_old_weeklies(ytm, "My Mix", keep_weeks=2) == []
