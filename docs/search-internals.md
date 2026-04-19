# Search Internals

## Text Normalization (`src/search/normalization.py`)

All text comparison goes through a normalization pipeline:

| Function | Purpose |
|---|---|
| `nfkc_casefold()` | Unicode NFKC normalization + casefolding |
| `ascii_fold()` | Transliterate to ASCII via `unidecode` (removes diacritics) |
| `normalize_base()` | NFKC casefold + `&` &rarr; `and` + whitespace collapse |
| `alnum_space()` | Strip non-alphanumeric chars (replaced with spaces) |
| `tokens()` | Extract normalized token set (both Unicode and ASCII-folded) |
| `match_key()` | ASCII-folded, alnum-only, whitespace-collapsed - used for `SequenceMatcher` |

**Bracket removal** (`remove_bracketed()`): Iteratively strips content within 13 bracket pairs including Unicode variants: `()`, `[]`, `{}`, `（）`, `【】`, `「」`, `『』`, `〈〉`, `《》`, `＜＞`, `‹›`, `⟨⟩`.

**Featuring clause removal** (`strip_feat_clauses()`): Regex removes `feat.`, `featuring`, `ft.`, `with` and everything after.

**Uploader name cleaning** (`clean_uploader_name()`): Removes noise tokens common in YouTube channel names: `official`, `vevo`, `topic`, `music`, `records`, `recordings`, `channel`, `tv`, `label`, `wmg`, `umg`, `smg`, `sony`, `universal`, `warner`, `publishing`, `inc`, `ltd`, `entertainment`, etc.

---

## Similarity Metrics (`src/search/similarity.py`)

Three metrics used for fuzzy matching:

**Jaccard similarity** - token-based set intersection:

$$J(A, B) = \frac{|A \cap B|}{|A \cup B|}$$

**Coverage** - what fraction of a subset appears in a superset:

$$\text{cov}(S, T) = \frac{|S \cap T|}{|S|}$$

**Best similarity** - combined metric used for artist/title comparison:

$$\text{sim}(a, b) = 0.7 \times J(\text{tokens}(a), \text{tokens}(b)) + 0.3 \times \text{SequenceMatcher}(\text{match\_key}(a), \text{match\_key}(b))$$

The 70/30 split weights token overlap (order-independent) more heavily, while `SequenceMatcher` captures character-level sequential similarity.

---

## Match Scoring (`src/search/scoring.py`)

`score_candidate()` produces a 0.0-1.0 match score for each YouTube Music result.

### Base Score Components

| Component | Weight | Function |
|---|---|---|
| Title similarity | `0.56` | `title_similarity()` - Jaccard + SequenceMatcher on cleaned titles |
| Artist similarity | `0.32` | `artist_similarity()` - best match across all artist aliases vs candidate artists |
| Uploader similarity | `0.07` | `uploader_similarity()` - cleaned channel name vs artist aliases |
| Album similarity | `0.05` | `best_similarity()` on album names (if available) |

### Minimum Thresholds

Early rejection if scores are too low:

- Artist similarity &lt; `0.30` **and** uploader similarity &lt; `0.30` &rarr; score `0.0`
- Title similarity &lt; `0.25` &rarr; score `0.0`

### Bonuses

- **Song result type** (`resultType == "song"`): +`0.06` (official catalog)
- **Topic channel** (uploader contains "topic" with uploader similarity &ge; `0.6`): +`0.02`
- **Artist+title presence** (`artist_title_presence_bonus()`): up to +`0.07` when both artist and title tokens appear in the candidate title

### Penalties (subtractive, stacking)

| Penalty | Amount | Trigger |
|---|---|---|
| **Hard negative terms** | -`0.35` each (max -`0.60`) | `nightcore`, `daycore`, `sped`, `slowed`, `8d`, `chipmunk`, `reverb`, `pitch`, `bassboosted` in candidate but not in user query |
| **Soft negative terms** | -`0.08` each (max -`0.25`) | `live`, `acoustic`, `cover`, `karaoke`, `remix`, `instrumental`, `loop`, `mashup`, `tiktok`, `phonk`, `demo`, etc. |
| **Video result type** | -`0.03` | `resultType == "video"` (user upload) |
| **Video mismatch** | -`0.10` | Video title prefix doesn't match candidate artist (Jaccard &lt; `0.3`) |
| **Style mismatch** | -`0.12`/`0.18` | User wants a specific style (e.g., nightcore) but candidate lacks it |

**Hard negative auto-reject**: If hard negative terms are found in a `video` result from a non-topic channel, the score is immediately `0.0` (no further calculation).

---

## Query Building

`build_queries()` (`src/search/queries.py`) generates a comprehensive set of search query variants:

1. Split artist into aliases via `split_artist_aliases()` - handles separators like `,`, `&`, `feat.`, `/`, `x`, `×`, `;`, `and`, `with`, and dashes
2. Generate title variants: original, with brackets removed, with featured artist clauses stripped, ASCII-folded
3. For each alias &times; each title variant, produce three query patterns:
    - `"alias - title"` (dash-separated)
    - `'"title" "alias"'` (quoted terms)
    - `"title alias"` (space-separated)
    - Plus an album variant if album data is available
4. Append a fallback: `'"core_title"'` (title-only, quoted)
5. Deduplicate all queries against previously tried searches

---

## Two-Phase Search

`find_on_ytm()` (`src/search/executor.py`) uses a two-phase search strategy:

**Phase 1 - Exact query:** Runs `"artist - title"` sequentially through three YouTube Music filters (`songs`, `videos`, `None`). If a result exceeds the early termination threshold, returns immediately.

**Phase 2 - Parallel fallback:** If the exact query didn't produce a good enough match, generates the full query set via `build_queries()` and submits all (query, filter) pairs to a `ThreadPoolExecutor` (default 2 workers). A shared lock protects the best-score state; when any candidate exceeds the early termination threshold, all remaining futures are cancelled.

### Thresholds

- Base: `0.66` (no album) or `0.68` (with album)
- Videos: +`0.05` extra (harder to accept user uploads)
- Early termination: `max(EARLY_TERMINATION_SCORE, base + video_extra)`
- Grace zone: candidates within `0.06` of threshold are accepted with a debug log
