# Security Policy

## Supported versions

Security fixes are applied to the latest released version on the `main` branch
only. There are no long-term support branches; please upgrade to the most recent
release before reporting an issue.

| Version | Supported |
| ------- | --------- |
| Latest release (`main`) | &check; |
| Older releases | &times; |

## Trust model

This project is designed to run on a **single-user, trusted host or LAN**. By
design:

- The web dashboard has **no built-in authentication**.
- Credentials (YouTube Music auth headers, Last.fm API key, Flask secret,
  webhook URL) are stored **in plaintext on disk** (`browser.json`, `.env`,
  `cache/`, `config/`).

Keep the app on `localhost` or behind an authenticating reverse proxy before
exposing it to the internet. The full data and threat model is documented in
[docs/security-model.md](docs/security-model.md).

Issues that simply restate these documented design limitations are **not**
considered vulnerabilities.

## Scope

**In scope** (please report):

- Remote code execution, path traversal, or arbitrary file read/write.
- Injection flaws (command, template, SQL) reachable from untrusted input.
- Vulnerabilities in pinned dependencies that are exploitable as used here.
- Leaks of stored credentials beyond the documented plaintext-on-disk model
  (e.g. credentials exposed over the network or in logs).
- Cross-site scripting (XSS) in the web dashboard.

**Out of scope** (documented design decisions, not vulnerabilities):

- Lack of authentication on the web dashboard.
- Absence of CSRF protection on dashboard endpoints.
- Credentials stored in plaintext on the local disk.
- Issues that require an already-compromised host or local filesystem access.
- Findings from automated scanners without a demonstrated, reproducible impact.

## Safe harbor

I consider security research conducted in good faith to be authorised. If you
make a good-faith effort to comply with this policy, I will not pursue or
support legal action against you. Please avoid privacy violations, data
destruction, and any disruption to other people's systems while testing, and
only ever test against your own installation.

## A note from the maintainer

This is a hobby project maintained by **a single person** in their spare time. I
do my best to take security seriously, but there is no team, no on-call rotation,
and no guaranteed response window. Please be patient and kind - fixes happen when
time allows.

## Reporting a vulnerability

Please report security issues **privately** — do not open a public GitHub issue
for an undisclosed vulnerability.

1. Use GitHub's [private vulnerability reporting](https://github.com/Locko2901/lastfm-to-ytm/security/advisories/new)
   ("Report a vulnerability" on the repository's **Security** tab). This is the
   preferred channel.
2. If GitHub private reporting is unavailable to you, open a minimal public
   issue asking me to enable a private channel - **without** disclosing any
   vulnerability details.
3. Include enough detail to reproduce: affected version/commit, configuration,
   steps to trigger, and the impact you observed. A proof of concept or
   suggested fix is welcome but not required.

### What to expect

- **Acknowledgement:** within a few days, where possible.
- **Assessment:** I will confirm the report, determine severity, and keep you
  updated on remediation progress.
- **Disclosure:** once a fix is released, I will publish an advisory and credit
  reporters who wish to be named.

Please give me a reasonable opportunity to release a fix before any public
disclosure.
