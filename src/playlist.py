from __future__ import annotations

import bisect
import time
import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ytmusicapi import YTMusic

log = logging.getLogger(__name__)


def _chunked(seq: Iterable, n: int):
    seq_list = list(seq)
    for i in range(0, len(seq_list), n):
        yield seq_list[i : i + n]


def _get_playlist_items(ytm: YTMusic, playlist_id: str) -> List[Dict[str, Optional[str]]]:
    pl = ytm.get_playlist(playlist_id, limit=100000)
    items: List[Dict[str, Optional[str]]] = []
    for t in (pl.get("tracks") or []):
        set_id = t.get("setVideoId")
        vid = t.get("videoId")
        if not set_id:
            continue
        items.append({"videoId": vid, "setVideoId": set_id})
    return items


def _remove_extras_and_dupes(
    ytm: YTMusic, playlist_id: str, desired_set: Set[str]
) -> Tuple[List[str], Dict[str, str]]:
    items = _get_playlist_items(ytm, playlist_id)

    to_remove = []
    first_idx: Dict[str, int] = {}
    for i, it in enumerate(items):
        vid = it["videoId"]
        set_id = it["setVideoId"]
        if not isinstance(vid, str) or len(vid) != 11:
            to_remove.append({"setVideoId": set_id, "videoId": vid})
            continue
        if vid in first_idx:
            to_remove.append({"setVideoId": set_id, "videoId": vid})
        else:
            first_idx[vid] = i

    for vid, idx in list(first_idx.items()):
        if vid not in desired_set:
            it = items[idx]
            to_remove.append({"setVideoId": it["setVideoId"], "videoId": vid})
            del first_idx[vid]

    if to_remove:
        for chunk in _chunked(to_remove, 100):
            ytm.remove_playlist_items(playlist_id, chunk)

    kept_order: List[str] = []
    video_to_set: Dict[str, str] = {}
    for vid, idx in sorted(first_idx.items(), key=lambda kv: kv[1]):
        kept_order.append(vid)
        video_to_set[vid] = items[idx]["setVideoId"] or ""
    return kept_order, video_to_set


def _add_missing(ytm: YTMusic, playlist_id: str, desired_order: List[str], present_set: Set[str]) -> int:
    missing = [vid for vid in desired_order if vid not in present_set]
    for chunk in _chunked(missing, 100):
        if chunk:
            try:
                ytm.add_playlist_items(playlist_id, chunk, duplicates=False)
            except Exception:
                for vid in chunk:
                    try:
                        ytm.add_playlist_items(playlist_id, [vid], duplicates=False)
                    except Exception:
                        pass
    return len(missing)


def _lis_indices(seq: List[int]) -> List[int]:
    if not seq:
        return []
    parent = [-1] * len(seq)
    tails_val: List[int] = []
    tails_idx: List[int] = []

    for i, x in enumerate(seq):
        pos = bisect.bisect_left(tails_val, x)
        if pos == len(tails_val):
            tails_val.append(x)
            tails_idx.append(i)
        else:
            tails_val[pos] = x
            tails_idx[pos] = i
        if pos > 0:
            parent[i] = tails_idx[pos - 1]

    k = tails_idx[-1]
    out = []
    while k != -1:
        out.append(k)
        k = parent[k]
    out.reverse()
    return out


def _replace_playlist_items_safe(ytm: YTMusic, playlist_id: str, new_video_ids: List[str]) -> None:
    if hasattr(ytm, "replace_playlist_items"):
        ytm.replace_playlist_items(playlist_id, new_video_ids)
        return

    pl = ytm.get_playlist(playlist_id, limit=100000)
    tracks = pl.get("tracks") or []

    to_remove = []
    for t in tracks:
        set_id = t.get("setVideoId")
        vid = t.get("videoId")
        if set_id:
            item = {"setVideoId": set_id}
            if vid:
                item["videoId"] = vid
            to_remove.append(item)

    for chunk in _chunked(to_remove, 100):
        ytm.remove_playlist_items(playlist_id, chunk)

    for chunk in _chunked(new_video_ids, 100):
        ytm.add_playlist_items(playlist_id, chunk)


def _reorder_min_moves(
    ytm: YTMusic,
    playlist_id: str,
    desired_order: List[str],
    current_order: List[str],
    video_to_set: Dict[str, str],
) -> int:
    if current_order == desired_order:
        return 0

    desired_index = {v: i for i, v in enumerate(desired_order)}
    cf = [v for v in current_order if v in desired_index]
    idx_seq = [desired_index[v] for v in cf]
    lis_idx = _lis_indices(idx_seq)
    anchors = [cf[i] for i in lis_idx]
    anchors_set = set(anchors)

    moves = 0

    def _move_before(moved_vid: str, before_vid: Optional[str]):
        nonlocal moves, current_order
        moved_set = video_to_set.get(moved_vid)
        if not moved_set:
            return
        try:
            if before_vid is None:
                ytm.edit_playlist(playlist_id, moveItem=moved_set)
            else:
                before_set = video_to_set.get(before_vid)
                if not before_set:
                    return
                ytm.edit_playlist(playlist_id, moveItem=(moved_set, before_set))
        except Exception:
            raise

        if moved_vid in current_order:
            current_order.remove(moved_vid)
        if before_vid is None:
            current_order.append(moved_vid)
        else:
            try:
                idx = current_order.index(before_vid)
            except ValueError:
                idx = len(current_order)
            current_order.insert(idx, moved_vid)
        moves += 1

    prev: Optional[str] = None
    for vid in desired_order:
        if prev is None:
            if current_order and current_order[0] == vid:
                prev = vid
                continue
            if vid in anchors_set:
                prev = vid
            else:
                before_vid = current_order[0] if current_order and current_order[0] != vid else None
                _move_before(vid, before_vid)
                prev = vid
        else:
            if vid in anchors_set:
                prev = vid
            else:
                try:
                    idx_prev = current_order.index(prev)
                except ValueError:
                    before_vid = current_order[0] if current_order and current_order[0] != vid else None
                    _move_before(vid, before_vid)
                    prev = vid
                    continue

                if idx_prev + 1 < len(current_order) and current_order[idx_prev + 1] == vid:
                    prev = vid
                    continue

                before_vid = current_order[idx_prev + 1] if (idx_prev + 1) < len(current_order) else None
                if before_vid == vid:
                    prev = vid
                    continue
                _move_before(vid, before_vid)
                prev = vid

    return moves


def minimal_diff_update(ytm: YTMusic, playlist_id: str, desired_video_ids: List[str]) -> None:
    desired_video_ids = [v for v in desired_video_ids if isinstance(v, str) and len(v) == 11]
    seen: Set[str] = set()
    uniq_desired: List[str] = []
    for v in desired_video_ids:
        if v not in seen:
            seen.add(v)
            uniq_desired.append(v)
    desired_video_ids = uniq_desired
    desired_set = set(desired_video_ids)

    kept_order, video_to_set = _remove_extras_and_dupes(ytm, playlist_id, desired_set)

    added = _add_missing(ytm, playlist_id, desired_video_ids, set(kept_order))
    if added:
        items = _get_playlist_items(ytm, playlist_id)
        video_to_set = {}
        current_order = []
        for it in items:
            vid, set_id = it["videoId"], it["setVideoId"]
            if isinstance(vid, str) and len(vid) == 11 and vid in desired_set and vid not in video_to_set:
                video_to_set[vid] = set_id or ""
                current_order.append(vid)
    else:
        current_order = kept_order

    try:
        _reorder_min_moves(ytm, playlist_id, desired_video_ids, current_order, video_to_set)
    except Exception:
        _replace_playlist_items_safe(ytm, playlist_id, desired_video_ids)


def _normalize_desired_ids(desired_video_ids: List[str]) -> List[str]:
    desired = [v for v in desired_video_ids if isinstance(v, str) and len(v) == 11]
    seen: Set[str] = set()
    uniq: List[str] = []
    for v in desired:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def get_playlist_video_ids(ytm: YTMusic, playlist_id: str) -> List[str]:
    """
    Return the current playlist order as a list of 11-char videoIds.
    """
    items = _get_playlist_items(ytm, playlist_id)
    out: List[str] = []
    for it in items:
        vid = it.get("videoId")
        if isinstance(vid, str) and len(vid) == 11:
            out.append(vid)
    return out


def sync_playlist(
    ytm: YTMusic,
    playlist_id: str,
    desired_video_ids: List[str],
    *,
    verify_attempts: int = 3,
    verify_sleep_s: float = 1.0,
    force_replace_on_mismatch: bool = True,
) -> None:
    desired = _normalize_desired_ids(desired_video_ids)
    if not desired:
        _replace_playlist_items_safe(ytm, playlist_id, [])
        return

    minimal_diff_update(ytm, playlist_id, desired)

    def _matches() -> bool:
        current = get_playlist_video_ids(ytm, playlist_id)
        return current == desired

    for _ in range(max(1, verify_attempts)):
        if _matches():
            return
        time.sleep(max(0.0, verify_sleep_s))

    if force_replace_on_mismatch:
        _replace_playlist_items_safe(ytm, playlist_id, desired)
        for _ in range(2):
            if _matches():
                return
            time.sleep(max(0.0, verify_sleep_s))
        if not _matches():
            log.warning("Playlist %s order still mismatched after forced replace.", playlist_id)
