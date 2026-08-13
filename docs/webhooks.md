# Webhooks

Get notified when a sync completes or fails.

The recommended way to receive notifications is **[Apprise](#notifications-apprise)**,
which delivers to 100+ services (Discord, ntfy, Slack, Telegram, Gotify, …) and
supports **multiple targets** at once. The original single-URL
**[generic webhook](#legacy-generic-webhook)** still works but is **deprecated**.

---

## Notifications (Apprise)

Configure one or more [Apprise service URLs](https://appriseit.com/services/)
and each sync result is delivered to all of them.

**Docker**: Open **Settings &rarr; Notifications (Apprise)**, paste your URL(s),
choose when to send, and use the **Test** button to verify.

**CLI**: Add to your `.env`:

```bash
# Space- or comma-separated. Multiple targets supported.
APPRISE_URLS=discord://webhook_id/webhook_token ntfy://host/topic
APPRISE_EVENTS=all    # "all" = every sync, "error" = failures only
```

| Variable | Default | Description |
|----------|---------|-------------|
| `APPRISE_URLS` | *(empty)* | One or more Apprise URLs, separated by spaces or commas. Leave empty to disable. |
| `APPRISE_EVENTS` | `error` | When to send: `all` (every sync) or `error` (failures only) |

Apprise URLs are operator-configured and intentionally support self-hosted LAN
services (ntfy, Gotify, …), so no public-address SSRF check is applied to them.

### Managing targets in the dashboard

Under **Settings &rarr; Notifications (Apprise)** each saved URL appears as a row
with icon actions:

- **Test** (paper plane) - send a test notification to that one target.
- **Enable / Disable** - toggle a target without deleting it. Disabled
  targets are greyed out, tagged `(disabled)`, and skipped when syncing (stored
  with a leading `!` in `APPRISE_URLS`).
- **Delete** (trash) - remove the target.

**Double-click a saved URL** to edit it inline; press <kbd>Enter</kbd> to save or
<kbd>Esc</kbd> to cancel. Use the input row's **Test** button to try a URL
*before* adding it with **+**.

### Example: self-hosted ntfy with an access token

```bash
# ntfy:// = HTTP, ntfys:// = HTTPS. Token goes in the userinfo position.
APPRISE_URLS=ntfy://tk_youraccesstoken@10.10.10.10:8082/your-topic
```

This replaces the older pattern of POSTing a generic JSON webhook to ntfy with a
base64 `?auth=` query string - Apprise sends a native ntfy notification and
handles token auth for you.

---

## Legacy generic webhook

!!! warning "Deprecated"
    The generic single-URL webhook below is superseded by Apprise and will be
    removed in a future release. It still works for existing setups; leave
    `WEBHOOK_URL` empty to disable it.

The webhook sends a POST request with sync results to any URL you configure.
Any endpoint that accepts JSON POST requests works (Slack, ntfy, custom servers),
and **Discord** is auto-detected and formatted as a rich embed.

## Configuration

**Docker**: Open **Settings** and scroll to the **Webhook (Legacy)** section. Enter your webhook URL, choose when to send notifications, and use the **Test** button to verify.

**CLI**: Add to your `.env`:

```bash
WEBHOOK_URL=https://discord.com/api/webhooks/123456/abcdef
WEBHOOK_EVENTS=all    # "all" = success + error, "error" = failures only
```

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URL` | *(empty)* | Webhook endpoint URL. Leave empty to disable. |
| `WEBHOOK_EVENTS` | `error` | When to send: `all` (every sync) or `error` (failures only) |
| `WEBHOOK_ALLOW_PRIVATE` | `false` | Allow URLs resolving to private/LAN/localhost addresses. Off by default to prevent SSRF. |

---

## Private / LAN receivers

Before sending, the URL is validated: it must be `http`/`https` and, by default,
must resolve to a **public** IP address. This blocks server-side request forgery
(SSRF) where a crafted URL could probe internal services.

If your receiver runs on your own network - a self-hosted
[ntfy](https://ntfy.sh/) or [Gotify](https://gotify.net/) instance, a container
name, `localhost`, `192.168.x.x`, etc. - set `WEBHOOK_ALLOW_PRIVATE=true`
(or tick **Allow private/LAN webhook URLs** in **Settings &rarr; Webhooks**).
Leave it off when pointing at public services like Discord or ntfy.sh.

---

## Payload

Each webhook payload includes:

- **Status** - `success` or `error`
- **Sync type** - `main` or `tags`
- **Timestamp** - ISO 8601 timestamp of the sync
- **Tracks resolved / missed / total**
- **Duration** - wall-clock sync time in seconds
- **Cache hits / misses** - with hit rate percentage
- **API searches** - number of YouTube Music queries made
- **Playlist link** (on success)
- **Error details** (on failure, truncated to 500 characters)

## Discord Format

Discord webhooks are auto-detected by URL (matching `discord.com/api/webhooks/` or `discordapp.com/api/webhooks/`) and formatted as rich embeds with color-coded status:

- :green_circle: **Green** for success
- :red_circle: **Red** for errors

Other endpoints receive a plain JSON object with the same fields. Error details in Discord embeds are truncated to 1000 characters.
