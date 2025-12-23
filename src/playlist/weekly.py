import logging
from datetime import UTC, date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

log = logging.getLogger(__name__)


def _tz_from_name(name: str):
    if ZoneInfo is None:
        return UTC
    try:
        return ZoneInfo(name)
    except Exception:
        return UTC


def _parse_week_start(value: str | int) -> int:
    if isinstance(value, int):
        if 0 <= value <= 6:
            return value
        return 0
    v = str(value).strip().upper()
    mapping = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
    return mapping.get(v, 0)


def _start_of_week(dt: datetime, week_start: int) -> datetime:
    weekday = dt.weekday()
    delta_days = (weekday - week_start) % 7
    sow = (dt - timedelta(days=delta_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return sow


def _derive_weekly_prefix(main_playlist_name: str) -> str:
    s = main_playlist_name.strip()
    lower = s.lower()
    if lower.endswith("(auto)"):
        idx = lower.rfind("(auto)")
        base = s[:idx].rstrip()
        if base.endswith("("):
            base = base[:-1].rstrip()
        return base
    return s


def _weekly_playlist_name(base_prefix: str, week_start_date: date) -> str:
    return f"{base_prefix} week of {week_start_date.isoformat()}"


def _find_weekly_playlists(ytm, base_prefix: str) -> list[dict[str, str]]:
    marker = f"{base_prefix} week of "
    pls = ytm.get_library_playlists(limit=1000) or []
    out: list[dict[str, str]] = []
    for pl in pls:
        title = pl.get("title") or ""
        pid = pl.get("playlistId")
        if isinstance(title, str) and isinstance(pid, str) and title.startswith(marker):
            tail = title[len(marker) :].strip()
            try:
                _ = date.fromisoformat(tail)
                out.append({"title": title, "playlistId": pid})
            except Exception:
                continue
    return out


def _parse_week_date_from_title(title: str, base_prefix: str) -> date | None:
    marker = f"{base_prefix} week of "
    if not title.startswith(marker):
        return None
    tail = title[len(marker) :].strip()
    try:
        return date.fromisoformat(tail)
    except Exception:
        return None


def _prune_old_weeklies(ytm, base_prefix: str, keep_weeks: int) -> list[tuple[str, str]]:
    """Find weekly playlists older than keep_weeks and return them for deletion.

    Returns list of (title, playlist_id) tuples to delete.
    """
    if keep_weeks is None or keep_weeks <= 0:
        return []
    found = _find_weekly_playlists(ytm, base_prefix)
    if not found:
        return []
    dated: list[tuple[date, str, str]] = []
    for pl in found:
        title = pl["title"]
        pid = pl["playlistId"]
        d = _parse_week_date_from_title(title, base_prefix)
        if d is not None:
            dated.append((d, title, pid))
    dated.sort(key=lambda x: x[0], reverse=True)
    to_delete = dated[keep_weeks:]
    return [(title, pid) for _d, title, pid in to_delete]


def _build_weekly_desc(
    base_desc: str,
    user: str,
    week_start_dt: datetime,
    tz_name: str,
    week_start_label: str,
) -> str:
    return f"{base_desc}\nWeekly rolling mirror for {user}. Week of {week_start_dt.date().isoformat()} (start={week_start_label}, tz={tz_name})."


def update_weekly_playlist(
    ytm,
    get_existing_playlist_by_name,
    create_playlist_with_items,
    sync_playlist,
    *,
    settings,
    valid_video_ids: list[str],
    base_desc: str,
    cache=None,
) -> str | None:
    """Create or update the weekly playlist snapshot."""
    weekly_enabled = bool(getattr(settings, "weekly_enabled", True))
    if not weekly_enabled:
        log.info("Weekly playlist is disabled")
        return None

    base_prefix = getattr(settings, "weekly_playlist_prefix", None)
    if not base_prefix:
        base_prefix = _derive_weekly_prefix(settings.playlist_name)

    tz_name = str(getattr(settings, "weekly_timezone", "UTC"))
    tz = _tz_from_name(tz_name)
    week_start_label = str(getattr(settings, "weekly_week_start", "MON"))
    week_start = _parse_week_start(week_start_label)

    now = datetime.now(tz)
    sow = _start_of_week(now, week_start)
    weekly_name = _weekly_playlist_name(base_prefix, sow.date())

    weekly_privacy = getattr(settings, "weekly_privacy_status", None) or settings.privacy_status

    weekly_desc = _build_weekly_desc(
        base_desc=base_desc,
        user=settings.lastfm_user,
        week_start_dt=sow,
        tz_name=tz_name,
        week_start_label=week_start_label,
    )

    weekly_id = get_existing_playlist_by_name(ytm, weekly_name, cache=cache)

    main_template = cache.get_template(settings.playlist_name) if cache else None
    template_changed = main_template != valid_video_ids if main_template else True

    if weekly_id:
        log.info("Found existing weekly playlist '%s' (%s)", weekly_name, weekly_id)
        try:
            ytm.edit_playlist(
                weekly_id,
                title=weekly_name,
                description=weekly_desc,
                privacyStatus=weekly_privacy,
            )
        except Exception as e:
            log.error("Failed to edit weekly playlist: %s", e)

        if template_changed:
            log.info("Weekly template changed, syncing...")
            try:
                sync_playlist(ytm, weekly_id, valid_video_ids)
            except Exception as e:
                log.error("Weekly update failed: %s", e)
                return weekly_id
        else:
            log.info("Weekly unchanged (matches main), skipping sync")
    else:
        log.info("Creating weekly playlist '%s' (privacy=%s)", weekly_name, weekly_privacy)
        try:
            weekly_id = create_playlist_with_items(
                ytm,
                weekly_name,
                weekly_desc,
                weekly_privacy,
                valid_video_ids,
            )
            log.info("Weekly playlist created and populated")
        except Exception as e:
            log.error("Weekly create failed: %s", e)
            weekly_id = None

    keep_weeks = int(getattr(settings, "weekly_keep_weeks", 2))
    try:
        to_prune = _prune_old_weeklies(ytm, base_prefix, keep_weeks)
        for title, pid in to_prune:
            try:
                log.info("Pruning old weekly: %s (%s)", title, pid)
                ytm.delete_playlist(pid)
            except Exception as e:
                log.warning("Failed to delete %s: %s", title, e)
    except Exception as e:
        log.warning("Pruning old weeklies failed: %s", e)

    return weekly_id
