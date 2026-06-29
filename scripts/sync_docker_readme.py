#!/usr/bin/env python3
"""Mirror the shared sections of README.md into README.docker.md.

``README.md`` is the single source of truth. Sections that should be identical
on GitHub and Docker Hub are wrapped in ``<!-- docker-sync:start -->`` /
``<!-- docker-sync:end -->`` markers in *both* files. Everything outside the
markers (badges, the absolute image URL, the "Supported tags" section, the
footer, etc.) is platform-specific and left untouched.

Usage::

    python scripts/sync_docker_readme.py           # rewrite README.docker.md
    python scripts/sync_docker_readme.py --check    # fail if out of sync (CI)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "README.md"
TARGET = ROOT / "README.docker.md"

START = "<!-- docker-sync:start -->"
END = "<!-- docker-sync:end -->"
BLOCK_RE = re.compile(
    re.escape(START) + r"\n(?P<body>.*?)\n" + re.escape(END),
    re.DOTALL,
)


def extract_blocks(text: str) -> list[str]:
    """Return the bodies of all docker-sync blocks found in ``text``."""
    return [m.group("body") for m in BLOCK_RE.finditer(text)]


def render(target_text: str, source_blocks: list[str]) -> str:
    """Replace each docker-sync block in ``target_text`` with the source body."""
    blocks = iter(source_blocks)

    def replace(_match: re.Match[str]) -> str:
        return f"{START}\n{next(blocks)}\n{END}"

    return BLOCK_RE.sub(replace, target_text)


def main() -> int:
    """Sync (or check) README.docker.md against README.md; return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if README.docker.md is out of sync (does not write)",
    )
    args = parser.parse_args()

    source_text = SOURCE.read_text(encoding="utf-8")
    target_text = TARGET.read_text(encoding="utf-8")

    source_blocks = extract_blocks(source_text)
    target_count = len(extract_blocks(target_text))

    if len(source_blocks) != target_count:
        print(
            f"docker-sync marker mismatch: {SOURCE.name} has {len(source_blocks)} shared block(s) but {TARGET.name} has {target_count}.",
            file=sys.stderr,
        )
        return 1

    updated = render(target_text, source_blocks)

    if updated == target_text:
        return 0

    if args.check:
        print(
            f"{TARGET.name} is out of sync with {SOURCE.name}. Run: python scripts/sync_docker_readme.py",
            file=sys.stderr,
        )
        return 1

    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.name} from {SOURCE.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
