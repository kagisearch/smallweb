"""Tests for the prefetch deck: next-post selection and the /api/deck payload."""
import json

from conftest import entry


# --- _pick_next_entry ---------------------------------------------------------

def test_next_entry_never_repeats_current(app_module):
    cache = app_module.urls_cache
    current = cache[0].link
    for _ in range(50):
        nxt = app_module._pick_next_entry(cache, current, set(), [], "", 0)
        assert nxt.link != current


def test_next_entry_prefers_unseen(app_module):
    cache = app_module.urls_cache
    current = cache[0].link
    # Everything but the last entry has been seen already.
    seen = {app_module._hash_url(e.link) for e in cache[:-1]}
    for _ in range(20):
        nxt = app_module._pick_next_entry(cache, current, seen, [], "", 0)
        assert nxt.link == cache[-1].link


def test_next_entry_falls_back_when_everything_seen(app_module):
    cache = app_module.urls_cache
    current = cache[0].link
    seen = {app_module._hash_url(e.link) for e in cache}
    nxt = app_module._pick_next_entry(cache, current, seen, [], "", 0)
    assert nxt is not None and nxt.link != current


def test_next_entry_empty_cache_returns_none(app_module):
    assert app_module._pick_next_entry([], "https://x.example", set(), [], "", 0) is None


def test_next_entry_recent_mode_walks_in_order(app_module):
    cache = app_module.urls_cache
    assert app_module._pick_next_entry(cache, cache[1].link, set(), [], "", 6).link == cache[2].link
    # Last entry has nothing after it.
    assert app_module._pick_next_entry(cache, cache[-1].link, set(), [], "", 6) is None


def test_cat_filter_restricts_pool(app_module):
    filtered = app_module._apply_cat_filters(app_module.urls_cache, "art", set())
    links = {e.link for e in filtered}
    assert links == {"https://c.example/3", "https://d.example/4"}
    for _ in range(20):
        nxt = app_module._pick_next_entry(filtered, "https://c.example/3", set(), [], "art", 0)
        assert nxt.link == "https://d.example/4"


def test_excluded_cats_are_dropped(app_module):
    filtered = app_module._apply_cat_filters(app_module.urls_cache, "", {"tech"})
    links = {e.link for e in filtered}
    assert "https://a.example/1" not in links
    assert "https://c.example/3" in links


# --- /api/deck ----------------------------------------------------------------

def test_deck_returns_requested_count_of_distinct_posts(client):
    res = client.get("/api/deck?count=4&url=https://a.example/1")
    assert res.status_code == 200
    posts = res.get_json()["posts"]
    assert len(posts) == 4
    links = [p["url"] for p in posts]
    assert len(set(links)) == 4
    assert "https://a.example/1" not in links


def test_deck_stops_at_available_posts(client):
    # Comics mode has two entries, so a deck of five can only ever yield two.
    res = client.get("/api/deck?comic&count=5&url=https://comic.example/1")
    posts = res.get_json()["posts"]
    assert len(posts) == 1
    assert posts[0]["url"] == "https://comic.example/2"


def test_deck_respects_category_filter(client):
    res = client.get("/api/deck?cat=art&count=3&url=https://c.example/3")
    posts = res.get_json()["posts"]
    assert [p["url"] for p in posts] == ["https://d.example/4"]


def test_deck_chains_next_links(client):
    res = client.get("/api/deck?count=3&url=https://a.example/1")
    posts = res.get_json()["posts"]
    # A post's no-JS next link must land on exactly the page the deck would push.
    for i, post in enumerate(posts[:-1]):
        assert post["next_link"] == posts[i + 1]["page_url"]
    # The last queued post has nothing behind it yet.
    assert posts[-1]["next_link"] is None


def test_deck_empty_cache_returns_404(client, app_module):
    app_module.urls_cache = []
    res = client.get("/api/deck?count=3")
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_deck_rejects_non_iframe_modes(client, app_module):
    app_module.urls_gh_cache = [app_module.urls_cache[0]]
    res = client.get("/api/deck?gh&count=3")
    assert res.status_code == 400


def test_deck_count_is_clamped(client, app_module):
    res = client.get("/api/deck?count=999&url=https://a.example/1")
    assert len(res.get_json()["posts"]) <= app_module.DECK_MAX


def test_deck_bad_count_falls_back_to_default(client):
    res = client.get("/api/deck?count=abc&url=https://a.example/1")
    assert res.status_code == 200
    assert len(res.get_json()["posts"]) == 3


# --- deck payload -------------------------------------------------------------

def test_deck_slots_carry_the_posts_own_url(client):
    res = client.get("/api/deck?count=1&url=https://a.example/1")
    post = res.get_json()["posts"][0]
    slots = post["slots"]
    assert set(slots) >= {
        "reactions", "post-cats", "url-display-phone",
        "share-dropdown", "mobile-more-dropdown", "flag-dropdown", "flag-btn-label",
    }
    # The like form must post the post's own URL, not the one we came from.
    assert f'value="{post["url"]}"' in slots["reactions"]
    assert "https://a.example/1" not in slots["reactions"]
    assert post["domain"] in slots["url-display-phone"]


def test_deck_marks_flagged_posts(client, app_module):
    app_module.flagged_content_dict = {"https://b.example/2": 5}
    res = client.get("/api/deck?count=4&url=https://a.example/1")
    posts = {p["url"]: p for p in res.get_json()["posts"]}
    assert posts["https://b.example/2"]["flagged"] is True
    for url, post in posts.items():
        if url != "https://b.example/2":
            assert post["flagged"] is False


def test_deck_reports_reaction_counts(client, app_module):
    app_module.likes_dict = {"https://b.example/2": {"👍": 3}}
    res = client.get("/api/deck?count=4&url=https://a.example/1")
    posts = {p["url"]: p for p in res.get_json()["posts"]}
    assert ">3<" in posts["https://b.example/2"]["slots"]["reactions"]


def test_post_cats_slot_is_empty_string_without_categories(client):
    # .post-cats:empty hides the container, so stray whitespace would leave a
    # visible gap in the header for uncategorized posts.
    res = client.get("/api/deck?count=4&url=https://a.example/1")
    posts = {p["url"]: p for p in res.get_json()["posts"]}
    assert posts["https://e.example/5"]["slots"]["post-cats"] == ""


def test_deck_similar_hidden_without_embedding(client):
    res = client.get("/api/deck?count=1&url=https://a.example/1")
    assert res.get_json()["posts"][0]["similar_href"] == ""


def test_deck_page_url_round_trips_mode(client):
    res = client.get("/api/deck?comic&count=1&url=https://comic.example/1")
    post = res.get_json()["posts"][0]
    assert "comic" in post["page_url"]
    assert "url=" in post["page_url"]
    assert "count=" not in post["page_url"]


# --- index page ---------------------------------------------------------------

def test_index_ships_deck_for_iframe_modes(client):
    res = client.get("/?url=https://a.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert 'name="sw-deck-url"' in body
    assert "deck.js" in body
    assert 'class="deck-panel"' in body


def test_index_omits_deck_for_code_mode(client, app_module):
    app_module.urls_gh_cache = [app_module.urls_cache[0]]
    res = client.get("/?gh&url=https://a.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert 'name="sw-deck-url"' not in body
    assert "deck.js" not in body


def test_index_keeps_next_anchor_for_no_js(client):
    res = client.get("/?url=https://a.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert "next-button" in body
    assert 'href="/?url=' in body or "href=\"/?" in body


def test_index_no_longer_prerenders(client):
    res = client.get("/?url=https://a.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert "speculationrules" not in body
    assert "seen-cookie.js" not in body


def test_deck_json_is_serializable(client):
    res = client.get("/api/deck?count=2&url=https://a.example/1")
    json.loads(res.get_data(as_text=True))


# --- search -------------------------------------------------------------------

# index() filters the pool by ?search before picking a post, so the deck has to
# apply the same filter or Next walks out of the result set.

def _searchable(app_module):
    """Three posts about rust, two about baking."""
    app_module.urls_cache = [
        entry("https://r.example/1", "Rust ownership", ["tech"]),
        entry("https://r.example/2", "Rust lifetimes", ["tech"]),
        entry("https://r.example/3", "Learning Rust", ["tech"]),
        entry("https://k.example/1", "Sourdough baking", ["food"]),
        entry("https://k.example/2", "Baking bread", ["food"]),
    ]
    return app_module.urls_cache


def test_deck_respects_search_filter(client, app_module):
    _searchable(app_module)
    res = client.get("/api/deck?search=rust&count=4&url=https://r.example/1")
    assert res.status_code == 200
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links, "deck queued nothing for a search with two more matches"
    assert set(links) == {"https://r.example/2", "https://r.example/3"}


def test_deck_search_excludes_non_matching_posts(client, app_module):
    _searchable(app_module)
    res = client.get("/api/deck?search=baking&count=5&url=https://k.example/1")
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links == ["https://k.example/2"]


def test_deck_search_with_no_other_match_queues_nothing(client, app_module):
    _searchable(app_module)
    # "sourdough" matches only the post already on screen.
    res = client.get("/api/deck?search=sourdough&count=3&url=https://k.example/1")
    assert res.status_code == 200
    assert res.get_json()["posts"] == []


def test_deck_search_with_zero_matches_returns_404(client, app_module):
    _searchable(app_module)
    res = client.get("/api/deck?search=nothingmatchesthis&count=3")
    assert res.status_code == 404


def test_deck_search_combines_with_category(client, app_module):
    _searchable(app_module)
    # Category narrows to food; the search term only matches tech posts.
    res = client.get("/api/deck?search=rust&cat=food&count=3")
    assert res.status_code == 404


def test_deck_page_url_round_trips_search(client, app_module):
    _searchable(app_module)
    res = client.get("/api/deck?search=rust&count=1&url=https://r.example/1")
    post = res.get_json()["posts"][0]
    # Following the deck's own link must land back in the same result set.
    assert "search=rust" in post["page_url"]


# --- non-embeddable domains ----------------------------------------------------

# Tumblr sends X-Frame-Options: deny, so an iframe pointed at it renders blank.
# Those posts get the same interstitial the flagged ones use.

def _with_tumblr(app_module):
    app_module.urls_cache = [
        entry("https://bogleech.tumblr.com/post/823100926826004480", "Tumblr post"),
        entry("https://a.example/1", "Alpha", ["tech"]),
    ]
    return app_module.urls_cache


def test_no_embed_flags_tumblr(app_module):
    assert app_module._is_embeddable("https://a.example/1") is True
    assert app_module._is_embeddable("https://bogleech.tumblr.com/post/1") is False
    # Subdomains and the apex are both blocked.
    assert app_module._is_embeddable("https://www.tumblr.com/x") is False
    assert app_module._is_embeddable("https://tumblr.com/x") is False
    # Lookalikes are not: the match is on a host-label boundary, not substring.
    assert app_module._is_embeddable("https://nottumblr.com/x") is True
    assert app_module._is_embeddable("https://tumblr.com.evil.example/x") is True


def test_deck_marks_non_embeddable_posts(client, app_module):
    _with_tumblr(app_module)
    res = client.get("/api/deck?count=2&url=https://a.example/1")
    posts = {p["url"]: p for p in res.get_json()["posts"]}
    tumblr = "https://bogleech.tumblr.com/post/823100926826004480"
    assert posts[tumblr]["no_embed"] is True


def test_deck_marks_embeddable_posts(client, app_module):
    _with_tumblr(app_module)
    res = client.get(
        "/api/deck?count=2&url=https://bogleech.tumblr.com/post/823100926826004480"
    )
    posts = {p["url"]: p for p in res.get_json()["posts"]}
    assert posts["https://a.example/1"]["no_embed"] is False


def test_index_shows_interstitial_for_non_embeddable(client, app_module):
    _with_tumblr(app_module)
    tumblr = "https://bogleech.tumblr.com/post/823100926826004480"
    res = client.get(f"/?url={tumblr}", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert "srcdoc" in body, "no interstitial: the iframe would render blank"
    assert "cannot be displayed here" in body
    # The escape hatch has to be a real link to the post.
    assert f'href="{tumblr}"' in body


def test_index_embeds_normal_sites_directly(client, app_module):
    _with_tumblr(app_module)
    res = client.get("/?url=https://a.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert 'src="https://a.example/1"' in body
    assert "cannot be displayed here" not in body


# --- category and cookie paths -------------------------------------------------

# The deck is fetched with same-origin credentials, so the cookie-driven filters
# have to apply there too or Next escapes the user's chosen topic.

def test_deck_respects_sticky_cat_cookie(client):
    client.set_cookie("sw_sticky_cat", "art", domain="localhost")
    res = client.get("/api/deck?count=4&url=https://c.example/3")
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links == ["https://d.example/4"]


def test_deck_respects_excluded_cats_cookie(client):
    client.set_cookie("sw_excluded_cats", "tech", domain="localhost")
    res = client.get("/api/deck?count=5&url=https://c.example/3")
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links, "excluded-cats cookie emptied the deck"
    assert "https://a.example/1" not in links
    assert "https://b.example/2" not in links


def test_deck_cat_param_overrides_sticky_cookie(client):
    client.set_cookie("sw_sticky_cat", "art", domain="localhost")
    res = client.get("/api/deck?cat=tech&count=4&url=https://a.example/1")
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links == ["https://b.example/2"]


def test_deck_page_url_round_trips_cat(client):
    res = client.get("/api/deck?cat=art&count=1&url=https://c.example/3")
    post = res.get_json()["posts"][0]
    assert "cat=art" in post["page_url"]


def test_deck_recent_mode_walks_in_order(client, app_module):
    ordered = sorted(app_module.urls_cache, key=lambda e: e.updated, reverse=True)
    res = client.get(f"/api/deck?recent&count=2&url={ordered[0].link}")
    links = [p["url"] for p in res.get_json()["posts"]]
    assert links == [ordered[1].link, ordered[2].link]


def test_deck_sticky_cookie_ignored_outside_blog_mode(client):
    # _resolve_current_cat only honours the sticky cookie for mode 0, so comics
    # must not be filtered by a leftover blog category.
    client.set_cookie("sw_sticky_cat", "art", domain="localhost")
    res = client.get("/api/deck?comic&count=2&url=https://comic.example/1")
    assert res.status_code == 200
    assert [p["url"] for p in res.get_json()["posts"]] == ["https://comic.example/2"]


def test_index_search_and_deck_agree_on_pool(client, app_module):
    """The no-JS next anchor and the deck must not disagree about the pool."""
    _searchable(app_module)
    res = client.get("/?search=rust&url=https://r.example/1", follow_redirects=True)
    body = res.get_data(as_text=True)
    assert "k.example" not in body, "index leaked a non-matching post"
    deck = client.get("/api/deck?search=rust&count=4&url=https://r.example/1")
    for post in deck.get_json()["posts"]:
        assert "k.example" not in post["url"]
