"""Recognise YouTube Music answers that come from a signed-out session."""

from __future__ import annotations

from ytmusicapi.exceptions import YTMusicServerError

SIGNED_OUT_MARKERS = ("Sign in", "singleColumnBrowseResultsRenderer")


def is_signed_out(error: BaseException) -> bool:
    """Whether ``error`` means the session behind the auth file is signed out.

    A signed-out page says "Sign in" or lacks the signed-in layout
    (``singleColumnBrowseResultsRenderer``). For the signed-out history page,
    which holds neither the history nor a notice shelf, ytmusicapi raises
    ``YTMusicServerError(None)``.
    """
    if isinstance(error, YTMusicServerError) and not any(error.args):
        return True
    text = str(error)
    return any(marker in text for marker in SIGNED_OUT_MARKERS)
