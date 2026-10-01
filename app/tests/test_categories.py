"""Topic categories: the app must know every slug the feed API emits.

update_entries() drops tags it does not recognise, so a slug the classifier
emits but CATEGORIES lacks turns those posts into "uncategorized".
"""
from types import SimpleNamespace

import pytest

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Kagi Small Web</title>
  <entry>
    <title>Why I stopped grading homework</title>
    <link href="https://teacher.example/grading"/>
    <updated>2026-09-28T10:00:00Z</updated>
    <category term="{slug}" scheme="https://kagi.com/smallweb/categories"/>
  </entry>
</feed>"""

# Slugs the classifier gained after the app first shipped its topic list.
ADDED_SLUGS = ["education", "work", "sports", "design"]


@pytest.mark.parametrize("slug", ADDED_SLUGS)
def test_added_tag_survives_ingest(app_module, monkeypatch, slug):
    resp = SimpleNamespace(
        content=ATOM.format(slug=slug).encode(), raise_for_status=lambda: None
    )
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: resp)
    monkeypatch.setattr(app_module, "_is_embeddable", lambda link: True)

    [post] = app_module.update_entries("https://feed.example/?nso")
    assert post.categories == [slug]


@pytest.mark.parametrize("slug", ADDED_SLUGS)
def test_added_topic_is_browsable_from_the_topics_menu(client, app_module, slug):
    assert any(slug in slugs for slugs in app_module.CATEGORY_GROUPS.values())
    html = client.get("/", follow_redirects=True).get_data(as_text=True)
    assert f"?cat={slug}" in html


def test_topic_groups_fill_their_two_column_rows(app_module):
    # The Topics menu is a two-column grid; an odd group leaves a hole at the
    # end of its last row. "Other" holds only the conditional Uncategorized.
    for name, slugs in app_module.CATEGORY_GROUPS.items():
        if name != "Other":
            assert len(slugs) % 2 == 0, name


def test_every_topic_is_listed_in_exactly_one_group(app_module):
    # A topic missing from the groups cannot be picked; one listed twice shows
    # up twice. Spam is filtered out of browsing and has no menu entry.
    listed = [s for slugs in app_module.CATEGORY_GROUPS.values() for s in slugs]
    assert sorted(listed) == sorted(set(app_module.CATEGORIES) - {"spam"})
