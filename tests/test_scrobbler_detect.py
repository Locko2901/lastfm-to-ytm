import pytest

from src.scrobbler.detect import BASELINE, PLAYS, RESET, SNAPSHOT_LIMIT, Pending, SnapshotEntry, confirm_step, detect_new_plays, snapshot_of
from src.scrobbler.history import HistoryItem, parse_history

pytestmark = pytest.mark.usefixtures("no_network")


def item(video_id, played="Today", duration=200):
    return HistoryItem(video_id=video_id, title=f"Song {video_id}", artists=("Artist",), duration=duration, played=played)


def items(*ids, played="Today"):
    return [item(v, played) for v in ids]


def snap(*ids, played="Today"):
    return [SnapshotEntry(v, played) for v in ids]


def new_ids(detection):
    return [i.video_id for i in detection.new_items]


def test_first_poll_is_only_a_baseline():
    detection = detect_new_plays(None, items("a", "b"))
    assert detection.baseline
    assert detection.new_items == []


def test_empty_previous_snapshot_is_also_a_baseline():
    assert detect_new_plays([], items("a")).baseline


def test_empty_history_is_reported_and_detects_nothing():
    detection = detect_new_plays(snap("a"), [])
    assert detection.empty
    assert detection.new_items == []


def test_unchanged_history_has_no_new_plays():
    detection = detect_new_plays(snap("a", "b", "c"), items("a", "b", "c"))
    assert new_ids(detection) == []
    assert not detection.reset


def test_new_songs_on_top_are_new_plays_newest_first():
    detection = detect_new_plays(snap("a", "b", "c"), items("x", "y", "a", "b", "c"))
    assert new_ids(detection) == ["x", "y"]
    assert detection.replays == 0


def test_song_played_again_moves_to_top_and_counts_once():
    detection = detect_new_plays(snap("a", "b", "c"), items("c", "a", "b"))
    assert new_ids(detection) == ["c"]
    assert detection.replays == 1


def test_song_from_the_middle_played_again():
    detection = detect_new_plays(snap("a", "b", "c", "d"), items("c", "a", "b", "d"))
    assert new_ids(detection) == ["c"]


def test_replay_above_a_new_song_is_detected():
    detection = detect_new_plays(snap("x", "a", "b"), items("x", "y", "a", "b"))
    assert new_ids(detection) == ["x", "y"]
    assert detection.replays == 1


def test_same_song_twice_in_a_row_is_invisible_in_the_same_shelf():
    detection = detect_new_plays(snap("a", "b"), items("a", "b"))
    assert new_ids(detection) == []


def test_same_song_again_is_detected_when_it_moves_into_today():
    previous = snap("a", "b", played="Yesterday")
    current = [item("a", "Today"), item("b", "Yesterday")]
    detection = detect_new_plays(previous, current)
    assert new_ids(detection) == ["a"]
    assert detection.shelf_moves == 1


def test_shelf_move_below_the_top_counts_everything_above():
    previous = snap("a", "b", "c", played="Yesterday")
    current = [item("a", "Today"), item("b", "Today"), item("c", "Yesterday")]
    assert new_ids(detect_new_plays(previous, current)) == ["a", "b"]


def test_shelf_move_with_inconsistent_shelves_is_ignored():
    previous = snap("a", "b", played="Last week")
    current = [item("a", "Yesterday"), item("b", "Today")]
    assert new_ids(detect_new_plays(previous, current)) == []


def test_midnight_moving_rows_out_of_today_detects_nothing():
    previous = snap("a", "b", played="Today")
    current = items("a", "b", played="Yesterday")
    assert new_ids(detect_new_plays(previous, current)) == []


def test_unknown_shelf_labels_never_count_as_moves():
    previous = snap("a", "b", played="Gestern")
    current = items("a", "b", played="Heute")
    assert new_ids(detect_new_plays(previous, current)) == []


def test_rows_removed_from_the_history_are_tolerated():
    assert new_ids(detect_new_plays(snap("a", "b", "c", "d"), items("a", "c", "d"))) == []


def test_older_rows_appearing_at_the_bottom_are_ignored():
    detection = detect_new_plays(snap("a", "b", "c"), items("x", "a", "b", "c", "z"))
    assert new_ids(detection) == ["x"]


def test_unknown_row_in_the_middle_means_everything_above_was_played():
    detection = detect_new_plays(snap("a", "b", "c"), items("x", "a", "y", "b", "c"))
    assert new_ids(detection) == ["x", "a", "y"]


def test_history_with_nothing_in_common_resets_the_snapshot():
    detection = detect_new_plays(snap("a", "b"), items("x", "y"))
    assert detection.reset
    assert detection.new_items == []


def test_snapshot_keeps_order_shelf_and_limit():
    rows = [item(f"v{i}", "Today" if i < 3 else "Yesterday") for i in range(SNAPSHOT_LIMIT + 10)]
    snapshot = snapshot_of(rows)
    assert len(snapshot) == SNAPSHOT_LIMIT
    assert snapshot[0] == SnapshotEntry("v0", "Today")
    assert snapshot[5] == SnapshotEntry("v5", "Yesterday")


def test_parse_history_reads_ytmusicapi_rows():
    raw = [
        {
            "videoId": "abc",
            "title": "Get Lucky",
            "artists": [{"name": "Daft Punk", "id": "x"}, {"name": "Pharrell Williams", "id": "y"}],
            "album": {"name": "Random Access Memories", "id": "z"},
            "duration": "6:09",
            "duration_seconds": 369,
            "played": "Today",
            "videoType": "MUSIC_VIDEO_TYPE_ATV",
        },
        {"videoId": None, "title": "No id"},
        {"videoId": "def", "title": "Clip", "artists": [], "album": None, "played": "Yesterday"},
    ]
    parsed, repeats = parse_history(raw)
    assert repeats == 0
    assert [p.video_id for p in parsed] == ["abc", "def"]
    first = parsed[0]
    assert first.artists == ("Daft Punk", "Pharrell Williams")
    assert first.album == "Random Access Memories"
    assert first.duration == 369
    assert first.is_today
    assert first.scrobble_artist == "Daft Punk"
    assert parsed[1].duration is None
    assert parsed[1].scrobble_artist == ""


def test_parse_history_counts_repeated_songs_and_keeps_the_newest_row():
    raw = [
        {"videoId": "a", "title": "One", "played": "Today"},
        {"videoId": "b", "title": "Two", "played": "Today"},
        {"videoId": "a", "title": "One", "played": "Yesterday"},
    ]
    parsed, repeats = parse_history(raw)
    assert repeats == 1
    assert [(p.video_id, p.played) for p in parsed] == [("a", "Today"), ("b", "Today")]


def test_music_video_titles_are_cleaned_for_scrobbling():
    clip = HistoryItem(
        video_id="v",
        title="Rick Astley - Never Gonna Give You Up (Official Music Video)",
        artists=("Rick Astley",),
        video_type="MUSIC_VIDEO_TYPE_OMV",
    )
    assert clip.scrobble_title == "Never Gonna Give You Up"
    song = HistoryItem(video_id="s", title="Song (Official Video)", artists=("A",), video_type="MUSIC_VIDEO_TYPE_ATV")
    assert song.scrobble_title == "Song (Official Video)"


def test_topic_channel_suffix_is_dropped_from_the_artist():
    row = HistoryItem(video_id="v", title="Song", artists=("Some Band - Topic",))
    assert row.scrobble_artist == "Some Band"


def test_podcast_episodes_are_not_music():
    episode = HistoryItem(video_id="p", title="Episode 1", artists=("Host",), video_type="MUSIC_VIDEO_TYPE_PODCAST_EPISODE")
    assert not episode.is_music


def test_upload_takes_artist_and_title_from_an_artist_title_title():
    upload = HistoryItem(
        video_id="u",
        title="Real Artist - Song (Lyrics)",
        artists=("Lyrics Channel",),
        video_type="MUSIC_VIDEO_TYPE_UGC",
    )
    assert upload.is_upload
    assert (upload.scrobble_artist, upload.scrobble_title) == ("Real Artist", "Song")
    assert upload.match_artists == ("Real Artist",)


def test_upload_without_an_artist_in_its_title_has_no_known_artist():
    upload = HistoryItem(video_id="u", title="Song (Lyrics)", artists=("Lyrics Channel",), video_type="MUSIC_VIDEO_TYPE_UGC")
    assert upload.scrobble_artist == ""
    assert upload.scrobble_title == ""
    assert upload.match_artists == ()


def test_official_music_video_keeps_the_credited_artist():
    clip = HistoryItem(video_id="o", title="Song (Official Video)", artists=("Real Artist",), video_type="MUSIC_VIDEO_TYPE_OMV")
    assert (clip.scrobble_artist, clip.scrobble_title) == ("Real Artist", "Song")
    assert clip.match_artists == ("Real Artist",)


def ids(entries):
    return [e.video_id for e in entries]


def accepted_ids(step):
    return [i.video_id for i in step.accepted]


def test_first_list_becomes_the_snapshot_once_the_next_fetch_lists_the_same_rows():
    first = confirm_step(None, None, items("a", "b"), 100)
    assert first.snapshot is None
    assert first.pending.kind == BASELINE
    second = confirm_step(None, first.pending, items("a", "b"), 160)
    assert (second.kind, ids(second.snapshot), second.observed_at) == (BASELINE, ["a", "b"], 160)
    assert second.accepted == []


def test_first_list_that_changed_waits_for_two_matching_fetches():
    first = confirm_step(None, None, items("a", "b", "c"), 100)
    flickered = confirm_step(None, first.pending, items("a", "c"), 160)
    assert flickered.snapshot is None
    third = confirm_step(None, flickered.pending, items("a", "b", "c"), 220)
    assert third.snapshot is None
    fourth = confirm_step(None, third.pending, items("a", "b", "c"), 280)
    assert ids(fourth.snapshot) == ["a", "b", "c"]


def test_new_rows_are_accepted_only_when_the_next_poll_confirms_them():
    confirmed = snap("a", "b", "c")
    seen = confirm_step(confirmed, None, items("x", "a", "b", "c"), 100)
    assert seen.accepted == []
    assert seen.snapshot is None
    assert seen.pending.new_ids == ("x",)
    assert seen.changed
    again = confirm_step(confirmed, seen.pending, items("x", "a", "b", "c"), 160)
    assert accepted_ids(again) == ["x"]
    assert (again.kind, again.seen_at, again.observed_at) == (PLAYS, 100, 160)
    assert ids(again.snapshot) == ["x", "a", "b", "c"]
    assert again.pending is None


def test_rows_confirmed_under_newer_ones_are_accepted_and_the_newer_ones_wait():
    confirmed = snap("a", "b", "c")
    seen = confirm_step(confirmed, None, items("x", "a", "b", "c"), 100)
    step = confirm_step(confirmed, seen.pending, items("y", "x", "a", "b", "c"), 160)
    assert accepted_ids(step) == ["x"]
    assert step.pending.new_ids == ("y",)
    assert step.pending.seen_at == 160
    assert step.observed_at == 100


def test_a_row_moved_up_for_one_poll_is_a_flicker():
    confirmed = snap("a", "b", "c", "d")
    moved = confirm_step(confirmed, None, items("c", "a", "b", "d"), 100)
    assert moved.pending.new_ids == ("c",)
    back = confirm_step(confirmed, moved.pending, items("a", "b", "c", "d"), 160)
    assert back.flicker
    assert back.accepted == []
    assert back.snapshot is None
    assert back.pending is None
    assert back.observed_at is None


def test_a_row_missing_for_one_poll_never_becomes_a_play():
    confirmed = snap("a", "b", "c", "d")
    seen = confirm_step(confirmed, None, items("x", "a", "c", "d"), 100)
    assert seen.pending.new_ids == ("x",)
    step = confirm_step(confirmed, seen.pending, items("x", "a", "b", "c", "d"), 160)
    assert accepted_ids(step) == ["x"]
    assert ids(step.snapshot) == ["x", "a", "b", "c", "d"]
    later = confirm_step(step.snapshot, step.pending, items("x", "a", "b", "c", "d"), 220)
    assert later.pending is None
    assert later.accepted == []


def test_a_stale_list_confirms_nothing_and_keeps_the_window_open():
    confirmed = snap("a", "b", "c")
    seen = confirm_step(confirmed, None, items("x", "a", "b", "c"), 100)
    stale = confirm_step(confirmed, seen.pending, items("a", "b", "c"), 160)
    assert stale.flicker
    assert (stale.accepted, stale.snapshot, stale.pending, stale.observed_at) == ([], None, None, None)
    again = confirm_step(confirmed, None, items("x", "a", "b", "c"), 220)
    step = confirm_step(confirmed, again.pending, items("x", "a", "b", "c"), 280)
    assert accepted_ids(step) == ["x"]
    assert step.seen_at == 220


def test_a_change_the_next_poll_shows_differently_starts_over():
    confirmed = snap("a", "b", "c")
    seen = confirm_step(confirmed, None, items("x", "a", "b", "c"), 100)
    other = confirm_step(confirmed, seen.pending, items("y", "a", "b", "c"), 160)
    assert other.flicker
    assert other.accepted == []
    assert other.pending.new_ids == ("y",)
    assert other.pending.seen_at == 160


def test_a_quiet_poll_moves_the_observed_time_and_refreshes_shelves():
    confirmed = snap("a", "b", played="Today")
    step = confirm_step(confirmed, None, items("a", "b", played="Yesterday"), 100)
    assert step.observed_at == 100
    assert step.accepted == []
    assert [e.played for e in step.snapshot] == ["Yesterday", "Yesterday"]


def test_a_list_sharing_nothing_resets_only_once_confirmed():
    confirmed = snap("a", "b")
    first = confirm_step(confirmed, None, items("p", "q"), 100)
    assert first.snapshot is None
    assert first.pending.kind == RESET
    second = confirm_step(confirmed, first.pending, items("p", "q"), 160)
    assert (second.kind, ids(second.snapshot), second.accepted) == (RESET, ["p", "q"], [])


def test_an_empty_list_keeps_everything_as_it_was():
    pending = Pending((SnapshotEntry("x"),), ("x",), 100)
    step = confirm_step(snap("a"), pending, [], 160)
    assert step.pending == pending
    assert step.snapshot is None
    assert step.observed_at is None
