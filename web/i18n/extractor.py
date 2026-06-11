"""Custom Babel extractor for JavaScript files.

Extracts _("...") and _('...') calls from JS source files.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

_MSG_RE = re.compile(
    r"""\b_\(\s*"""
    r"""(?:"""
    r'''"((?:[^"\\]|\\.)*)"'''  # double-quoted
    r"""|"""
    r"""'((?:[^'\\]|\\.)*)'"""  # single-quoted
    r""")"""
)


def extract_js(fileobj: Any, _keywords: Any, _comment_tags: Any, options: Any) -> Iterator[tuple[int, str, str, list[str]]]:
    """Yield (lineno, funcname, message, comments) from a JS file."""
    encoding = options.get("encoding", "utf-8")
    for lineno, raw_line in enumerate(fileobj, 1):
        line = raw_line.decode(encoding) if isinstance(raw_line, bytes) else raw_line
        for match in _MSG_RE.finditer(line):
            msg = match.group(1) or match.group(2)
            if msg:
                msg = msg.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n")
                yield lineno, "_", msg, []
