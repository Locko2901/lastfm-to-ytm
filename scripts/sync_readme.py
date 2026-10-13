#!/usr/bin/env python3
"""Mirror the shared sections of README.md into README.docker.md and docs/index.md.

``README.md`` is the single source of truth. Each shared section is wrapped in
``<!-- sync:start NAME -->`` / ``<!-- sync:end -->`` markers, and a target
holds the same markers around each section it mirrors. Everything outside the
markers (badges, the image path, Docker's "Supported tags" section, the docs
grid card, etc.) is specific to that file and left untouched.

Links into the docs site are absolute in README.md, because Docker Hub cannot
resolve relative ones. docs/index.md gets them back as relative ``page.md``
links, so ``mkdocs build --strict`` checks them.

Usage::

    python scripts/sync_readme.py           # rewrite the targets
    python scripts/sync_readme.py --check   # fail if a target is out of sync (CI)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "README.md"

BLOCK_RE = re.compile(
    r"<!-- sync:start (?P<name>[a-z][a-z0-9-]*) -->\n(?P<body>.*?)\n<!-- sync:end -->",
    re.DOTALL,
)
DOCS_URL_RE = re.compile(r"https://locko2901\.github\.io/lastfm-to-ytm/(?:(?P<page>[a-z0-9-]+)/)?(?P<anchor>#[\w-]+)?")


def to_docs_links(body: str) -> str:
    """Turn absolute links into the docs site into relative ``page.md`` links."""
    return DOCS_URL_RE.sub(lambda m: f"{m['page'] or 'index'}.md{m['anchor'] or ''}", body)


TARGETS: dict[Path, Callable[[str], str]] = {
    ROOT / "README.docker.md": lambda body: body,
    ROOT / "docs" / "index.md": to_docs_links,
}


def extract_blocks(text: str) -> list[tuple[str, str]]:
    """Return the ``(name, body)`` of every sync block found in ``text``."""
    return [(m["name"], m["body"]) for m in BLOCK_RE.finditer(text)]


def render(target_text: str, source_blocks: dict[str, str], transform: Callable[[str], str]) -> str:
    """Replace each sync block in ``target_text`` with the transformed source body of the same name."""

    def replace(match: re.Match[str]) -> str:
        name = match["name"]
        return f"<!-- sync:start {name} -->\n{transform(source_blocks[name])}\n<!-- sync:end -->"

    return BLOCK_RE.sub(replace, target_text)


def main() -> int:
    """Sync (or check) every target against README.md; return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a target is out of sync (does not write)",
    )
    args = parser.parse_args()

    source_list = extract_blocks(SOURCE.read_text(encoding="utf-8"))
    source_blocks = dict(source_list)
    if len(source_blocks) != len(source_list):
        print(f"sync marker error: {SOURCE.name} names a section more than once.", file=sys.stderr)
        return 1

    target_texts = {target: target.read_text(encoding="utf-8") for target in TARGETS}
    used: set[str] = set()
    for target, text in target_texts.items():
        names = {name for name, _ in extract_blocks(text)}
        unknown = sorted(names - source_blocks.keys())
        if unknown:
            print(f"sync marker error: {target.relative_to(ROOT)} has section(s) {SOURCE.name} lacks: {', '.join(unknown)}.", file=sys.stderr)
            return 1
        used |= names

    unused = [name for name in source_blocks if name not in used]
    if unused:
        print(f"sync marker error: no target mirrors {SOURCE.name} section(s): {', '.join(unused)}.", file=sys.stderr)
        return 1

    stale = []
    for target, transform in TARGETS.items():
        text = target_texts[target]
        updated = render(text, source_blocks, transform)
        if updated == text:
            continue
        stale.append(target.relative_to(ROOT))
        if not args.check:
            target.write_text(updated, encoding="utf-8")
            print(f"Updated {target.relative_to(ROOT)} from {SOURCE.name}.")

    if args.check and stale:
        print(
            f"{', '.join(map(str, stale))} out of sync with {SOURCE.name}. Run: python scripts/sync_readme.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
