# Troubleshooting

## Known Issues

### Chromium: sync console output appears all at once

In Chromium-based browsers (but **not** Chrome, Firefox, Safari, etc.), Server-Sent Events from the sync console may be buffered and only displayed after the sync finishes, rather than streaming in real time. This is a Chromium-specific SSE buffering behavior when the response doesn't meet its internal flush heuristics.

**Workaround:** Use Chrome, Firefox, or another browser for real-time sync output. The sync itself is unaffected - only the live display is delayed in Chromium.

### Copyright-deleted videos linger in the playlist

When YouTube removes a video for copyright reasons, it stays in the playlist as a hidden `[Deleted video]` entry. The YouTube Music API does not expose these ghost entries, so the sync engine cannot detect or remove them. Because we try to keep a single playlist ID, the deleted video remains and the sync simply works around it - emptying what it can and re-adding the current tracks while the orphaned entry stays behind.

**Workaround:** Manually delete the playlist and let the next sync create a fresh one.

### Sync leaves behind an empty playlist

Occasionally the sync can fail mid-run (rate limits, transient API errors, etc.) and leave the playlist in an empty or partially-filled state.

**Workaround:** Run the sync again. If the playlist is still empty after a retry, open the **cache management modal** (database icon in the dashboard header) &rarr; *Playlist cache* tab and remove the affected entry, then run the sync once more so it rebuilds from scratch. As a last resort you can delete `cache/.playlist_cache.json` directly.

---

## Common Problems

### YouTube Music auth errors

- Ensure `browser.json` is valid (re-export via ytmusicapi or the web dashboard)
- Auth cookies expire periodically - re-authenticate if you see 401/403 errors from YouTube Music
- If using Docker, use the built-in auth flow in the web dashboard under **Settings**

### Last.fm errors (401/403/invalid key)

- Confirm `LASTFM_API_KEY` and `LASTFM_USER` are set correctly
- Verify your key at <https://www.last.fm/api/accounts>
- If Last.fm has intermittent IPv6 issues, try `LASTFM_FORCE_IPV4=true` (enabled by default)

### Playlist not updating

- Confirm `PLAYLIST_NAME` matches the existing playlist name exactly (case-sensitive)
- Check that `cache/.playlist_cache.json` has the correct playlist ID
- Set `LOG_LEVEL=DEBUG` for verbose output

### Missing or wrong matches

- Toggle `USE_ANON_SEARCH` - anonymous and authenticated searches can return different results
- Increase `EARLY_TERMINATION_SCORE` for more thorough searching (0.8-0.9)
- Set `EARLY_TERMINATION_SCORE=1.0` to disable early termination entirely
- Some tracks may be region-restricted or unavailable on YouTube Music
- Use [manual overrides](overrides.md) to fix specific songs
- Check the **Not Found** tab in the web dashboard to see all unresolved tracks

### Search performance issues

- Decrease `EARLY_TERMINATION_SCORE` for faster matching (results above this score stop the search immediately)
- Set `SLEEP_BETWEEN_SEARCHES=0` for maximum speed (default is 0.25s)
- Increase `SEARCH_MAX_WORKERS` for more parallel search threads (default: 2)

### Rate limiting or throttling

- Increase `SLEEP_BETWEEN_SEARCHES` (e.g., `0.5` or `1.0`)
- Reduce `SEARCH_MAX_WORKERS` to lower API load

### Weekly date mismatches

- Last.fm timestamps are in UTC - set `WEEKLY_TIMEZONE` to your local timezone so week boundaries align with your expectations
- Adjust `WEEKLY_WEEK_START` if your week starts on a different day (default: `MON`)

### Stale cache results

- Cached search results expire after `CACHE_SEARCH_TTL_DAYS` (default: 30). If a video has been removed or a better match exists, open the **cache management modal** (database icon in the dashboard header) &rarr; *Search cache* tab and bulk-delete the affected entries, or delete `cache/.search_cache.json` entirely.
- "Not found" entries are retried after `CACHE_NOTFOUND_TTL_DAYS` (default: 7). To force an immediate retry, clear the entry from the cache.
