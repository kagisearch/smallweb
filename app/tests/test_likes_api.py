from collections import OrderedDict

import pytest


def test_unlike_decrements_selected_reaction(client, app_module, monkeypatch):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 3), ("🔥", 2)])}
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: None)

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "url": url,
        "emoji": "👍",
        "reaction_count": 2,
        "likes_total": 4,
    }
    assert app_module.likes_dict[url] == OrderedDict([("👍", 2), ("🔥", 2)])


def test_unlike_removes_zero_count_reaction_and_empty_url(
    client, app_module, monkeypatch
):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 1)])}
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: None)

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert response.get_json()["reaction_count"] == 0
    assert response.get_json()["likes_total"] == 0
    assert url not in app_module.likes_dict


def test_unlike_absent_reaction_is_idempotent(client, app_module, monkeypatch):
    url = "https://example.com/post"
    reactions = OrderedDict([("🔥", 2)])
    app_module.likes_dict = {url: reactions}

    def unexpected_side_effect():
        raise AssertionError("an absent reaction must not trigger side effects")

    monkeypatch.setattr(app_module, "_rebuild_liked_cache", unexpected_side_effect)
    monkeypatch.setattr(app_module, "save_likes", unexpected_side_effect)

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "url": url,
        "emoji": "👍",
        "reaction_count": 0,
        "likes_total": 2,
    }
    assert app_module.likes_dict[url] is reactions


def test_unlike_persists_changed_reaction(client, app_module, monkeypatch):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 2)])}
    saves = []
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: saves.append(True))

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert saves == [True]


def test_unlike_rebuilds_liked_cache_after_change(client, app_module, monkeypatch):
    url = "https://a.example/1"
    app_module.likes_dict = {url: OrderedDict([("👍", 2)])}
    feed_rebuilds = []
    monkeypatch.setattr(app_module, "save_likes", lambda: None)
    monkeypatch.setattr(
        app_module, "generate_liked_feed", lambda: feed_rebuilds.append(True)
    )

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert [entry.link for entry in app_module.urls_liked_cache] == [url]
    assert feed_rebuilds == [True]


def test_unlike_decrements_supplied_emoji(client, app_module, monkeypatch):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 4), ("🔥", 2)])}
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: None)

    response = client.post("/api/unlike", json={"url": url, "emoji": "🔥"})

    assert response.status_code == 200
    assert response.get_json()["emoji"] == "🔥"
    assert response.get_json()["reaction_count"] == 1
    assert response.get_json()["likes_total"] == 5
    assert app_module.likes_dict[url] == OrderedDict([("👍", 4), ("🔥", 1)])


def test_unlike_invalid_emoji_matches_like_fallback(client, app_module, monkeypatch):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 2)])}
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: None)

    response = client.post(
        "/api/unlike", json={"url": url, "emoji": "not-an-emoji"}
    )

    assert response.status_code == 200
    assert response.get_json()["emoji"] == "👍"
    assert response.get_json()["reaction_count"] == 1


@pytest.mark.parametrize("payload", [{}, {"url": ""}, {"url": "   "}])
def test_unlike_rejects_missing_or_empty_url(client, payload):
    response = client.post("/api/unlike", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "missing url"}


def test_unlike_rejects_malformed_json(client, app_module, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "PROPAGATE_EXCEPTIONS", False)

    response = client.post("/api/unlike", data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": "expected JSON object",
    }


def test_unlike_never_creates_negative_count(client, app_module, monkeypatch):
    url = "https://example.com/post"
    app_module.likes_dict = {url: OrderedDict([("👍", 0)])}
    monkeypatch.setattr(app_module, "_rebuild_liked_cache", lambda: None)
    monkeypatch.setattr(app_module, "save_likes", lambda: None)

    response = client.post("/api/unlike", json={"url": url})

    assert response.status_code == 200
    assert response.get_json()["reaction_count"] == 0
    assert response.get_json()["likes_total"] == 0
    assert url not in app_module.likes_dict
