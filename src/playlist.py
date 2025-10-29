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


class _QueryCounter:
    """Track API usage and performance metrics."""
    def __init__(self):
        self.count = 0
        self.session_start = None
        self.operation_counts = {
            'get_playlist': 0,
            'add_playlist_items': 0,
            'remove_playlist_items': 0,
            'edit_playlist': 0,
            'replace_playlist_items': 0,
            'get_song': 0
        }
        self.error_counts = {
            'retries': 0,
            'individual_fallbacks': 0,
            'failed_operations': 0
        }
    
    def increment(self, operation_type: str = 'unknown'):
        if self.session_start is None:
            self.session_start = time.time()
        
        self.count += 1
        if operation_type in self.operation_counts:
            self.operation_counts[operation_type] += 1
    
    def increment_error(self, error_type: str):
        if error_type in self.error_counts:
            self.error_counts[error_type] += 1
    
    def reset(self):
        """Reset all counters."""
        self.count = 0
        self.session_start = time.time()
        self.operation_counts = {k: 0 for k in self.operation_counts}
        self.error_counts = {k: 0 for k in self.error_counts}
    
    def get_count(self):
        return self.count
    
    def get_session_duration(self):
        if self.session_start is None:
            return 0.0
        return time.time() - self.session_start

_query_counter = _QueryCounter()


def _get_playlist_items(ytm: YTMusic, playlist_id: str) -> List[Dict[str, Optional[str]]]:
    _query_counter.increment('get_playlist')
    log.debug("API Query #%d: get_playlist(%s)", _query_counter.get_count(), playlist_id)
    pl = ytm.get_playlist(playlist_id, limit=None)
    items: List[Dict[str, Optional[str]]] = []
    for t in (pl.get("tracks") or []):
        set_id = t.get("setVideoId")
        vid = t.get("videoId")
        if not set_id:
            continue
        items.append({"videoId": vid, "setVideoId": set_id})
    log.debug("Retrieved %d playlist items", len(items))
    return items


def _retry_with_backoff(func, max_attempts=3, base_delay=0.0, max_delay=0.0):
    """Retry a function with fast retries only."""
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            error_msg = str(e).lower()
            
            is_retriable = (
                'conflict' in error_msg or 
                'server returned http' in error_msg or
                'sorry, something went wrong' in error_msg or
                'rate limit' in error_msg
            )
            
            if attempt == max_attempts - 1 or not is_retriable:
                raise
            
            log.debug("Attempt %d failed (%s), retrying immediately...", attempt + 1, str(e))
    
    raise Exception("Max retry attempts exceeded")


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
        for chunk in _chunked(to_remove, 50):
            def _remove_chunk():
                _query_counter.increment('remove_playlist_items')
                log.debug("API Query #%d: remove_playlist_items(%s, %d items)", _query_counter.get_count(), playlist_id, len(chunk))
                ytm.remove_playlist_items(playlist_id, chunk)
            
            try:
                _retry_with_backoff(_remove_chunk, max_attempts=3)
            except Exception as e:
                _query_counter.increment_error('retries')
                log.warning("Failed to remove chunk after retries: %s", e)
                for item in chunk:
                    try:
                        def _remove_item():
                            _query_counter.increment('remove_playlist_items')
                            log.debug("API Query #%d: remove_playlist_items(%s, 1 item)", _query_counter.get_count(), playlist_id)
                            ytm.remove_playlist_items(playlist_id, [item])
                        _retry_with_backoff(_remove_item, max_attempts=2)
                    except Exception:
                        _query_counter.increment_error('individual_fallbacks')
                        log.debug("Failed to remove individual item %s", item.get('videoId', 'unknown'))

    kept_order: List[str] = []
    video_to_set: Dict[str, str] = {}
    for vid, idx in sorted(first_idx.items(), key=lambda kv: kv[1]):
        kept_order.append(vid)
        video_to_set[vid] = items[idx]["setVideoId"] or ""
    return kept_order, video_to_set


def _add_missing(ytm: YTMusic, playlist_id: str, desired_order: List[str], present_set: Set[str]) -> Tuple[int, Dict[str, str]]:
    """Add missing videos and detect substitutions. Returns (count, substitutions)."""
    missing = [vid for vid in desired_order if vid not in present_set]
    detected_substitutions = {}
    
    if not missing:
        return 0, detected_substitutions
    
    items_before = _get_playlist_items(ytm, playlist_id)
    before_count = len(items_before)
    
    for chunk in _chunked(missing, 50):
        if chunk:
            def _add_chunk():
                _query_counter.increment('add_playlist_items')
                log.debug("API Query #%d: add_playlist_items(%s, %d items)", _query_counter.get_count(), playlist_id, len(chunk))
                ytm.add_playlist_items(playlist_id, chunk, duplicates=False)
            
            try:
                _retry_with_backoff(_add_chunk, max_attempts=3)
                
                if len(chunk) <= 5:
                    items_after = _get_playlist_items(ytm, playlist_id)
                    
                    new_items = items_after[before_count:]
                    new_video_ids = [item.get('videoId') for item in new_items[-len(chunk):] if item.get('videoId')]
                    
                    if len(new_video_ids) == len(chunk):
                        chunk_set = set(chunk)
                        added_set = set(new_video_ids)
                        
                        if added_set != chunk_set:
                            log.debug("Potential substitutions detected in chunk of %d videos", len(chunk))
                            
                            substitution_cache = {}
                            for orig_vid, new_vid in zip(chunk, new_video_ids):
                                if orig_vid != new_vid and _are_same_song(ytm, orig_vid, new_vid, substitution_cache):
                                    detected_substitutions[orig_vid] = new_vid
                                    log.info("Detected substitution during add: %s -> %s", orig_vid, new_vid)
                    
                    before_count = len(items_after)
                
            except Exception as e:
                _query_counter.increment_error('retries')
                log.warning("Failed to add chunk after retries: %s", e)
                for vid in chunk:
                    try:
                        def _add_item():
                            _query_counter.increment('add_playlist_items')
                            log.debug("API Query #%d: add_playlist_items(%s, 1 item)", _query_counter.get_count(), playlist_id)
                            ytm.add_playlist_items(playlist_id, [vid], duplicates=False)
                        _retry_with_backoff(_add_item, max_attempts=2)
                    except Exception:
                        _query_counter.increment_error('individual_fallbacks')
                        log.debug("Failed to add individual video %s", vid)
    
    return len(missing), detected_substitutions


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


def _get_video_title(ytm: YTMusic, video_id: str) -> str:
    try:
        info = ytm.get_song(video_id)
        if info and 'title' in info:
            return info['title']
        elif info:
            return info.get('name', f"<no-title:{video_id}>")
        
        try:
            search_results = ytm.search(video_id, filter="songs", limit=1)
            if search_results and len(search_results) > 0:
                result = search_results[0]
                if result.get('videoId') == video_id:
                    return result.get('title', f"<search-found:{video_id}>")
        except Exception:
            pass
            
    except Exception as e:
        log.debug("Failed to get title for video %s: %s", video_id, e)
    return f"<api-issue:{video_id}>"


def _analyze_video_accessibility(ytm: YTMusic, video_id: str) -> dict:
    analysis = {
        'video_id': video_id,
        'get_song_works': False,
        'search_finds_it': False,
        'title': None,
        'error': None
    }
    
    try:
        info = ytm.get_song(video_id)
        if info:
            analysis['get_song_works'] = True
            analysis['title'] = info.get('title', 'No title')
        else:
            analysis['error'] = 'get_song returned None'
    except Exception as e:
        analysis['error'] = str(e)
    
    try:
        search_results = ytm.search(video_id, filter="songs", limit=5)
        for result in search_results:
            if result.get('videoId') == video_id:
                analysis['search_finds_it'] = True
                if not analysis['title']:
                    analysis['title'] = result.get('title', 'No title')
                break
    except Exception as e:
        if not analysis['error']:
            analysis['error'] = f"Search failed: {str(e)}"
    
    return analysis


def _replace_playlist_items_safe(ytm: YTMusic, playlist_id: str, new_video_ids: List[str]) -> None:
    if hasattr(ytm, "replace_playlist_items"):
        try:
            def _replace_all():
                _query_counter.increment('replace_playlist_items')
                log.debug("API Query #%d: replace_playlist_items(%s, %d items)", _query_counter.get_count(), playlist_id, len(new_video_ids))
                ytm.replace_playlist_items(playlist_id, new_video_ids)
            _retry_with_backoff(_replace_all, max_attempts=3)
            return
        except Exception as e:
            _query_counter.increment_error('retries')
            log.warning("replace_playlist_items failed after retries, falling back to manual replace: %s", e)

    _query_counter.increment('get_playlist')
    log.debug("API Query #%d: get_playlist(%s) for manual replace", _query_counter.get_count(), playlist_id)
    pl = ytm.get_playlist(playlist_id, limit=None)
    tracks = pl.get("tracks") or []
    log.debug("Got %d tracks for manual replace", len(tracks))

    to_remove = []
    for t in tracks:
        set_id = t.get("setVideoId")
        vid = t.get("videoId")
        if set_id:
            item = {"setVideoId": set_id}
            if vid:
                item["videoId"] = vid
            to_remove.append(item)

    if to_remove:
        for chunk in _chunked(to_remove, 50): 
            def _remove_chunk():
                _query_counter.increment('remove_playlist_items')
                log.debug("API Query #%d: remove_playlist_items(%s, %d items)", _query_counter.get_count(), playlist_id, len(chunk))
                ytm.remove_playlist_items(playlist_id, chunk)
            
            try:
                _retry_with_backoff(_remove_chunk, max_attempts=3)
            except Exception as e:
                _query_counter.increment_error('retries')
                log.warning("Failed to remove chunk from playlist %s after retries: %s", playlist_id, e)
                for item in chunk:
                    try:
                        def _remove_item():
                            _query_counter.increment('remove_playlist_items')
                            log.debug("API Query #%d: remove_playlist_items(%s, 1 item)", _query_counter.get_count(), playlist_id)
                            ytm.remove_playlist_items(playlist_id, [item])
                        _retry_with_backoff(_remove_item, max_attempts=2)
                    except Exception:
                        _query_counter.increment_error('individual_fallbacks')
                        log.debug("Failed to remove individual item %s", item.get('videoId', 'unknown'))

    if new_video_ids:
        for chunk in _chunked(new_video_ids, 50):  # Larger chunks since no delay concerns
            def _add_chunk():
                _query_counter.increment('add_playlist_items')
                log.debug("API Query #%d: add_playlist_items(%s, %d items)", _query_counter.get_count(), playlist_id, len(chunk))
                ytm.add_playlist_items(playlist_id, chunk, duplicates=False)
            
            try:
                _retry_with_backoff(_add_chunk, max_attempts=3)
            except Exception as e:
                _query_counter.increment_error('retries')
                log.warning("Failed to add chunk to playlist %s after retries: %s", playlist_id, e)
                for vid in chunk:
                    try:
                        def _add_item():
                            _query_counter.increment('add_playlist_items')
                            log.debug("API Query #%d: add_playlist_items(%s, 1 item)", _query_counter.get_count(), playlist_id)
                            ytm.add_playlist_items(playlist_id, [vid], duplicates=False)
                        _retry_with_backoff(_add_item, max_attempts=2)
                    except Exception as ve:
                        _query_counter.increment_error('individual_fallbacks')
                        log.warning("Failed to add video %s to playlist %s: %s", vid, playlist_id, ve)


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
        
        def _do_move():
            if before_vid is None:
                _query_counter.increment('edit_playlist')
                log.debug("API Query #%d: edit_playlist(%s, moveItem to end)", _query_counter.get_count(), playlist_id)
                ytm.edit_playlist(playlist_id, moveItem=moved_set)
            else:
                _query_counter.increment('edit_playlist')
                log.debug("API Query #%d: edit_playlist(%s, moveItem before)", _query_counter.get_count(), playlist_id)
                before_set = video_to_set.get(before_vid)
                if not before_set:
                    return
                ytm.edit_playlist(playlist_id, moveItem=(moved_set, before_set))
        
        try:
            _retry_with_backoff(_do_move, max_attempts=3, base_delay=1.0)
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


def minimal_diff_update(ytm: YTMusic, playlist_id: str, desired_video_ids: List[str]) -> Dict[str, str]:
    """Update playlist with minimal changes. Returns detected substitutions."""
    desired_video_ids = [v for v in desired_video_ids if isinstance(v, str) and len(v) == 11]
    seen: Set[str] = set()
    uniq_desired: List[str] = []
    for v in desired_video_ids:
        if v not in seen:
            seen.add(v)
            uniq_desired.append(v)
    desired_video_ids = uniq_desired
    desired_set = set(desired_video_ids)

    log.debug("Updating playlist %s with %d desired videos", playlist_id, len(desired_video_ids))

    kept_order, video_to_set = _remove_extras_and_dupes(ytm, playlist_id, desired_set)
    log.debug("After removing extras/dupes: %d videos kept", len(kept_order))

    added_count, add_substitutions = _add_missing(ytm, playlist_id, desired_video_ids, set(kept_order))
    
    if add_substitutions:
        log.info("Applying %d substitutions detected during add phase", len(add_substitutions))
        desired_video_ids = _apply_substitutions(desired_video_ids, add_substitutions)
        desired_set = set(desired_video_ids)
    
    if added_count:
        log.debug("Added %d missing videos, refreshing playlist state", added_count)
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

    if current_order != desired_video_ids:
        log.debug("Reordering needed: current has %d items, desired has %d items", 
                 len(current_order), len(desired_video_ids))
        try:
            moves = _reorder_min_moves(ytm, playlist_id, desired_video_ids, current_order, video_to_set)
            log.debug("Completed reordering with %d moves", moves)
        except Exception as e:
            log.warning("Reordering failed (%s), falling back to replace", e)
            _replace_playlist_items_safe(ytm, playlist_id, desired_video_ids)
    else:
        log.debug("No reordering needed")
    
    return add_substitutions


def _normalize_desired_ids(desired_video_ids: List[str]) -> List[str]:
    desired = [v for v in desired_video_ids if isinstance(v, str) and len(v) == 11]
    seen: Set[str] = set()
    uniq: List[str] = []
    for v in desired:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _validate_video_accessibility(ytm: YTMusic, video_ids: List[str], max_batch_size: int = 20) -> List[str]:
    """
    Check which video IDs are actually accessible/valid by trying to get their info.
    Returns only the valid video IDs.
    """
    valid_ids = []
    
    for i in range(0, len(video_ids), max_batch_size):
        batch = video_ids[i:i + max_batch_size]
        for vid in batch:
            try:
                info = ytm.get_song(vid)
                if info and info.get('videoId') == vid:
                    valid_ids.append(vid)
                else:
                    log.debug("Video %s failed validation check", vid)
            except Exception:
                log.debug("Video %s is not accessible", vid)
    
    if len(valid_ids) < len(video_ids):
        log.info("Filtered out %d inaccessible videos (%d valid out of %d total)", 
                len(video_ids) - len(valid_ids), len(valid_ids), len(video_ids))
    
    return valid_ids


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
    log.debug("Extracted %d valid video IDs from playlist", len(out))
    return out


def _log_playlist_mismatch(playlist_id: str, desired: List[str], current: List[str], max_details: int = 10, ytm: Optional[YTMusic] = None) -> None:
    """Log detailed information about playlist order mismatches."""
    log.warning("Playlist %s order mismatch detected:", playlist_id)
    log.warning("  Expected %d items, got %d items", len(desired), len(current))
    
    if len(desired) != len(current):
        log.warning("  Length mismatch indicates some videos may be unavailable or restricted")
        
        desired_set = set(desired)
        current_set = set(current)
        missing = [vid for vid in desired if vid not in current_set]
        extra = [vid for vid in current if vid not in desired_set]
        
        if missing:
            log.warning("  Missing from current playlist: %s", missing[:5] + (['...'] if len(missing) > 5 else []))
        if extra:
            log.warning("  Extra in current playlist: %s", extra[:5] + (['...'] if len(extra) > 5 else []))
    else:
        mismatches = []
        for i in range(min(len(desired), len(current))):
            if desired[i] != current[i]:
                mismatches.append((i, desired[i], current[i]))
                if len(mismatches) >= max_details:
                    break
        
        if mismatches:
            log.warning("  Position mismatches (pos, expected, actual):")
            for pos, exp, act in mismatches:
                if ytm:
                    try:
                        exp_title = _get_video_title(ytm, exp)
                        act_title = _get_video_title(ytm, act)
                        log.warning("    [%d] expected='%s' (%s) actual='%s' (%s)", pos, exp, exp_title, act, act_title)
                    except Exception:
                        log.warning("    [%d] expected='%s' actual='%s'", pos, exp, act)
                else:
                    log.warning("    [%d] expected='%s' actual='%s'", pos, exp, act)
            if len(mismatches) == max_details and len(desired) > max_details:
                log.warning("    ... and potentially more mismatches")
        
        if ytm and mismatches and len(mismatches) <= 5:
            log.warning("  Analyzing problematic videos in detail:")
            problematic_videos = set()
            for pos, exp, act in mismatches:
                problematic_videos.add(exp)
                problematic_videos.add(act)
            
            for vid in list(problematic_videos)[:8]:
                analysis = _analyze_video_accessibility(ytm, vid)
                log.warning("    Video %s: get_song=%s, search_finds=%s, title='%s', error='%s'", 
                           vid, analysis['get_song_works'], analysis['search_finds_it'], 
                           analysis['title'] or 'None', analysis['error'] or 'None')


def _filter_problematic_videos(ytm: YTMusic, video_ids: List[str]) -> List[str]:
    """
    Filter out video IDs that cause issues with playlist operations.
    This is a last resort when normal validation fails.
    """
    log.debug("Filtering potentially problematic videos from %d total", len(video_ids))
    valid_ids = []
    
    for vid in video_ids:
        try:
            info = ytm.get_song(vid)
            if info and (info.get('videoId') == vid or info.get('title')):
                valid_ids.append(vid)
            else:
                log.debug("Video %s failed basic validation", vid)
        except Exception as e:
            log.debug("Video %s caused error during validation: %s", vid, e)
    
    if len(valid_ids) < len(video_ids):
        log.warning("Filtered out %d problematic videos that may cause playlist sync issues", 
                   len(video_ids) - len(valid_ids))
    
    return valid_ids


def _apply_substitutions(desired_ids: List[str], substitutions: Dict[str, str]) -> List[str]:
    """Apply detected video ID substitutions to the desired list."""
    if not substitutions:
        return desired_ids
    
    result = []
    for vid in desired_ids:
        substituted = substitutions.get(vid, vid)
        result.append(substituted)
        if substituted != vid:
            log.debug("Applied substitution: %s -> %s", vid, substituted)
    
    return result


def _are_same_song(ytm: YTMusic, vid1: str, vid2: str, cache: Dict[str, dict] = None) -> bool:
    """
    Check if two video IDs represent the same song using metadata comparison.
    Uses caching to minimize API calls.
    """
    if vid1 == vid2:
        return True
    
    if cache is None:
        cache = {}
    
    def get_cached_info(vid):
        if vid not in cache:
            try:
                _query_counter.increment('get_song')
                log.debug("API Query #%d: get_song(%s) for similarity check", _query_counter.get_count(), vid)
                cache[vid] = ytm.get_song(vid) or {}
            except Exception as e:
                log.debug("Failed to get info for %s: %s", vid, e)
                cache[vid] = {}
        return cache[vid]
    
    info1 = get_cached_info(vid1)
    info2 = get_cached_info(vid2)
    
    if not info1 or not info2:
        return False
    
    title1 = info1.get('title', '').strip()
    title2 = info2.get('title', '').strip()
    artists1 = [a.get('name', '').strip() for a in info1.get('artists', []) if a.get('name')]
    artists2 = [a.get('name', '').strip() for a in info2.get('artists', []) if a.get('name')]
    album1 = info1.get('album', {}).get('name', '').strip()
    album2 = info2.get('album', {}).get('name', '').strip()
    duration1 = info1.get('duration_seconds')
    duration2 = info2.get('duration_seconds')
    
    similarity_score = 0.0
    max_score = 0.0
    
    # Title similarity (40% of total score)
    if title1 and title2 and title1 != "No title" and title2 != "No title":
        max_score += 0.4
        try:
            from .search import _best_similarity
            title_sim = _best_similarity(title1, title2)
        except ImportError:
            from difflib import SequenceMatcher
            title_sim = SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
        similarity_score += title_sim * 0.4
        log.debug("Title similarity: %.3f ('%s' vs '%s')", title_sim, title1[:50], title2[:50])
    
    # Artist similarity (35% of total score)
    if artists1 and artists2:
        max_score += 0.35
        artist_set1 = set(name.lower() for name in artists1)
        artist_set2 = set(name.lower() for name in artists2)
        common_artists = len(artist_set1 & artist_set2)
        total_artists = len(artist_set1 | artist_set2)
        artist_sim = common_artists / total_artists if total_artists > 0 else 0.0
        similarity_score += artist_sim * 0.35
        log.debug("Artist similarity: %.3f (%s vs %s)", artist_sim, artists1, artists2)
    
    # Album similarity (15% of total score)  
    if album1 and album2:
        max_score += 0.15
        if album1.lower() == album2.lower():
            similarity_score += 0.15
        else:
            try:
                from .search import _best_similarity
                album_sim = _best_similarity(album1, album2)
            except ImportError:
                from difflib import SequenceMatcher
                album_sim = SequenceMatcher(None, album1.lower(), album2.lower()).ratio()
            if album_sim > 0.8:  # Only give partial credit for similar albums
                similarity_score += album_sim * 0.15
    
    # Duration similarity (10% of total score)
    if duration1 and duration2 and duration1 > 0 and duration2 > 0:
        max_score += 0.1
        duration_diff = abs(duration1 - duration2)
        if duration_diff <= 2:
            similarity_score += 0.1
        elif duration_diff <= 10:
            similarity_score += 0.05
    
    # Calculate final similarity as percentage of possible score
    if max_score > 0:
        final_similarity = similarity_score / max_score
        is_same = final_similarity >= 0.8  # 80% threshold
        log.debug("Song similarity: %.3f (score: %.3f/%.3f) -> %s", 
                 final_similarity, similarity_score, max_score, "SAME" if is_same else "DIFFERENT")
        return is_same
    
    # Fallback: if no metadata available, assume different
    return False


def _detect_video_substitutions_smart(ytm: YTMusic, expected_ids: List[str], actual_ids: List[str], cache: Dict[str, dict] = None) -> Dict[str, str]:
    """
    Improved substitution detection using content-aware matching instead of just position-based.
    More robust against reordering and partial matches.
    """
    substitutions = {}
    
    if not expected_ids or not actual_ids:
        return substitutions
    
    if cache is None:
        cache = {}
    
    # Find videos that are in expected but not in actual (candidates for substitution)
    expected_set = set(expected_ids)
    actual_set = set(actual_ids)
    missing_from_actual = expected_set - actual_set
    extra_in_actual = actual_set - expected_set
    
    if not missing_from_actual or not extra_in_actual:
        return substitutions
    
    log.debug("Checking for substitutions: %d missing, %d extra videos", 
             len(missing_from_actual), len(extra_in_actual))
    
    # For each missing video, try to find a matching video in the extras
    for missing_vid in missing_from_actual:
        best_match = None
        best_similarity = 0.0
        
        for extra_vid in extra_in_actual:
            if _are_same_song(ytm, missing_vid, extra_vid, cache):
                # Found a match - use this as substitution
                best_match = extra_vid
                break
        
        if best_match:
            substitutions[missing_vid] = best_match
            extra_in_actual.remove(best_match)  # Don't match it again
            log.info("Detected substitution: %s -> %s", missing_vid, best_match)
    
    return substitutions


def sync_playlist(
    ytm: YTMusic,
    playlist_id: str,
    desired_video_ids: List[str],
    *,
    verify_attempts: int = 2,
    validate_videos: bool = False,
    accept_substitutions: bool = True,
) -> None:
    # Reset counter at start of sync
    initial_count = _query_counter.get_count()
    log.info("Starting playlist sync for %s (current query count: %d)", playlist_id, initial_count)
    
    desired = _normalize_desired_ids(desired_video_ids)
    if not desired:
        _replace_playlist_items_safe(ytm, playlist_id, [])
        final_count = _query_counter.get_count()
        queries_used = final_count - initial_count
        log.info("Completed playlist sync for %s using %d API queries (total: %d)", 
                 playlist_id, queries_used, final_count)
        return
    
    if validate_videos:
        log.debug("Validating accessibility of %d videos...", len(desired))
        desired = _validate_video_accessibility(ytm, desired)

    detected_substitutions = minimal_diff_update(ytm, playlist_id, desired)
    
    if detected_substitutions:
        log.info("Applying %d substitutions detected during playlist update", len(detected_substitutions))
        desired = _apply_substitutions(desired, detected_substitutions)

    current = get_playlist_video_ids(ytm, playlist_id)
    if current == desired:
        final_count = _query_counter.get_count()
        queries_used = final_count - initial_count
        log.info("Completed playlist sync for %s using %d API queries (total: %d)", 
                 playlist_id, queries_used, final_count)
        return

    additional_substitutions = {}
    substitution_cache = {}
    
    if accept_substitutions:
        log.debug("Checking for additional video substitutions before retrying...")
        additional_substitutions = _detect_video_substitutions_smart(ytm, desired, current, substitution_cache)
        
        if additional_substitutions:
            log.info("Detected %d additional video substitutions, applying them...", len(additional_substitutions))
            adjusted_desired = _apply_substitutions(desired, additional_substitutions)
            
            if adjusted_desired != desired:
                minimal_diff_update(ytm, playlist_id, adjusted_desired)
                
                current = get_playlist_video_ids(ytm, playlist_id)
                if current == adjusted_desired:
                    log.info("Playlist sync successful with substituted video IDs")
                    final_count = _query_counter.get_count()
                    queries_used = final_count - initial_count
                    log.info("Completed playlist sync for %s using %d API queries (total: %d)", 
                             playlist_id, queries_used, final_count)
                    return
                else:
                    desired = adjusted_desired

    if current != desired:
        log.debug("Substitutions didn't resolve mismatch, trying full replace...")
        _replace_playlist_items_safe(ytm, playlist_id, desired)
        
        # Final verification
        for attempt in range(verify_attempts):
            current = get_playlist_video_ids(ytm, playlist_id)
            if current == desired:
                log.debug("Playlist sync successful after replace (attempt %d)", attempt + 1)
                final_count = _query_counter.get_count()
                queries_used = final_count - initial_count
                log.info("Completed playlist sync for %s using %d API queries (total: %d)", 
                         playlist_id, queries_used, final_count)
                return

    current = get_playlist_video_ids(ytm, playlist_id)
    current_set = set(current)
    desired_set = set(desired)
    content_similarity = len(current_set & desired_set) / len(desired_set) if desired_set else 0.0
    
    if content_similarity >= 0.95:
        log.info("Accepting playlist with %.1f%% content similarity (likely minor substitutions)", 
                content_similarity * 100)
    elif content_similarity >= 0.8:
        log.warning("Playlist has %.1f%% content similarity - may have unresolved issues", 
                   content_similarity * 100)
        # Log some details about the mismatch
        missing = desired_set - current_set
        extra = current_set - desired_set
        if missing:
            log.debug("Missing videos: %s", list(missing)[:5])
        if extra:
            log.debug("Extra videos: %s", list(extra)[:5])
    else:
        log.warning("Playlist sync failed with only %.1f%% content similarity", 
                   content_similarity * 100)
        log.warning("This indicates significant issues with video availability or API problems")
    
    final_count = _query_counter.get_count()
    queries_used = final_count - initial_count
    log.info("Completed playlist sync for %s using %d API queries (total: %d)", 
             playlist_id, queries_used, final_count)


def reset_query_counter():
    """Reset the global query counter. Useful for starting fresh counts."""
    _query_counter.reset()
    log.info("Playlist query counter reset to 0")


def get_query_count():
    """Get the current query count."""
    return _query_counter.get_count()


def log_playlist_statistics():
    """Log comprehensive playlist operation statistics for the session."""
    if _query_counter.session_start is None:
        log.info("No playlist statistics available - no operations performed this session")
        return
    
    session_duration = _query_counter.get_session_duration()
    total_queries = _query_counter.get_count()
    
    log.info("=== Playlist Session Statistics ===")
    log.info("Total playlist API queries: %d", total_queries)
    log.info("Session duration: %.1f seconds", session_duration)
    
    if session_duration > 0:
        log.info("Query rate: %.2f queries/second", total_queries / session_duration)
    
    # Log operation breakdown
    log.info("Operation breakdown:")
    for op_type, count in _query_counter.operation_counts.items():
        if count > 0:
            percentage = 100.0 * count / total_queries if total_queries > 0 else 0
            log.info("  %s: %d (%.1f%%)", op_type, count, percentage)
    
    # Log error statistics
    total_errors = sum(_query_counter.error_counts.values())
    if total_errors > 0:
        log.info("Error statistics:")
        for error_type, count in _query_counter.error_counts.items():
            if count > 0:
                log.info("  %s: %d", error_type, count)
        
        if total_queries > 0:
            error_rate = 100.0 * total_errors / total_queries
            log.info("Overall error rate: %.1f%%", error_rate)
    
    log.info("=====================================")


def get_playlist_statistics():
    """Get playlist statistics as a dictionary."""
    return {
        'total_queries': _query_counter.get_count(),
        'session_duration': _query_counter.get_session_duration(),
        'operation_counts': _query_counter.operation_counts.copy(),
        'error_counts': _query_counter.error_counts.copy(),
        'query_rate': _query_counter.get_count() / _query_counter.get_session_duration() 
                     if _query_counter.get_session_duration() > 0 else 0
    }
