from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Union

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


log = logging.getLogger(__name__)


def _tz_from_name(name: str):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _parse_week_start(value: Union[str, int]) -> int:
    """
    Return 0..6 where 0 = Monday, 6 = Sunday.
    Accepts 'MON'..'SUN' or int.
    """
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
    """
    Use the main playlist name without a trailing ' (auto)' for the weekly base.
    """
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


def _find_weekly_playlists(ytm, base_prefix: str) -> List[Dict[str, str]]:
    """
    Return library playlists whose title matches '<base_prefix> week of YYYY-MM-DD'.
    """
    marker = f"{base_prefix} week of "
    pls = ytm.get_library_playlists(limit=1000) or []
    out: List[Dict[str, str]] = []
    for pl in pls:
        title = pl.get("title") or ""
        pid = pl.get("playlistId")
        if isinstance(title, str) and isinstance(pid, str) and title.startswith(marker):
            tail = title[len(marker) :].strip()
            try:
                # exact ISO date
                _ = date.fromisoformat(tail)
                out.append({"title": title, "playlistId": pid})
            except Exception:
                continue
    return out


def _parse_week_date_from_title(title: str, base_prefix: str) -> Optional[date]:
    marker = f"{base_prefix} week of "
    if not title.startswith(marker):
        return None
    tail = title[len(marker) :].strip()
    try:
        return date.fromisoformat(tail)
    except Exception:
        return None


def _prune_old_weeklies(ytm, base_prefix: str, keep_weeks: int) -> None:
    """
    Keep the most recent 'keep_weeks' weekly playlists (by week date); delete older ones.
    If keep_weeks <= 0, do nothing (keep all).
    """
    if keep_weeks is None or keep_weeks <= 0:
        return
    found = _find_weekly_playlists(ytm, base_prefix)
    if not found:
        return
    dated: List[Tuple[date, str, str]] = []
    for pl in found:
        title = pl["title"]
        pid = pl["playlistId"]
        d = _parse_week_date_from_title(title, base_prefix)
        if d is not None:
            dated.append((d, title, pid))
    dated.sort(key=lambda x: x[0], reverse=True)
    to_delete = dated[keep_weeks:]
    for d, title, pid in to_delete:
        try:
            log.info("Pruning old weekly playlist: %s (%s)", title, pid)
            ytm.delete_playlist(pid)
        except Exception as e:
            log.warning("Failed to delete playlist %s (%s): %s", title, pid, e)


def _build_weekly_desc(
    base_desc: str,
    user: str,
    week_start_dt: datetime,
    tz_name: str,
    week_start_label: str,
) -> str:
    return (
        f"{base_desc}\n"
        f"Weekly rolling mirror for {user}. Week of {week_start_dt.date().isoformat()} "
        f"(start={week_start_label}, tz={tz_name})."
    )


def update_weekly_playlist(
    ytm,
    get_existing_playlist_by_name,
    create_playlist_with_items,
    minimal_diff_update,
    *,
    settings,
    valid_video_ids: List[str],
    base_desc: str,
) -> Optional[str]:
    """
    Create/update a weekly 'week of YYYY-MM-DD' playlist that mirrors the main recents.
    Keeps the previous week intact and optionally prunes older weeks.
    """
    weekly_enabled = bool(getattr(settings, "weekly_enabled", True))
    if not weekly_enabled:
        log.info("Weekly playlist is disabled by settings.weekly_enabled=False")
        return None

    base_prefix = getattr(settings, "weekly_playlist_prefix", None)
    if not base_prefix:
        base_prefix = _derive_weekly_prefix(settings.playlist_name)

    tz_name = str(getattr(settings, "weekly_timezone", "UTC"))
    tz = _tz_from_name(tz_name)
    week_start_label = str(getattr(settings, "weekly_week_start", "MON"))
    week_start = _parse_week_start(week_start_label)

    now = datetime.now(tz)
    sow = _start_of_week(now, week_start)  # timezone-aware
    weekly_name = _weekly_playlist_name(base_prefix, sow.date())

    weekly_privacy = getattr(settings, "weekly_privacy_status", None) or settings.privacy_status

    weekly_desc = _build_weekly_desc(
        base_desc=base_desc,
        user=settings.lastfm_user,
        week_start_dt=sow,
        tz_name=tz_name,
        week_start_label=week_start_label,
    )

    weekly_id = get_existing_playlist_by_name(ytm, weekly_name)
    if weekly_id:
        log.info("Updating weekly playlist '%s' (%s) ...", weekly_name, weekly_id)
        try:
            ytm.edit_playlist(weekly_id, title=weekly_name, description=weekly_desc, privacyStatus=weekly_privacy)
        except Exception:
            pass
        try:
            minimal_diff_update(ytm, weekly_id, valid_video_ids)
        except Exception as e:
            log.error("Weekly update failed: %s", e)
            return weekly_id
    else:
        log.info("Creating weekly playlist '%s' (privacy=%s) ...", weekly_name, weekly_privacy)
        try:
            weekly_id = create_playlist_with_items(ytm, weekly_name, weekly_desc, weekly_privacy, valid_video_ids)
        except Exception as e:
            log.error("Weekly create failed: %s", e)
            weekly_id = None

    keep_weeks = int(getattr(settings, "weekly_keep_weeks", 2))
    try:
        _prune_old_weeklies(ytm, base_prefix, keep_weeks)
    except Exception as e:
        log.warning("Pruning old weeklies failed: %s", e)

    return weekly_id
