# Webhooks

Get notified when a sync completes or fails. The webhook sends a POST request with sync results to any URL you configure.

**Discord** is the only tested provider, but any endpoint that accepts JSON POST requests should work (Slack, ntfy, custom servers, etc.).

---

## Configuration

**Docker**: Open **Settings** and scroll to the **Webhooks** section. Enter your webhook URL, choose when to send notifications, and use the **Test** button to verify.

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
