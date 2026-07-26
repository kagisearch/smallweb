"""Import sw with the network stubbed out and a deterministic in-memory cache.

sw.py fetches every feed at import time and resolves data paths relative to the
app directory, so both have to be handled before the module is imported.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
import requests

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _no_network(*args, **kwargs):
    raise requests.RequestException("network disabled in tests")


os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)
requests.get = _no_network

import sw  # noqa: E402

sw.scheduler.shutdown(wait=False)


def entry(link, title="T", cats=None, minutes_old=0):
    # Naive timestamps, matching what update_entries() stores.
    return sw.FeedEntry(
        link=link,
        title=title,
        author="A",
        description="D",
        updated=datetime.now() - timedelta(minutes=minutes_old),
        categories=cats if cats is not None else [],
    )


BLOGS = [
    entry("https://a.example/1", "Alpha", ["tech"], 5),
    entry("https://b.example/2", "Beta", ["tech"], 4),
    entry("https://c.example/3", "Gamma", ["art"], 3),
    entry("https://d.example/4", "Delta", ["art"], 2),
    entry("https://e.example/5", "Epsilon", [], 1),
]

COMICS = [
    entry("https://comic.example/1", "Strip One"),
    entry("https://comic.example/2", "Strip Two"),
]


@pytest.fixture
def app_module():
    """sw module with caches reset to a known state for each test."""
    sw.urls_cache = list(BLOGS)
    sw.urls_comic_cache = list(COMICS)
    sw.urls_yt_cache = []
    sw.urls_gh_cache = []
    sw.urls_liked_cache = []
    sw.urls_flagged_cache = []
    sw.likes_dict = {}
    sw.flagged_content_dict = {}
    sw.embeddings_cache = {}
    return sw


@pytest.fixture
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
