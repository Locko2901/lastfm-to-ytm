from src.observability.http_status import (
    RATE_LIMIT_STATUSES,
    RETRYABLE_STATUSES,
    TERMINAL_STATUSES,
    extract_http_status,
    is_rate_limited,
    is_retryable,
)


def test_extract_status_with_space():
    assert extract_http_status("Server returned HTTP 403: Forbidden.") == 403


def test_extract_status_with_slash():
    assert extract_http_status("HTTP/500 internal error") == 500


def test_extract_status_no_separator():
    assert extract_http_status("HTTP404 not found") == 404


def test_extract_status_case_insensitive():
    assert extract_http_status("http 429 too many requests") == 429


def test_extract_status_missing_returns_none():
    assert extract_http_status("connection reset by peer") is None


def test_extract_status_ignores_bare_digits():
    assert extract_http_status("video dQw403WgXcQ played 403 times at 1403000000") is None


def test_extract_status_ignores_https():
    assert extract_http_status("failed to reach https://music.youtube.com") is None


def test_extract_status_first_match_wins():
    assert extract_http_status("HTTP 502 then HTTP 503") == 502


def test_is_retryable_for_retryable_statuses():
    for status in RETRYABLE_STATUSES:
        assert is_retryable(f"HTTP {status}: error") is True


def test_is_retryable_false_for_terminal_statuses():
    for status in TERMINAL_STATUSES:
        assert is_retryable(f"HTTP {status}: error") is False


def test_is_retryable_json_decode_fallback():
    assert is_retryable("Expecting value: line 1 column 1 (char 0)") is True


def test_is_retryable_unknown_message_false():
    assert is_retryable("totally unrelated failure") is False


def test_is_rate_limited_by_status():
    for status in RATE_LIMIT_STATUSES:
        assert is_rate_limited(f"HTTP {status}: throttled") is True


def test_is_rate_limited_by_text_fallback():
    assert is_rate_limited("You have hit the rate limit, slow down") is True


def test_is_rate_limited_false_for_other_status():
    assert is_rate_limited("HTTP 500: internal error") is False


def test_is_rate_limited_false_for_unrelated():
    assert is_rate_limited("connection refused") is False
