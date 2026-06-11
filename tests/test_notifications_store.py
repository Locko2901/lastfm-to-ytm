"""Unit tests for the notification store (``web.services.notifications``)
and its HTTP routes (``web.routes.notifications``).

The store is pure + file-backed (broadcasts go to an in-memory event bus with
no subscribers during tests), so these are fully deterministic against the
``web_paths`` fixture. See the "What the web tests deliberately skip" section
in ``docs/testing.md`` for the full list of what is and isn't covered here.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("flask")

from web.services import notifications as notif


@pytest.mark.usefixtures("web_paths")
def test_add_and_list():
    entry = notif.add("hello", type_="success", source="test")
    assert entry["message"] == "hello"
    assert entry["type"] == "success"

    listed = notif.list_all()
    assert len(listed["notifications"]) == 1
    assert listed["notifications"][0]["id"] == entry["id"]
    assert listed["last_seen_at"] is None


@pytest.mark.usefixtures("web_paths")
def test_add_empty_message_raises():
    with pytest.raises(ValueError):
        notif.add("   ")


@pytest.mark.usefixtures("web_paths")
def test_add_invalid_type_coerced_to_info():
    entry = notif.add("hi", type_="bogus")
    assert entry["type"] == "info"


@pytest.mark.usefixtures("web_paths")
def test_add_truncates_long_message():
    entry = notif.add("x" * 600)
    assert len(entry["message"]) == 500


@pytest.mark.usefixtures("web_paths")
def test_add_dedupes_identical_within_5s():
    first = notif.add("dup", type_="info", source="s")
    second = notif.add("dup", type_="info", source="s")
    assert first["id"] == second["id"]
    assert len(notif.list_all()["notifications"]) == 1


@pytest.mark.usefixtures("web_paths")
def test_list_newest_first_and_prunes_expired(tmp_path):
    now = datetime.now(UTC)
    old = (now - timedelta(days=40)).isoformat()
    recent_old = (now - timedelta(hours=2)).isoformat()
    recent_new = now.isoformat()

    (tmp_path / ".notifications.json").write_text(
        json.dumps(
            {
                "notifications": [
                    {"id": "expired", "message": "old", "type": "info", "created_at": old, "source": None},
                    {"id": "a", "message": "older", "type": "info", "created_at": recent_old, "source": None},
                    {"id": "b", "message": "newer", "type": "info", "created_at": recent_new, "source": None},
                ],
                "last_seen_at": None,
            }
        )
    )

    listed = notif.list_all()["notifications"]
    assert [n["id"] for n in listed] == ["b", "a"]


@pytest.mark.usefixtures("web_paths")
def test_delete_returns_bool():
    entry = notif.add("to delete")
    assert notif.delete(entry["id"]) is True
    assert notif.delete(entry["id"]) is False
    assert notif.list_all()["notifications"] == []


@pytest.mark.usefixtures("web_paths")
def test_clear_removes_all():
    notif.add("one")
    time.sleep(0.001)
    notif.add("two", source="x")
    notif.clear()
    assert notif.list_all()["notifications"] == []


@pytest.mark.usefixtures("web_paths")
def test_mark_read_sets_last_seen():
    notif.add("seen me")
    seen = notif.mark_read()
    assert notif.list_all()["last_seen_at"] == seen


def test_route_list_empty(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    assert resp.get_json()["notifications"] == []


def test_route_create_requires_message(client):
    resp = client.post("/api/notifications", json={})
    assert resp.status_code == 400


def test_route_create_returns_201(client):
    resp = client.post("/api/notifications", json={"message": "hi", "type": "success"})
    assert resp.status_code == 201
    assert resp.get_json()["message"] == "hi"


def test_route_clear(client):
    client.post("/api/notifications", json={"message": "hi"})
    resp = client.post("/api/notifications/clear")
    assert resp.get_json() == {"status": "ok"}
    assert client.get("/api/notifications").get_json()["notifications"] == []


def test_route_mark_read(client):
    resp = client.post("/api/notifications/read")
    assert "last_seen_at" in resp.get_json()


def test_route_delete_missing_returns_404(client):
    resp = client.delete("/api/notifications/nonexistent")
    assert resp.status_code == 404


def test_route_delete_existing(client):
    created = client.post("/api/notifications", json={"message": "bye"}).get_json()
    resp = client.delete(f"/api/notifications/{created['id']}")
    assert resp.get_json() == {"status": "ok"}
