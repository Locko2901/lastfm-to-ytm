"""Custom Babel extractor for JavaScript files.

Extracts _("...") and _('...') calls from JS source files.
"""

from __future__ import annotations

import re

_MSG_RE = re.compile(
    r"""\b_\(\s*"""
    r"""(?:"""
    r'''"((?:[^"\\]|\\.)*)"'''  # double-quoted
    r"""|"""
    r"""'((?:[^'\\]|\\.)*)'"""  # single-quoted
    r""")"""
)


def extract_js(fileobj, keywords, comment_tags, options):
    """Yield (lineno, funcname, message, comments) from a JS file."""
    encoding = options.get("encoding", "utf-8")
    for lineno, line in enumerate(fileobj, 1):
        if isinstance(line, bytes):
            line = line.decode(encoding)
        for match in _MSG_RE.finditer(line):
            msg = match.group(1) or match.group(2)
            if msg:
                msg = msg.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n")
                yield lineno, "_", msg, []
