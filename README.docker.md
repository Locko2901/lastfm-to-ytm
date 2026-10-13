# Last.fm → YouTube Music

<!-- sync:start intro -->
**A self-hosted music dashboard that turns your Last.fm scrobbles into intelligently curated YouTube Music playlists - and keeps them that way.**

YouTube Music's *Replay Mix* was my go-to for playing my current favorites - whatever I'd actually been listening to most lately. The problem is how little it really does: hit shuffle and you get one random track, then the rest drop straight back into their original order, there's no way to blacklist a song you're sick of, and there's no insight into how it picks anything. So I rebuilt it properly. This tool reads your Last.fm history, finds the right *official* upload on YouTube Music for each track (skipping live versions, remixes, nightcore, sped-up, 8D, etc.), weights the result by what you've *actually* been listening to lately, and keeps the playlist in sync on whatever schedule you set - with every step documented and fully configurable, a real blacklist to drop tracks for good, and a lot more than a single playlist.

On top of that you get **weekly snapshot playlists** that archive your listening habits, **custom playlists** built from your Last.fm tags, chosen artists, discovery recommendations, or listening-history filters, and a **full web dashboard** with a first-launch setup wizard, built-in scheduler, sync console, history database, notifications, encrypted backup/restore, and PWA install - so after the initial 5-minute install you never have to touch a terminal or config file again.
<!-- sync:end -->

![Dashboard Preview](https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/docs/screenshots/dashboard.png)

<!-- sync:start get-started -->
## Get started in ~5 minutes

The Docker setup includes a web dashboard, a setup wizard, and a built-in scheduler. No terminal needed after install.

&rarr; **[Quick Start (Docker)](https://locko2901.github.io/lastfm-to-ytm/quickstart/)**

Using Portainer or Unraid? Paste the [compose template](https://locko2901.github.io/lastfm-to-ytm/compose/) into your stack editor instead.

Prefer not to use Docker? There's a [standalone CLI install](https://locko2901.github.io/lastfm-to-ytm/cli-install/) too. It runs the same sync engine; you handle scheduling yourself with cron/systemd. The Docker path is recommended for almost everyone.
<!-- sync:end -->

## Supported tags

- `latest` - newest stable release
- `X.Y.Z`, `X.Y`, `X` - pinned release versions
- `dev` - latest build from `main` (may be unstable)

Images are published for `linux/amd64` and `linux/arm64`.

<!-- sync:start highlights -->
## Highlights

**Playlists**

- **A main playlist that follows what you're into right now**, weighted by recency and play count - or by lifetime plays plus recency in [full-history mode](https://locko2901.github.io/lastfm-to-ytm/local-history/).
- **Weekly snapshot playlists** so you build a long-term archive of how your taste evolves.
- **[Custom playlists](https://locko2901.github.io/lastfm-to-ytm/tag-playlists/)**, each kept in sync on its own:
    - *Tag-based* - e.g. *"Breakcore Mix"*, *"Chill Electronic"*, auto-filled from your Last.fm tags
    - *Artist-based* - every found song by the artists you choose
    - *Discovery* - songs you've never scrobbled, recommended from your top artists and tracks
    - *Template/filter* - top tracks in a window, forgotten favorites, seasonal, and more, built from composable history filters
- **Export any playlist** to M3U, CSV, JSON, or your own format.

**Matching you can see and control**

- **Smart matching** that prefers official Songs over user uploads and rejects nightcore, sped-up, slowed, 8D, etc.
- **[Overrides and blacklists](https://locko2901.github.io/lastfm-to-ytm/overrides/)** - pin the right upload for a track, drop a song or a whole artist for good, and fix misses from the Not Found tab in one click.
- **Dry-run preview** of exactly what a sync would add, remove, and reorder before anything changes on YouTube Music.
- **See why each track made the cut** - a score graph of the playlist, near misses that just missed the cutoff, and an optional [history database](https://locko2901.github.io/lastfm-to-ytm/history/) of every sync and match.

**Runs itself**

- **Web dashboard and setup wizard** to configure everything, YouTube Music auth included, and watch syncs run live - no terminal needed after install.
- **Built-in scheduler and notifications** through [Apprise](https://locko2901.github.io/lastfm-to-ytm/webhooks/#notifications-apprise) to Discord, ntfy, Telegram, and 100+ other services.
- **[Encrypted backup/restore](https://locko2901.github.io/lastfm-to-ytm/teleporter/)** to move your whole setup to a new server.

**The other direction (optional)**

- **[History scrobbler](https://locko2901.github.io/lastfm-to-ytm/scrobbler/)** that scrobbles what you play in the YouTube Music apps (e.g. on your phone) by reading your YouTube Music history. It skips plays a real-time scrobbler already sent, and the Scrobbler tab shows what it did with every play. Off by default, with a dry run to check its decisions first.
<!-- sync:end -->

<!-- sync:start documentation -->
## Documentation

Full documentation lives at **[locko2901.github.io/lastfm-to-ytm](https://locko2901.github.io/lastfm-to-ytm/)**.
<!-- sync:end -->

**Updating?** See the [update guide](https://locko2901.github.io/lastfm-to-ytm/docker-reference/#updating).

## Source & License

Source code: **[github.com/Locko2901/lastfm-to-ytm](https://github.com/Locko2901/lastfm-to-ytm)**

MIT licensed.
