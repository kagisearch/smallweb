"""Topic categories: the app must know every slug the feed API emits.

update_entries() drops tags it does not recognise, so a slug the classifier
emits but CATEGORIES lacks turns those posts into "uncategorized".
"""
from types import SimpleNamespace

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Kagi Small Web</title>
  <entry>
    <title>Why I stopped grading homework</title>
    <link href="https://teacher.example/grading"/>
    <updated>2026-09-28T10:00:00Z</updated>
    <category term="education" label="Education" scheme="https://kagi.com/smallweb/categories"/>
  </entry>
</feed>"""


def test_education_tag_survives_ingest(app_module, monkeypatch):
    resp = SimpleNamespace(content=ATOM, raise_for_status=lambda: None)
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: resp)
    monkeypatch.setattr(app_module, "_is_embeddable", lambda link: True)

    [post] = app_module.update_entries("https://feed.example/?nso")
    assert post.categories == ["education"]


def test_education_is_browsable_from_the_topics_menu(client, app_module):
    assert any("education" in slugs for slugs in app_module.CATEGORY_GROUPS.values())
    html = client.get("/", follow_redirects=True).get_data(as_text=True)
    assert "?cat=education" in html
