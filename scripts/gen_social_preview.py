#!/usr/bin/env python3
"""Generate the GitHub social preview card (``docs/assets/social-preview.png``).

Renders a branded 1280x640 card with the project logo, title and tagline using
Playwright + Chromium - the same rendering stack the dashboard screenshots use
(`tests/screenshots/generate.py`). The logo is read live from
``web/static/icons/icon.svg`` so the card never drifts from the app branding.

Usage (project root, venv active)::

    python scripts/gen_social_preview.py                 # -> docs/assets/social-preview.png
    python scripts/gen_social_preview.py --out card.png  # custom path

GitHub recommends social images be at least 640x320 (1280x640 for best
display); this script renders at 1280x640 @2x device scale. Upload the result
under the repo's Settings -> General -> Social preview.
"""

from __future__ import annotations

import argparse
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_SVG = ROOT / "web" / "static" / "icons" / "icon.svg"
DEFAULT_OUT = ROOT / "docs" / "assets" / "social-preview.png"

WIDTH = 1280
HEIGHT = 640
SUPERSAMPLE = 2
MAX_BYTES = 1_000_000

BG_DARK = "#09090b"
BG_PANEL = "#0e1624"
ACCENT = "#3b82f6"
ACCENT_SOFT = "#93b4f8"
TEXT_PRIMARY = "#f3f4f6"
TEXT_SECONDARY = "#a1a1aa"

TAGLINE = "Turns your Last.fm scrobbles into intelligently curated YouTube Music playlists - kept in sync automatically."
FEATURES = (
    "Smart official-upload matching",
    "Recency &amp; play-count weighting",
    "Weekly &amp; tag playlists",
    "Web dashboard &bull; Docker",
)


def _build_html(logo_svg: str) -> str:
    chips = "\n".join(f'<li><span class="dot"></span>{feature}</li>' for feature in FEATURES)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {WIDTH}px; height: {HEIGHT}px; }}
  body {{
    font-family: -apple-system, "Segoe UI", "Noto Sans", "DejaVu Sans", Arial, sans-serif;
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    overflow: hidden;
  }}
  .card {{
    position: relative;
    width: {WIDTH}px;
    height: {HEIGHT}px;
    background:
      radial-gradient(1100px 700px at 78% -10%, rgba(59,130,246,0.22), transparent 60%),
      radial-gradient(900px 600px at 8% 115%, rgba(59,130,246,0.12), transparent 55%),
      linear-gradient(135deg, {BG_PANEL} 0%, {BG_DARK} 60%);
    overflow: hidden;
  }}
  .frame {{
    position: absolute;
    left: 64px;
    right: 64px;
    top: 56px;
    bottom: 56px;
    display: flex;
    align-items: center;
    gap: 52px;
  }}
  .logo {{
    flex: 0 0 auto;
    width: 240px;
    height: 240px;
    filter: drop-shadow(0 18px 40px rgba(59,130,246,0.35));
  }}
  .logo svg {{ width: 100%; height: 100%; display: block; }}
  .content {{ flex: 1 1 auto; min-width: 0; }}
  .eyebrow {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-size: 21px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: {TEXT_SECONDARY};
    margin-bottom: 18px;
  }}
  .eyebrow .lf {{ color: {TEXT_PRIMARY}; }}
  .eyebrow .yt {{ color: {ACCENT_SOFT}; }}
  h1 {{
    font-size: 60px;
    line-height: 1.06;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-bottom: 20px;
  }}
  h1 .arrow {{ color: {ACCENT}; }}
  .tagline {{
    font-size: 25px;
    line-height: 1.42;
    color: {TEXT_SECONDARY};
    max-width: 700px;
    margin-bottom: 26px;
  }}
  ul {{
    list-style: none;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px 36px;
    max-width: 760px;
  }}
  li {{
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 22px;
    font-weight: 500;
    color: {TEXT_PRIMARY};
    white-space: nowrap;
  }}
  .dot {{
    flex: 0 0 auto;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: {ACCENT};
    box-shadow: 0 0 0 5px rgba(59,130,246,0.18);
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="frame">
      <div class="logo">{logo_svg}</div>
      <div class="content">
        <div class="eyebrow"><span class="lf">Last.fm</span> &rarr; <span class="yt">YouTube&nbsp;Music</span></div>
        <h1>Scrobbles, auto-synced<br>to <span class="arrow">YT Music</span></h1>
        <p class="tagline">{TAGLINE}</p>
        <ul>{chips}</ul>
      </div>
    </div>
  </div>
</body>
</html>"""


def main() -> int:
    """Render the social preview card to a PNG and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output PNG path (default: docs/assets/social-preview.png)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write(
            "playwright is not installed.\nInstall with:  pip install -e '.[web-docs]'  &&  python -m playwright install chromium\n",
        )
        return 2

    try:
        from PIL import Image
    except ImportError:
        sys.stderr.write("Pillow is not installed.\nInstall with:  pip install -e '.[web-docs]'\n")
        return 2

    if not LOGO_SVG.exists():
        sys.stderr.write(f"logo not found: {LOGO_SVG}\n")
        return 1

    logo_svg = LOGO_SVG.read_text(encoding="utf-8")
    html = _build_html(logo_svg)

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=SUPERSAMPLE,
        )
        page.set_content(html, wait_until="networkidle")
        hi_res = page.locator(".card").screenshot()
        browser.close()

    img = Image.open(BytesIO(hi_res)).convert("RGB")
    img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
    img.save(args.out, format="PNG", optimize=True)

    size = args.out.stat().st_size
    if size > MAX_BYTES:
        sys.stderr.write(
            f"warning: {args.out} is {size / 1_000_000:.2f} MB, above GitHub's 1 MB limit.\n",
        )
    print(f"wrote {args.out} ({WIDTH}x{HEIGHT}, supersampled {SUPERSAMPLE}x, {size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
