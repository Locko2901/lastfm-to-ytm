# History Scrobbler

What you play in the YouTube Music apps, on a phone in particular, never reaches
Last.fm when no scrobbler runs there. The **history scrobbler** fills that gap: it
reads your YouTube Music listening history every few minutes while you listen
(less often while the history is quiet), finds the plays that are new since the
last look, decides from the evidence whether each one
reached Last.fm's listening threshold, and scrobbles those that did, unless a
real-time scrobbler (a desktop or browser scrobbler, an Android app) already did.

!!! info "Optional, off by default, and a dry run first"
    Nothing happens until you enable it. When you do, it starts in **dry run**: a
    preview that records every decision (would scrobble, skipped as a duplicate
    of which scrobble, skipped for what reason) on the **Scrobbler** tab without
    sending anything to Last.fm. Look through the decisions, then switch dry run
    off.

It runs on the dashboard's [built-in scheduler](dashboard.md#integrated-scheduler),
as its own job: it does not need the automated sync to be on.

---

## Setting it up

1. **API secret.** Writing to Last.fm needs the *shared secret* of your Last.fm
   API account, and Last.fm shows it only when the API account is created. If you
   kept it, enter it next to the API key under **Settings &rarr; General &rarr;
   Credentials**, or in step 1 of the setup wizard. If you don't have it, create a
   new API account at
   [last.fm/api/account/create](https://www.last.fm/api/account/create) and enter
   its API key and secret together: a secret only works with the key of its own
   account (the sync works with the new key too). The secret is only needed for
   the history scrobbler.
2. **Connect Last.fm.** Under **Settings &rarr; Automation &rarr; History
   Scrobbler** (or the optional last step of the setup wizard), click **Connect
   Last.fm**, then **Approve on Last.fm** and allow access. Back in the dashboard
   the connection completes by itself. Behind the scenes this is Last.fm's token
   flow: `auth.getToken`, your approval on last.fm, then `auth.getSession`, which
   returns a session key that does not expire until you revoke it. You must
   approve as the account set in `LASTFM_USER`; another account is refused.
3. **Enable it.** Tick **Enable history scrobbler** and save. Leave **Dry run** on
   to preview the decisions first.

The first polls only save a snapshot of the history (a baseline, taken once two
polls in a row list the same rows). From then on a new play is recorded once the
poll after the one that showed it [confirms it](#confirmed-by-the-next-poll).
The dry run works without step 2: reading recent scrobbles only needs the API
key.

| Variable | Default | Description |
|---|---|---|
| `SCROBBLER_ENABLED` | `false` | Poll the YouTube Music history and scrobble new plays |
| `SCROBBLER_DRY_RUN` | `true` | Record every decision without scrobbling |
| `SCROBBLER_POLL_MINUTES` | `2` | Fastest interval between polls, in minutes (`1`-`60`): used while the history changes. See [adaptive polling](#adaptive-polling) and [what the interval changes](#what-the-poll-interval-changes) |
| `SCROBBLER_IDLE_MINUTES` | `10` | Interval after 30 minutes without a change, in whole minutes from the fastest interval to `60`. See [choosing the intervals](#choosing-the-intervals) |
| `SCROBBLER_DEFER_TO_REALTIME` | `true` | Leave the plays from while a real-time scrobbler was active to it, skips included. See [leaving plays to a real-time scrobbler](#leaving-plays-to-a-real-time-scrobbler) |
| `SCROBBLER_DB_FILE` | `runtime/scrobbler.db` | Snapshot, decisions, and the ledger of the scrobbler's own scrobbles |
| `LASTFM_API_SECRET` | *(empty)* | Shared secret of your Last.fm API account (in the main credentials) |
| `LASTFM_SESSION_KEY` | *(empty)* | Written by **Connect Last.fm**. Never shown in the dashboard |
| `LASTFM_SESSION_USER` | *(empty)* | The account that approved the session, written with the key |

Saving these settings reschedules the job right away; no restart is needed.
`LASTFM_MAX_RETRIES` and `LASTFM_FORCE_IPV4` apply to the scrobbler's Last.fm
calls too, and `API_MAX_RETRIES` to its history reads (see
[failures](#failures-and-notifications)).

## Previewing with the dry run

Open the **Scrobbler** tab (it appears while the scrobbler is enabled). It shows
the last and next poll (with the current [pace](#adaptive-polling)), the last 24
hours of decisions, and every detected play
with its estimated time, how uncertain that time is, how long it was listened to
according to the polls, and the decision:

| Decision | Meaning |
|---|---|
| **Would scrobble** | Dry run: this play would have been sent |
| **Scrobbled** | Sent and accepted. When Last.fm corrected the names, the correction is shown |
| **Skipped**, *listened at most ...* | The bounds show it stayed under Last.fm's threshold (**certain**), or the tie-break says so (**estimated**) |
| **Skipped**, *not counted: ... end ... / timing ...* | Its [end](#end-unknown) or its [timing](#timing-unknown) is not in the history and that case's model did not count it (**estimated**) |
| **Skipped**, *Left to the real-time scrobbler* | A real-time scrobbler was active around it (the active period is shown), so the play happened on its device and it decided it (see [below](#leaving-plays-to-a-real-time-scrobbler)) |
| **Skipped**, *Already scrobbled* | A recent scrobble covers it; the scrobble and how far apart they are is shown |
| **Skipped**, *Already playing on Last.fm* | It is Last.fm's now playing track |
| **Skipped**, other reasons | 30 s or shorter, no track length, older than 14 days, a podcast episode, too many scrobbles around it to check (see [long outages](#long-outages)), or ignored by Last.fm (with its code) |
| **Waiting** | Detected, not decided yet (see [when a play is decided](#when-a-play-is-decided)) |
| **Failed** | Last.fm refused the request; the error is shown |

Every decided play shows its listening bounds ("listened between 0:40 and 3:10
of 3:45; Last.fm needs 1:52") and whether the decision was **certain** or
**estimated**, with the tie-break's value for estimated ones. A play whose end or
timing the history does not show says so instead ("end unknown", "timing
unknown"); such decisions are never certain. A **near miss**
note means a scrobble with the same title was close in time but was not taken as
a duplicate (another version or another artist, see [matching](#matching)).
**Played again** marks a song that was already in the history and moved back to
the top.

**Poll now** runs a poll immediately. **Start over** forgets the snapshot and all
decisions (including the ledger); the next poll takes a new baseline. Scrobbles
on Last.fm are never touched.

To go live, untick **Dry run** and save. If the dry run recorded plays as "would
scrobble", the dashboard asks once whether to send them too; the default is
**no** (Enter, Escape and clicking outside the dialog all keep them unsent).

- **Send them**: only plays Last.fm still accepts by age (14 days, see
  [Last.fm's rules](#lastfms-rules)) are queued; older ones stay unsent. The next
  poll checks each queued play against your recent scrobbles again, exactly like
  a new play (so a play a real-time scrobbler sent in the meantime is skipped as
  a duplicate), records it in the ledger and sends it in batches of 50.
- **Don't send**: the plays stay "would scrobble".

Either way the answer is recorded on each of those plays and shown in the
decision log ("you chose to send it", "you chose not to send it", or "too old for
Last.fm"), together with what then happened to it. A play is offered only once:
turning the dry run on and off again only offers the plays recorded since.

The dry run shows what the scrobbler decides for your own listening. How well
the rule itself works is measured independently of any account, by the
[simulation](#what-the-poll-interval-changes) below.

## What the YouTube Music history gives

The scrobbler reads the history with ytmusicapi's `get_history()` and the same
browser auth as the sync. What that call returns shapes everything below:

- **No play times, no listening times.** Each row only says which shelf it sits
  in: *Today*, *Yesterday*, *This week*, *Last week*, or a month. Nothing shows
  how long a song played, or a pause or a stop.
- **One page.** A single unpaginated page of roughly 200 rows, newest first.
- **One row per song.** A song played again moves to the top; its older row
  disappears. Playing the song that is already on top changes nothing at all.
- **Shelf labels follow the request language.** ytmusicapi asks for English, so
  the labels are English.
- **A paused or empty history** cannot be read; the poll reports an error and
  keeps the last snapshot.
- **Offline plays arrive late.** Google's help for offline listening says the
  listening history is updated in your account when you go back online
  ([YouTube Music Help: Download music & podcasts to listen offline](https://support.google.com/youtubemusic/answer/6313535)).
  When exactly, in which order, and on which shelf those rows appear is not
  documented. They reach the history together, long after they started, which
  breaks the "a row appears when its song starts" assumption below (see
  [timing unknown](#timing-unknown)).

!!! warning "Not verified against a live account here"
    The points above come from ytmusicapi's code and from other projects that
    read the same history (rows are unique per video, replays move to the top,
    about 200 rows, no timestamps). The scrobbler assumes a row appears when a
    song starts. Each poll records how many rows were listed more than once
    (`history_repeats` in the poll log), so a dry run shows whether the "one row
    per song" behaviour ever changes. Whether a fetch can return a list that is
    briefly inconsistent is not known either; the scrobbler
    [does not trust a single fetch](#confirmed-by-the-next-poll).

## How new plays are detected

Every poll compares the current history with the snapshot saved by the previous
poll. Since a play puts its song on top and removes its older row, the current
list should be "songs played since the last poll" followed by the rest of the old
list in its old order. The detector takes the **fewest top rows** that explain
the current list this way: below them, every row must come from the snapshot,
in the same relative order.

| Snapshot (newest first) | Now | Detected |
|---|---|---|
| A B C | X Y A B C | X and Y |
| A B C | C A B | C (played again) |
| X A B | X Y A B | X and Y (X was played again after Y) |
| A B | A B | nothing: playing A again while it is on top is invisible |
| A *(Yesterday)* B | A *(Today)* B | A: a row moving into *Today* was played again |
| A B C D | A C D | nothing: B was removed from the history |
| A B C | X A B C Z | X (Z is an older song coming into view at the bottom) |
| A B | X Y | nothing: no overlap, the snapshot is reset |

Taking the fewest rows means that when the history is ambiguous the scrobbler
under-counts rather than inventing plays. A shelf change is only used when it
moves a row into *Today* and every row above it is in *Today* too.

### Confirmed by the next poll

The history list may not be consistent from one fetch to the next: a row listed
higher than it belongs for one fetch, a row missing for one fetch, or an older
version of the list served again. Trusting every fetch would turn each of these
into plays that never happened. So new rows are only **accepted once the
following poll confirms them**: the same new rows, in the same order, still
above the rows of the last confirmed snapshot. A change the next poll does not
confirm is a **flicker** (shown as the poll's status) and the confirmed snapshot
stays as it was.

| Confirmed snapshot | Poll 1 | Poll 2 | Result |
|---|---|---|---|
| A B C | X A B C | X A B C | X is accepted at poll 2, as first seen at poll 1 |
| A B C | X A B C | Y X A B C | X is accepted; Y waits for poll 3 |
| A B C D | C A B D | A B C D | flicker: C moved up for one fetch, nothing is played |
| A B C D | X A C D | X A B C D | X is accepted; B, missing for one fetch, is no play |
| A B C | X A B C | A B C | flicker (an older list); X is accepted once two polls show it again |

The next snapshot is built from the accepted rows on top of the previous
snapshot, never copied from a single fetch, so a row missing from one fetch
cannot come back later as a new play. A first list (and a list that shares
nothing with the snapshot) is only taken once two fetches in a row list the
same rows.

The extra poll costs nothing: a play is only decided once the next play is
known anyway. The timing is not affected either: a confirmed play keeps the
time window of the poll that first showed it.

**Restarts.** The snapshot, the rows waiting for confirmation, the time of the
last poll that confirmed nothing new had started, and the plays found are saved
in one SQLite transaction. A restart (or a crash) between polls therefore
neither loses plays (the next poll compares with the same snapshot and still
confirms the waiting rows) nor repeats them (they are already recorded). The
next poll simply covers a longer window.

## Timestamps and how uncertain they are

Plays first shown by one poll started between that poll and the last poll that
showed nothing new, in the order the history shows; nothing more is known about
when. The scrobbler spreads them evenly over that window and uses those times as
the scrobble timestamps.
The larger distance from a timestamp to the ends of its window is shown as
**±** on the Scrobbler tab: with 2-minute polls a single new song is placed
within ±1 minute. Plays whose [timing is unknown](#timing-unknown) (a burst, or
after a long gap) are instead laid back to back at full length, the newest
ending at the poll that showed them; their uncertainty is as long as the gap.

## Deciding whether a play counts

Last.fm counts a play of a track longer than 30 seconds once it was listened to
for **T = half the track or 4 minutes, whichever is less**. The history never
says how long a song played, but the polls bound it from both ends:

- a play **started** after the poll before the one that first showed it, and by
  that poll;
- it **ended** when the next play started, and the next play's start is bounded
  the same way by the polls around it.

So the listening time lies between

- **lo** = earliest start of the next play minus latest start of this one, and
- **hi** = latest start of the next play minus earliest start of this one,

both capped by the track length. Plays found in the same poll share that window:
each of them, except the newest, started and ended inside it.

The decision follows from the bounds:

- **hi < T**: the play certainly stayed under the threshold. Skipped, *certain*.
- **lo >= T**: the play certainly reached it. Counted, *certain*.
- in between: one **tie-break** decides, *estimated*, the same for every user.
  It counts the play when it reached T with **at least an even chance**, taking
  every start as equally likely anywhere in its window (and plays that share a
  window in their known order). That is the only assumption: nothing about
  when or how often anyone skips.

The newest play has no next play yet, so it stays **open** while it could still
be playing: being on top says nothing about whether it still plays, so an open
play is never counted from its time on top alone. It is decided once the next
play appears, or once it has been on top longer than it could have lasted (see
end unknown).

The tie-break was chosen by the simulation below, against the plain midpoint of
lo and hi (which counts nearly every play, since hi is capped by the track
length), the midpoint with plays sharing a window capped to its length, a
stricter three-in-four chance, and skipping every play the bounds leave open.

### End unknown

The history shows neither a pause nor a stop. When the next play started later
than this one could have lasted (its earliest start minus this one's latest
start is more than the track length plus 30 seconds), or nothing followed and
the play has been on top longer than that, listening stopped or paused at a
time the history does not show. Such a play has an **unknown end**: the bounds
are meaningless, the decision is never certain, and an explicit model decides:

| Model | Decision |
|---|---|
| `count` (default) | count it |
| `skip` | skip it |
| `pause_window` | count it when the next play started within 30 minutes of when this one could have ended (a pause), skip it otherwise (a stop) |

The simulation chose `count`: it has the lowest weighted error at every
interval. Most such plays are the last song of a session or a song paused for a
while, and those were mostly played far enough. The decision log shows
*end unknown* on these plays.

### Timing unknown

Two cases break the assumption that a row appears when its song starts:

- **A burst**: more new plays in one window than could have started in it at a
  few seconds each (more than one per 5 seconds of the window). That is not
  skipping but rows arriving late, as when offline plays sync.
- **A long gap**: plays found after more than 30 minutes without a successful
  read (an outage, the dashboard was down), whose window is too long to bound
  anything.

Their timing is unknown: the decision is never certain, a model decides
(`count`, the default chosen by the simulation, or `skip`), and duplicates are
looked for over a whole day around them (see [the window](#the-window)). The
play just before them has an unknown end. A small burst found in a long window
(for example 15 offline plays found by a poll at the idle pace, 10 minutes after
the previous one) looks the same as fast skipping and is judged by its bounds;
the simulation shows what that costs.

## Adaptive polling

`SCROBBLER_POLL_MINUTES` is the **fastest** interval and `SCROBBLER_IDLE_MINUTES`
the **idle** one (both under **Settings &rarr; Automation &rarr; History
Scrobbler**). The scheduler ticks at the fastest interval, and each tick only
reads the history when a poll is due:

| Pace | Interval | When |
|---|---|---|
| fast | `SCROBBLER_POLL_MINUTES` (default 2 minutes) | the history changed in the last 30 minutes |
| idle | `SCROBBLER_IDLE_MINUTES` (default 10 minutes, from the fastest interval up to 60) | nothing changed for 30 minutes |
| backoff | the fastest interval doubled per failed read in a row, up to 30 minutes | the history could not be read |

The first change seen at the idle pace brings the fast pace back for the next
poll. **Poll now** always polls. The Scrobbler tab shows the current pace and
when the next poll is due. The cost of a longer idle interval: the first play
after a quiet spell is found in a window of up to that interval, so its timing
and bounds are looser; the simulation below includes it (each session starts
after an idle hour). Saving an idle interval below the fastest one, or anything
but a whole number of minutes, is refused.

## What the poll interval changes

A shorter interval narrows every window, which narrows lo and hi: more decisions
are certain and fewer depend on the tie-break. The table below comes from a
simulation (`scripts/scrobbler_simulation.py`) that generates listening sessions
with known listening times and runs each through the scrobbler's own poller, in
dry run with a temporary database: on the scheduler's ticks with the adaptive
pacing above (from an idle hour before each session to two hours after it),
with a fake history that returns what each poll would read and a fake Last.fm.
Detection, confirmation, the played rule, the deferral to a real-time scrobbler
and the duplicate check are the service's own, so the tables follow any change
to them; every decision is compared with Last.fm's rule applied to the real
listening times.

Each scenario is 40 sessions. Skipped tracks are skipped after a time drawn half
from the first 30 seconds and half from anywhere in the track; pauses last 1 to
20 minutes. Half of the sessions end with listening stopped somewhere in the
last track, the others play it out (an album always plays out). Offline plays
reach the history together, when the phone reconnects (after the session, 5 to
60 minutes later, or at the next online play for an offline stretch in a
session). The outage scenario cannot read the history for two hours; the flicker
scenario returns, on 15% of the fetches, a list with a row moved up, a row
missing, or the previous list. In the mixed-device scenario the sessions take
turns between the phone and a computer whose real-time scrobbler shows each song
as now playing while it plays and scrobbles those that reach the threshold, on
the fake Last.fm the poller reads; there the missed scrobbles only count the
phone's, and sending one of the computer's plays is always a false scrobble (a
second scrobble of a real one, or one that should not exist). Immediate repeats
are invisible in the history, so they show up as missed scrobbles. False
scrobbles weigh most: they end up on a public profile. The tables are generated
by the script (`--write` updates this section, `--check` fails when it is out of
date).

### Simulation results

Each cell: **false scrobbles** (share of sent scrobbles that should not exist) / **missed scrobbles** (share of real ones not sent) / **certain** (share of decisions the bounds made without a model or tie-break).

| Scenario | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| Album played through | 0.0% / 0.0% / 85.4% | 0.0% / 0.0% / 43.9% | 0.0% / 13.8% / 0.5% | 0.0% / 10.3% / 0.0% |
| Shuffle, no skips | 1.0% / 0.3% / 89.2% | 1.3% / 0.2% / 46.9% | 0.9% / 14.8% / 1.0% | 0.9% / 11.6% / 0.0% |
| Shuffle, 20% skipped | 2.5% / 0.3% / 84.0% | 3.4% / 1.5% / 39.7% | 5.7% / 16.4% / 0.7% | 8.7% / 19.1% / 0.0% |
| Shuffle, 50% skipped | 6.3% / 1.2% / 71.8% | 11.3% / 6.1% / 33.7% | 13.7% / 25.2% / 0.4% | 19.4% / 36.6% / 0.0% |
| Fast skipping through a playlist | 10.2% / 0.3% / 80.7% | 11.2% / 8.6% / 35.5% | 20.1% / 38.6% / 0.4% | 28.4% / 56.4% / 0.0% |
| Repeats (same track again, or one of the last five) | 2.6% / 25.1% / 64.0% | 3.4% / 25.7% / 38.4% | 4.4% / 32.7% / 3.2% | 9.2% / 36.7% / 0.0% |
| Pauses of 1 to 20 min | 6.0% / 0.4% / 65.3% | 6.1% / 0.8% / 34.3% | 8.4% / 13.7% / 1.5% | 9.9% / 14.1% / 0.0% |
| Many very short tracks (15 to 45 s) | 3.2% / 5.1% / 58.4% | 5.1% / 2.7% / 30.6% | 7.0% / 18.3% / 0.8% | 9.5% / 31.9% / 0.0% |
| Many very long tracks (10 to 20 min) | 1.8% / 0.5% / 86.1% | 3.9% / 1.4% / 55.5% | 6.6% / 11.5% / 26.5% | 7.8% / 10.1% / 13.1% |
| Played offline, synced when the phone reconnects | 25.0% / 96.1% / 0.0% | 20.0% / 95.7% / 0.0% | 25.0% / 96.1% / 0.0% | 20.0% / 95.7% / 0.0% |
| Offline stretch in a session, synced at the next online play | 5.2% / 43.5% / 55.6% | 6.1% / 42.1% / 28.6% | 8.7% / 51.8% / 0.3% | 10.3% / 52.1% / 0.0% |
| History unreadable for two hours | 10.3% / 1.5% / 41.5% | 8.4% / 20.5% / 26.7% | 12.8% / 9.9% / 0.3% | 12.4% / 26.7% / 0.0% |
| Inconsistent lists on 15% of the fetches | 3.2% / 2.4% / 71.0% | 5.1% / 9.1% / 36.2% | 6.4% / 20.5% / 1.3% | 8.7% / 20.2% / 0.0% |
| Phone and a computer with a real-time scrobbler, taking turns | 4.4% / 1.0% / 79.8% | 6.5% / 2.2% / 40.0% | 12.2% / 19.1% / 1.3% | 12.6% / 32.9% / 0.0% |
| **All scenarios** | **4.3% / 14.4% / 66.6%** | **5.3% / 17.0% / 34.8%** | **7.8% / 27.8% / 2.7%** | **9.4% / 31.7% / 1.0%** |

Polls per simulated session with adaptive pacing (each session runs from an idle hour before it to two hours after it): fastest 1 min: 114; fastest 2 min: 64; fastest 5 min: 35; fastest 10 min: 25.

Variants compared over all scenarios (false / missed, and the cost: 3 per false scrobble, 1 per missed one). Each table changes one choice and keeps the others; the last one only concerns the mixed-device scenario:

| Tie-break | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `midpoint` | 5.8% / 3.9% (cost 2039) | 8.3% / 6.4% (cost 2958) | 19.9% / 3.4% (cost 7029) | 20.4% / 5.9% (cost 7337) |
| `shared_midpoint` | 4.9% / 13.9% (cost 2556) | 6.7% / 15.7% (cost 3157) | 14.7% / 15.3% (cost 5502) | 15.6% / 18.5% (cost 5982) |
| `probability_50` (chosen) | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `probability_75` | 3.4% / 15.3% (cost 2282) | 3.4% / 26.8% (cost 3223) | 5.6% / 39.1% (cost 4660) | 7.4% / 61.3% (cost 6611) |
| `certain_only` | 3.0% / 22.7% (cost 2791) | 3.9% / 54.1% (cost 5578) | 14.9% / 85.6% (cost 8696) | 16.8% / 88.7% (cost 8946) |

| End unknown | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `count` (chosen) | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `skip` | 3.0% / 22.4% (cost 2780) | 4.2% / 24.8% (cost 3239) | 6.5% / 34.8% (cost 4516) | 8.6% / 37.4% (cost 5162) |
| `pause_window` | 3.3% / 19.0% (cost 2563) | 4.3% / 21.4% (cost 2979) | 6.6% / 32.3% (cost 4364) | 8.6% / 36.2% (cost 5080) |

| Timing unknown | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `count` (chosen) | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `skip` | 3.6% / 17.9% (cost 2553) | 4.9% / 19.4% (cost 2975) | 7.0% / 31.7% (cost 4395) | 8.6% / 36.1% (cost 5080) |

| Burst: seconds per play | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `3 s` | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `5 s` (chosen) | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `10 s` | 5.3% / 13.2% (cost 2611) | 5.4% / 17.0% (cost 2917) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `20 s` | 9.3% / 13.2% (cost 3736) | 7.3% / 15.4% (cost 3304) | 7.9% / 27.8% (cost 4336) | 9.4% / 31.7% (cost 4968) |

| New rows | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `confirmed by the next poll` (chosen) | 4.3% / 14.4% (cost 2442) | 5.3% / 17.0% (cost 2881) | 7.8% / 27.8% (cost 4292) | 9.4% / 31.7% (cost 4968) |
| `every fetch trusted` | 32.7% / 15.4% (cost 12935) | 6.5% / 17.7% (cost 3257) | 8.4% / 28.3% (cost 4511) | 9.7% / 31.8% (cost 5038) |

| Real-time deferral (mixed devices) | Fastest 1 min | Fastest 2 min | Fastest 5 min | Fastest 10 min |
|---|---|---|---|---|
| `off` | 6.2% / 1.0% (cost 82) | 9.6% / 2.2% (cost 119) | 19.0% / 17.6% (cost 250) | 21.2% / 21.7% (cost 274) |
| `gap 2 min` | 4.4% / 1.0% (cost 58) | 6.5% / 2.2% (cost 80) | 12.2% / 19.1% (cost 174) | 12.6% / 32.9% (cost 199) |
| `gap 5 min` | 4.4% / 1.0% (cost 58) | 6.5% / 2.2% (cost 80) | 12.2% / 19.1% (cost 174) | 12.6% / 32.9% (cost 199) |
| `gap 10 min` (chosen) | 4.4% / 1.0% (cost 58) | 6.5% / 2.2% (cost 80) | 12.2% / 19.1% (cost 174) | 12.6% / 32.9% (cost 199) |
| `gap 15 min` | 4.4% / 1.0% (cost 58) | 6.5% / 2.2% (cost 80) | 12.2% / 19.1% (cost 174) | 12.6% / 32.9% (cost 199) |
| `gap 2 min, no now playing` | 6.2% / 1.0% (cost 82) | 8.4% / 2.2% (cost 104) | 12.7% / 19.1% (cost 180) | 12.6% / 32.9% (cost 199) |
| `gap 5 min, no now playing` | 6.2% / 1.0% (cost 82) | 7.9% / 2.2% (cost 98) | 12.7% / 19.1% (cost 180) | 12.6% / 32.9% (cost 199) |
| `gap 10 min, no now playing` | 6.2% / 1.0% (cost 82) | 7.9% / 2.2% (cost 98) | 12.7% / 19.1% (cost 180) | 12.6% / 32.9% (cost 199) |
| `gap 15 min, no now playing` | 6.2% / 1.0% (cost 82) | 7.9% / 2.2% (cost 98) | 12.9% / 20.0% (cost 183) | 12.6% / 32.9% (cost 199) |

The idle interval (all scenarios, at the default fastest interval; the polls include an idle hour before and two hours after each session):

| Idle interval (fastest 2 min) | False / missed / certain | Polls per session |
|---|---|---|
| 5 min | 4.6% / 16.7% / 34.9% | 74 |
| 10 min (default) | 5.3% / 17.0% / 34.8% | 64 |
| 15 min | 5.9% / 17.2% / 31.8% | 56 |

### Choosing the intervals

**The default is 2 minutes.** Compared with 5 minutes it has fewer false
scrobbles and far fewer missed ones, and about a third of its decisions are
certain instead of almost none.

**1 minute is the shortest interval.** It cuts the weighted errors further and
makes about two thirds of the decisions certain, but it doubles the requests
while you listen (see below), and YouTube publishes no limit for them. Choose it
if you want the most certain decisions and polls keep succeeding. Fast skipping
through a playlist stays the hardest case at any interval: several songs share
one window and the bounds cannot separate them.

The variant tables show how each choice of the played rule was made: every
row changes one choice and keeps the others, and the chosen ones have the
lowest weighted error at the default interval. Making the burst rule wider
(more seconds per play) catches more offline plays but turns more fast skipping
into false scrobbles; `3 s` and `5 s` decide the same in these sessions.

A history request is one authenticated YouTube Music browse call. Its answer is
about 2 MB of JSON for the roughly 200 rows (about 150 KB compressed on the
wire), measured on ytmusicapi's recorded responses of the same shape. With
adaptive polling the number of requests depends on how much you listen; for a
day with 3 hours of listening (fast pace for those hours and the half hour
after, idle pace at the default 10 minutes for the rest):

| Fastest interval | Requests per day | Data per day (compressed) |
|---|---|---|
| 1 min (shortest) | about 330 | about 50 MB |
| **2 min (default)** | about 230 | about 34 MB |
| 5 min | about 165 | about 25 MB |
| 10 min | 144 | about 22 MB |

**The idle interval** decides how often a quiet history is read, which is most
of the day. At the default fastest interval of 2 minutes, for the same day:

| Idle interval | Requests per day | Without listening | Data per day (compressed) | First play after a quiet spell |
|---|---|---|---|---|
| 5 min | about 350 | 288 | about 53 MB | within ±2.5 min |
| **10 min (default)** | about 230 | 144 | about 34 MB | within ±5 min |
| 15 min | about 190 | 96 | about 28 MB | within ±7.5 min |

A shorter idle interval mostly buys a tighter window for the first play of a
session (and for offline plays that sync while the history is quiet); every
later play of the session is found at the fastest interval anyway. The last
table of the simulation results shows what that is worth over all scenarios.
10 minutes keeps the requests of a quiet day low; 5 minutes doubles them for
slightly fewer false scrobbles, 15 minutes saves a third of them for slightly
more false scrobbles and fewer certain decisions.

YouTube publishes no limits for these calls; ytmusicapi's documentation only
says a rate limit exists that normal use does not reach. Throttling would show
up as failed polls (reported like any other failure, and polls back off); raise
the intervals if it happens.

## Deduplication

### When a play is decided

A play is decided one minute after the poll that first showed the next play (in
practice at the poll that confirms the next play), or, when nothing followed,
one minute after it has been on top longer than it could have lasted (its length
plus 30 seconds). A play of unknown timing is decided one minute after the poll
that found it. The minute gives a real-time scrobbler running next to this one
the chance to scrobble the play, or show it as now playing, so the check below
sees it. With 2-minute polls a play is usually decided one poll after the next
one appeared.

Each poll goes through the waiting plays in this order:

1. a play older than Last.fm accepts is skipped as *too old* (whether due or not);
2. a due play gets the played rule's verdict; an open play keeps waiting;
3. with `SCROBBLER_DEFER_TO_REALTIME` on, a play from while a real-time
   scrobbler was active is [left to it](#leaving-plays-to-a-real-time-scrobbler);
4. a play the played rule did not count is skipped;
5. a play a recent scrobble or the now playing track covers is a duplicate;
6. the rest are scrobbled in batches of 50 (or recorded as *would scrobble* in
   the dry run).

### Leaving plays to a real-time scrobbler

YouTube Music plays on one device at a time. So when a real-time scrobbler (a
desktop or browser scrobbler, an Android app) reported a track as now playing,
or scrobbled tracks, around a history play, that play happened on the device it
watches, and that scrobbler has already decided it, skips included. With
`SCROBBLER_DEFER_TO_REALTIME` on (the default), such a play is skipped as *left
to the real-time scrobbler*, whatever the played rule says and whether or not a
matching scrobble exists. Without it, a song skipped on the computer would still
be judged from the history, and counted whenever the bounds or a model allow it.

**The evidence.**

- **Now playing at a poll.** Every poll reads Last.fm's now playing track (one
  extra `user.getRecentTracks` request per poll). When it is the song on top of
  the history (same artist and title after normalisation), the real-time
  scrobbler was playing at the poll's time. When nothing plays, or another song
  does (a now playing still shown after the computer stopped, or a player that
  is not YouTube Music), it was idle at that time. Some real-time scrobblers
  never send now playing, so a poll that saw nothing only counts as idle once
  the real-time scrobbler was seen showing the song on top (in the last 30
  days).
- **Scrobbles that are not the scrobbler's own.** Each recent scrobble marks the
  start of a track on the other device. The [ledger](#the-ledger) tells the
  scrobbler's own scrobbles apart; they are no evidence.

**Active periods.** Evidence of activity forms one active period as long as
consecutive points are at most **10 minutes** apart and no poll in between saw
the real-time scrobbler idle. Its edges are explicit: it starts at the first
point and ends at the last one. A now playing sighting is a point at the poll's
time (this server's clock); a scrobble covers 30 seconds either way of its
timestamp, since the other device's clock may differ. A play is left to the
real-time scrobbler when its start window (from the last quiet poll to the poll
that first showed it) overlaps an active period.

| Situation | Result |
|---|---|
| Songs played and skipped on the computer between its scrobbles | all left to the real-time scrobbler |
| A phone session after the computer stopped | scrobbled normally: it starts after the last evidence of activity |
| Computer, then phone, then computer again within 10 minutes | the phone plays are scrobbled normally: the polls in between saw the real-time scrobbler idle (when it shows now playing) |
| An idle real-time scrobbler (no now playing, its last scrobble long ago) | every play is decided from the history as usual |
| A real-time scrobbler that never sends now playing | followed through its scrobbles: a skip between two of them is left to it when the second one is there by the time the skip is decided |

The 10 minutes come from the simulation's mixed-device scenario (see the last
comparison table above). With a real-time scrobbler that shows now playing the
gap hardly matters: every poll during its activity is a point of activity, and
the first poll that shows a phone play sees it idle. It matters for one that
only scrobbles: there 5 to 10 minutes do best, a shorter gap loses skips between
its scrobbles and a longer one leaves phone plays to it. Such a scrobbler covers
fewer skips anyway, since a skip is decided a minute after the next play
appeared, often before that play is scrobbled. Plays found in a long window (the
idle pace, an outage) overlap more activity, so a phone play that started right
after the computer stopped can be left to the real-time scrobbler when both fall
in one window.

This assumes the real-time scrobbler only scrobbles YouTube Music on the same
account. If it also scrobbles another player (a local player, another streaming
service), turn the setting off: plays on the phone while that player scrobbles
would otherwise be left to it. When Last.fm cannot be read, plays the played
rule counts wait as usual, and plays it does not count are skipped by the
played rule alone.

### The window

Before deciding, the scrobbler reads your recent scrobbles with
`user.getRecentTracks` and your **now playing** track (timestamped at the poll).
It reads only the time ranges around the plays being decided (nearby ranges
together, at most a day per request), so plays spread over many days need no
huge request. A play is a duplicate when a
scrobble of the same track lies within

> estimated start ± (track duration + poll gap)

where the poll gap is the time between the two polls that found the play (the
poll interval, or the outage length after a restart). Both edges are included:
for a 4-minute song and 2-minute polls a scrobble up to 6 minutes before or after
the estimate counts, one second more does not. A play of
[unknown timing](#timing-unknown) is compared with the scrobbles of a whole day
around its estimate (or its window, when that is longer), since it may have
been played long before it showed up. Each scrobble covers at most one
play; when several match, the closest one does. That holds across polls too: a
scrobble an earlier poll matched as a duplicate is never used again, and a play
matched to the now playing track claims the scrobble that track later becomes
(the closest one of the same track within its window). A song you really played
twice within one window can therefore only be told apart if both plays show up
as separate scrobbles.

### The ledger

Every play the scrobbler sends is recorded with the exact timestamp it sent and
the names Last.fm answered with. This ledger guarantees that:

- **a detected play is sent at most once**: plays go from *waiting* to a final
  decision once, and only waiting plays are sent;
- **its own scrobbles are not mistaken for real-time ones**: when the same song
  is detected again later, its earlier scrobble (recognised by exact timestamp
  and title) is not taken as covering the new play;
- **an unanswered request is not sent twice**: plays are marked *sending* before
  the request, and `track.scrobble` is only retried within a poll when Last.fm
  said it did not process it (HTTP 429, errors 11, 16 or 29, or no connection at
  all). After any other failure (a timeout, a 5xx, an unreadable answer) the
  next poll looks for the plays among the recent scrobbles (same timestamp, same
  title or artist, since Last.fm may correct one of them) and marks them
  scrobbled, or sends them again if they never arrived.

Only one poll runs at a time, also across processes: a poll holds a lock file
next to the database (`scrobbler.db.lock`), and a poll that finds it taken does
nothing.

### Matching

Artist and title matching builds on the [search normalisation](search-internals.md)
(Unicode folding, accents, `&`, bracket and "feat." handling):

| Detected play | Scrobble on Last.fm | Result |
|---|---|---|
| Queen - Bohemian Rhapsody | Queen - Bohemian Rhapsody - Remastered 2011 | duplicate (remaster, edit, single version and similar qualifiers are ignored) |
| Daft Punk, Pharrell Williams - Get Lucky | Daft Punk feat. Pharrell Williams - Get Lucky (feat. Pharrell Williams) | duplicate (one shared artist is enough; "feat." clauses are dropped) |
| same track, album *A* | same track, album *B* | duplicate (the album is ignored) |
| Rick Astley - Never Gonna Give You Up (Official Music Video) | Rick Astley - Never Gonna Give You Up | duplicate (an "Artist - " prefix and video brackets are dropped) |
| Oasis - Wonderwall (Live) | Oasis - Wonderwall | **not** a duplicate: another version, shown as a near miss |
| Song (Remix), (Acoustic), (Instrumental), (Sped Up), ... | Song | **not** a duplicate: another version, near miss |
| Johnny Cash - Hurt | Nine Inch Nails - Hurt | **not** a duplicate: another artist, near miss |
| Oasis - Live Forever | Oasis - Live Forever - Remastered | duplicate ("live" in the title itself is not a version) |

Version words only count inside brackets or a dash suffix ("- Live at
Wembley"), so a song called *Live Forever* stays itself. Credits with several
artists are split like in the search: on commas, `&`, `×`, `/`, "and", "with",
"vs", "feat." and similar, and on "x" and "+" only with spaces around them
("DJ Snake x Lil Jon"; *Max Richter*, *Lil Nas X* and *C+C Music Factory* stay
one artist). The full credit is kept as well, so *Florence + the Machine*
matches itself as a whole. The scrobbler sends the first credited artist and,
for music videos, the title without "(Official Video)"-style noise.

**Uploads.** For a video a user uploaded (`MUSIC_VIDEO_TYPE_UGC`), the credited
"artist" is the uploading channel, not the artist. The scrobbler takes artist
and title from an "Artist - Title" video title instead ("Real Artist - Song
(Lyrics)" becomes Real Artist, *Song*), and matches duplicates on that artist.
An upload whose title names no artist is skipped as *not a song with a known
artist*.

### Long outages

A play found after a long outage has a window as long as the outage. Its
[timing is unknown](#timing-unknown) (more than 30 minutes without a successful
read): it is laid back to back with the other plays of that poll, ending at the
poll, decided by the timing model, and checked against every scrobble of that
period (at least a day). Plays with a window over a day are read
together with the others when Last.fm allows; when their period holds more than
5,000 scrobbles (25 pages), they are skipped as *too many scrobbles to check*
instead of holding up the other plays, which are then checked on their own range.

### When Last.fm cannot be read

Without the recent scrobbles there is no way to rule out duplicates, so nothing
is scrobbled: the plays keep waiting and are decided by the next poll that can
read Last.fm. Plays that wait longer than Last.fm accepts are skipped as too old.

## Last.fm's rules

| Rule | How the scrobbler handles it |
|---|---|
| Tracks of 30 s or less are not scrobbles | Skipped at detection |
| A play counts after half the track or 4 minutes | The [listening bounds](#deciding-whether-a-play-counts) decide |
| Old timestamps are refused | The API docs only list "timestamp too far in the past" (ignored code 3). Last.fm is known to refuse scrobbles older than 14 days, so plays older than 14 days minus an hour are skipped as too old |
| Batches | `track.scrobble` with up to 50 plays per request, oldest first |
| Rate limit | At most one call every 0.25 s (Last.fm allows 5 per second per IP) |
| Retries | Network errors, HTTP 429 and 5xx, and API errors 8, 11, 16 and 29 are retried up to `LASTFM_MAX_RETRIES` times with exponential backoff, honouring `Retry-After`. `track.scrobble` is the exception: it is only retried after HTTP 429, errors 11, 16, 29 or a failed connection, because any other failure may already have been processed (see [the ledger](#the-ledger)) |
| Invalid session (error 9) | Plays go back to waiting and the failure is reported: reconnect in Settings |
| Ignored scrobbles (codes 1-4) | Recorded as skipped with Last.fm's code and message |
| Daily limit (ignored code 5) | Plays go back to waiting and are retried by later polls |
| Other errors | The batch is recorded as failed with the error |

## Failures and notifications

Each history read is retried like the playlist sync's YouTube Music calls: HTTP
403, 408, 429 and 5xx are tried again with exponential backoff (1 s, 2 s, 4 s,
...) up to `API_MAX_RETRIES` attempts in all, while 400 and 409 fail at once.
[Adaptive polling](#adaptive-polling) is the second layer: a read that still
fails slows the next polls down. The failure message is the sync's summary of
the error ("HTTP 403 - rate limit or auth expired", "HTTP 503", ...), not the
raw upstream answer, and an error without a message shows its type. An HTTP 401
means the browser authentication has expired; a signed-out session answers with
HTTP 200 and a "Sign in to view your history" page instead (ytmusicapi raises it
without a message). No retry fixes either: each is an expired session, a failure
of its own that is notified once and shows the dashboard's auth banner
(**YouTube Music session expired: reconnect.**), also on pages opened later,
until `browser.json` is replaced. See
[YouTube Music session signed out](troubleshooting.md#youtube-music-session-signed-out)
for reconnecting from a private window. Polling picks up again by itself once
the session works. A notice shown instead of the history, such as a paused
history, is reported with its own text.

Failures (history unreadable, authentication expired, Last.fm unreachable,
session rejected, not connected while live, a session of another account,
refused scrobbles, the daily limit) are shown on the Scrobbler tab and sent
through the dashboard notifications, [Apprise and the legacy
webhook](webhooks.md), once each time the kind of failure changes, so an outage
does not notify on every poll. The notification is a sync failure with sync type
`scrobbler`.

## Data and privacy

- `runtime/scrobbler.db` (SQLite) holds the last history snapshot, the poll log
  and whether a real-time scrobbler was playing at each poll (kept 30 days), and
  every detected play with its decision (kept 90 days). Like the other
  databases it is a record of your listening.
- The API secret and the session key live in `.env` like your other
  credentials; the session key is never sent to the browser. **Disconnect**
  removes it from `.env`; to revoke the access entirely, also remove the app on
  Last.fm under *Settings &rarr; Applications*. See the
  [Data & Security Model](security-model.md#2-lastfm-credentials).

## Limitations

- Replays of the song on top of the history are invisible unless the song moves
  into *Today* (for example played yesterday, then again today).
- More than about 200 different songs between two successful polls break the
  overlap with the snapshot; the snapshot is reset and those plays are lost.
- Clearing the YouTube Music history has the same effect.
- Timestamps are estimates: the plays found in one poll are spread evenly over
  its window (see the ± on each play). After long outages they can be hours off.
- Pauses and stops are invisible: a play whose end the history does not show is
  decided by the [end-unknown model](#end-unknown), which counts it.
- Offline plays found in a window that could hold them at a few seconds each
  (typically at the idle pace) look like fast skipping and are mostly skipped;
  see the offline rows of the simulation.
- A stale list served while nothing waits for confirmation looks like a quiet
  poll. The play it hides is found one poll later, with a window that starts
  too late, so its bounds (even *certain* ones) can be wrong. The flicker
  scenario of the simulation includes this case.
- Only plays recorded in the YouTube Music history are seen; incognito plays and
  a paused history are not.
- Leaving plays to a real-time scrobbler assumes it scrobbles YouTube Music
  only. A phone play whose start window also holds the start of activity on the
  computer (a device switch between two polls) is left to the real-time
  scrobbler.
