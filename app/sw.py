import atexit
import hashlib
import json
import logging
import os
import random
import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from html import escape
from typing import NamedTuple
from urllib.parse import parse_qs, urlencode, urlparse

import fastfeedparser
import numpy as np
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from feedwerk.atom import AtomFeed
from flask import (
    Flask,
    Response,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeedEntry(NamedTuple):
    link: str
    title: str
    author: str
    description: str
    updated: datetime
    categories: list
    feed_url: str = ""


API_BASE = "https://kagi.com/api/v1/smallweb/feed"

# Category definitions — slug → label · description · emoji
CATEGORIES = OrderedDict(
    [
        (
            "ai",
            (
                "AI",
                "LLMs · agents · prompts · AI ethics · AI safety",
                "✨",
            ),
        ),
        (
            "programming",
            (
                "Programming",
                "Code · frameworks · devtools · APIs · tutorials · open source",
                "🧩",
            ),
        ),
        (
            "tech",
            (
                "Technology",
                "Tech news · gadgets · apps · platforms · social media",
                "\U0001f4f1",
            ),
        ),
        (
            "infra",
            (
                "Sysadmin & Security",
                "Servers · cloud · containers · networking · infosec · privacy",
                "\U0001f6e1\ufe0f",
            ),
        ),
        (
            "web",
            (
                "Web & Internet",
                "The open web · RSS · blogging · IndieWeb · web standards",
                "\U0001f578\ufe0f",
            ),
        ),
        (
            "hardware",
            ("Hardware", "Electronics · home lab · PCB design · keyboards · audio gear", "🎛️"),
        ),
        (
            "diy",
            (
                "DIY & Making",
                "Woodworking · metalworking · 3D printing · home · maker",
                "\U0001f6e0\ufe0f",
            ),
        ),
        (
            "retro",
            (
                "Retro",
                "Vintage computers · DOS · BBS · demoscene · old software",
                "\U0001f4be",
            ),
        ),
        (
            "science",
            (
                "Science",
                "Physics · biology · math · space · climate · research",
                "⚛️",
            ),
        ),
        (
            "humanities",
            (
                "Humanities",
                "History · philosophy · linguistics · archaeology · classics",
                "\U0001f3fa",
            ),
        ),
        (
            "essays",
            (
                "Essays",
                "Long-form reflective writing that defies topic categories",
                "\U0001fab6",
            ),
        ),
        (
            "art",
            (
                "Art & Design",
                "Visual art · illustration · typography · creative writing",
                "🌊",
            ),
        ),
        (
            "photography",
            (
                "Photography",
                "Photographic craft · technique · gear · film · photo essays",
                "🌄",
            ),
        ),
        (
            "culture",
            (
                "Pop Culture",
                "Film · TV · music · books · comics",
                "🎭",
            ),
        ),
        (
            "gaming",
            (
                "Gaming",
                "Video games · game dev · modding · interactive fiction",
                "🕹️",
            ),
        ),
        (
            "politics",
            (
                "Politics",
                "Government · legislation · international relations",
                "🎤",
            ),
        ),
        (
            "economy",
            (
                "Economy",
                "Markets · finance · labor economics · trade · analysis",
                "🎲",
            ),
        ),
        (
            "society",
            (
                "Society",
                "Discrimination · civil rights · social structure",
                "👥",
            ),
        ),
        (
            "life",
            (
                "Life & Personal",
                "Diary · weeknotes · parenting · pets · link roundups",
                "☀️",
            ),
        ),
        (
            "food",
            (
                "Food & Drink",
                "Recipes · cooking · restaurants · coffee · wine · baking",
                "🧑‍🍳",
            ),
        ),
        (
            "travel",
            (
                "Travel & Outdoors",
                "Trip reports · hiking · nature · birdwatching · gardening",
                "✈️",
            ),
        ),
        (
            "health",
            (
                "Health & Fitness",
                "Fitness · nutrition · mental health · longevity",
                "🏃",
            ),
        ),
        (
            "uncategorized",
            (
                "Uncategorized",
                "Posts that don\u2019t fit neatly into any topic",
                "\U0001f4c2",
            ),
        ),
        ("spam", ("Spam", "Suspected spam or low-quality content", "\U0001f6ab")),
    ]
)

# Groups for dropdown display
CATEGORY_GROUPS = OrderedDict(
    [
        (
            "Tech & Science",
            [
                "ai",
                "science",
                "programming",
                "diy",
                "tech",
                "hardware",
                "infra",
                "web",
            ],
        ),
        (
            "Culture & Creative",
            [
                "health",
                "art",
                "essays",
                "humanities",
                "retro",
                "photography",
                "culture",
                "gaming",
            ],
        ),
        (
            "Life & World",
            [
                "society",
                "life",
                "food",
                "travel",
                "politics",
                "economy",
            ],
        ),
        ("Other", ["uncategorized"]),
    ]
)

# Remap legacy category slugs from the feed API
CATEGORY_REMAP = {"sysadmin": "infra", "security": "infra"}

liked_feed = None  # Initialize the variable to store the liked Atom feed
opml_cache = None  # will hold generated OPML xml

# NOTE(z64): List of emotes that can be used for likes.
# Used to build the list in the template, and perform validation on the server.
like_emoji_list = [
    "👍",
    "😍",
    "😀",
    "😘",
    "😆",
    "😜",
    "🫶",
    "😂",
    "😱",
    "🤔",
    "👏",
    "🚀",
    "🥳",
    "🔥",
]

# --- Backend seen-cookie dedup ------------------------------------------------
SEEN_COOKIE = "seen"
SEEN_MAX = 100


def _hash_url(url):
    """8-char hex hash for compact cookie storage."""
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _get_seen(req):
    """Read seen hashes from cookie as a set."""
    raw = req.cookies.get(SEEN_COOKIE, "")
    return set(raw.split(",")) if raw else set()


def _pick_unseen(cache, seen):
    """Pick random entry not in seen set. Falls back to random.choice if all seen."""
    candidates = [e for e in cache if _hash_url(e.link) not in seen]
    if not candidates:
        candidates = cache
    return random.choice(candidates)


def _is_prefetch():
    """Detect prefetch / prerender requests (browsers send Sec-Purpose header)."""
    purpose = request.headers.get("Sec-Purpose", "") or request.headers.get("Purpose", "")
    return "prefetch" in purpose.lower() or "prerender" in purpose.lower()


def _set_seen_cookie(response, seen, new_url):
    """Append new_url hash to seen cookie, keeping last SEEN_MAX entries.

    Skips the update for prefetch/prerender requests to avoid a race condition
    where the speculative request overwrites the cookie set by the main navigation.
    """
    if _is_prefetch():
        return response
    h = _hash_url(new_url)
    seen_list = [x for x in seen if x and x != h]
    seen_list.append(h)
    if len(seen_list) > SEEN_MAX:
        seen_list = seen_list[-SEEN_MAX:]
    response.set_cookie(SEEN_COOKIE, ",".join(seen_list), max_age=86400, samesite="Lax")
    return response


# --- Embeddings for "Show similar" ------------------------------------------
embeddings_cache = {}  # url → set (for membership checks only)
_emb_matrix = None     # normalized numpy matrix (N x dim), float32
_emb_urls = []         # url list aligned with matrix rows
_emb_url_to_idx = {}   # url → row index


def _build_embedding_matrix(emb):
    """Build a pre-normalized numpy matrix from the raw embeddings dict."""
    global _emb_matrix, _emb_urls, _emb_url_to_idx
    urls = list(emb.keys())
    mat = np.array([emb[u] for u in urls], dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat /= norms
    _emb_matrix = mat
    _emb_urls = urls
    _emb_url_to_idx = {u: i for i, u in enumerate(urls)}


def update_embeddings():
    """Fetch pre-computed embeddings from the API."""
    global embeddings_cache
    try:
        resp = requests.get(
            API_BASE + "/embeddings", timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embeddings", {})
        if emb:
            embeddings_cache = emb
            _build_embedding_matrix(emb)
            logger.info("Loaded %d embeddings", len(emb))
    except Exception as e:
        logger.error("Failed to fetch embeddings: %s", e)


def find_similar(url, seen, cache):
    """Find the most similar unseen entry to `url` using cached embeddings."""
    idx = _emb_url_to_idx.get(url)
    if idx is None or _emb_matrix is None:
        return None

    scores = _emb_matrix @ _emb_matrix[idx]
    scores[idx] = -1.0  # exclude self

    entry_map = {e.link: e for e in cache}
    order = np.argsort(scores)[::-1]
    for i in order:
        candidate_url = _emb_urls[i]
        if candidate_url not in entry_map:
            continue
        if _hash_url(candidate_url) not in seen:
            return entry_map[candidate_url]

    return None


def generate_liked_feed():
    """Generate Atom feed for liked posts."""
    global liked_feed
    liked_feed = AtomFeed(
        "Kagi Small Web Liked", feed_url="https://kagi.com/smallweb/liked"
    )
    for entry in urls_liked_cache:
        liked_feed.add(
            title=entry.title,
            content=entry.description,
            content_type="html",
            url=entry.link,
            updated=entry.updated,
            author=entry.author,
        )


def _find_feed_file(name):
    """Locate a feed list file (check CWD first, then parent for local dev)."""
    for path in (name, os.path.join("..", name)):
        if os.path.isfile(path):
            return path
    return None


def _build_opml_outline(feed_url):
    """Build an OPML outline element from a simple feed URL."""
    parsed = urlparse(feed_url)
    domain = parsed.hostname or ""
    domain = domain.removeprefix("www.")
    html_url = f"{parsed.scheme}://{parsed.hostname}"
    safe = escape(domain, quote=True)
    return (
        f'    <outline text="{safe}" title="{safe}" '
        f'type="rss" xmlUrl="{escape(feed_url, quote=True)}" '
        f'htmlUrl="{escape(html_url, quote=True)}"/>'
    )


def generate_opml_feed() -> str:
    """Return OPML subscription list built from the curated feed URL files."""
    outlines = []

    # Blog feeds — one URL per line
    path = _find_feed_file("smallweb.txt")
    if path:
        with open(path) as f:
            for line in f:
                feed_url = line.split("#")[0].strip()
                if feed_url:
                    outlines.append(_build_opml_outline(feed_url))

    # YouTube feeds — format: URL # Channel Name https://...
    path = _find_feed_file("smallyt.txt")
    if path:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("#", 1)
                feed_url = parts[0].strip()
                if not feed_url:
                    continue
                # Extract channel name and URL from comment
                title = "YouTube"
                html_url = "https://www.youtube.com"
                if len(parts) > 1:
                    comment = parts[1].strip()
                    # "Channel Name https://www.youtube.com/channel/XXX"
                    idx = comment.find("https://")
                    if idx > 0:
                        title = comment[:idx].strip()
                        html_url = comment[idx:].strip()
                    elif comment:
                        title = comment.strip()
                safe = escape(title, quote=True)
                outlines.append(
                    f'    <outline text="{safe}" title="{safe}" '
                    f'type="rss" xmlUrl="{escape(feed_url, quote=True)}" '
                    f'htmlUrl="{escape(html_url, quote=True)}"/>'
                )

    # Comic feeds — one URL per line
    path = _find_feed_file("smallcomic.txt")
    if path:
        with open(path) as f:
            for line in f:
                feed_url = line.split("#")[0].strip()
                if feed_url:
                    outlines.append(_build_opml_outline(feed_url))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="1.0">\n'
        "  <head>\n"
        "    <title>Kagi Small Web OPML</title>\n"
        "  </head>\n"
        "  <body>\n" + "\n".join(outlines) + "\n  </body>\n</opml>"
    )


DIR_DATA = "data"
if not os.path.isdir(DIR_DATA):
    os.makedirs(DIR_DATA)
PATH_LIKES = os.path.join(DIR_DATA, "likes.json")
# Keep the legacy filename in sync while older deployments/rollbacks still
# expect favorites.json on disk.
PATH_FAVORITES_LEGACY = os.path.join(DIR_DATA, "favorites.json")
PATH_NOTES = os.path.join(DIR_DATA, "notes.json")
PATH_FLAGGED = os.path.join(DIR_DATA, "flagged_content.json")


def serialize_notes(notes: dict) -> dict:
    """Convert notes_dict to JSON-serializable format (datetime -> ISO string)."""
    return {
        url: [[content, ts.isoformat()] for content, ts in entries]
        for url, entries in notes.items()
    }


def deserialize_notes(data: dict) -> dict:
    """Convert JSON data back to notes_dict format (ISO string -> datetime)."""
    return {
        url: [(content, datetime.fromisoformat(ts)) for content, ts in entries]
        for url, entries in data.items()
    }


def _load_json(path, deserializer=None):
    """Load JSON data from path, applying optional deserializer."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if deserializer:
                data = deserializer(data)
            logger.info("Loaded %s (%d entries)", path, len(data))
            return data
    except Exception as e:
        logger.error("Failed to load %s: %s", path, e)
        return None


def save_likes():
    """Persist likes to the canonical file and the legacy favorites file."""
    payload = {u: dict(emojis) for u, emojis in likes_dict.items()}
    for path in [PATH_LIKES, PATH_FAVORITES_LEGACY]:
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(payload, file)
        except OSError as e:
            logger.error("Cannot write likes file %s: %s", path, e)


def time_ago(timestamp):
    delta = datetime.now() - timestamp
    seconds = delta.total_seconds()

    if seconds < 60:
        return "now"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes"
    elif seconds < 86400:
        return f"{int(seconds // 3600)} hours"
    else:
        return f"{int(seconds // 86400)} days"


_TAG_RE = re.compile(r"<[^>]+>")


def river_date(timestamp):
    """Format date for river cards: '2h ago', 'Mar 22', 'Jan 5, 2025'."""
    now = datetime.now()
    delta = now - timestamp
    seconds = delta.total_seconds()
    if seconds < 3600:
        mins = max(1, int(seconds // 60))
        return f"{mins}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if timestamp.year == now.year:
        return timestamp.strftime("%b %-d")
    return timestamp.strftime("%b %-d, %Y")


def make_excerpt(html, max_len=200):
    """Strip HTML tags and truncate at word boundary."""
    text = _TAG_RE.sub("", html or "")
    text = " ".join(text.split())  # collapse whitespace
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # cut at last space to avoid mid-word truncation
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated + "\u2026"


prefix = os.environ.get("URL_PREFIX", "")
app = Flask(__name__, static_url_path=prefix + "/static")
app.jinja_env.filters["time_ago"] = time_ago

master_feed = False


def _build_redirect_params():
    """Build query string from request.args, excluding 'url'."""
    params = {k: v for k, v in request.args.items() if k != "url"}
    return "&".join(f"{k}={v}" for k, v in params.items())


def _render_no_results(
    current_mode,
    title="",
    search_query="",
    current_cat="",
    category_counts=None,
    no_results_cat="",
    feed_unavailable=False,
):
    """Render the index template with no results."""
    return render_template(
        "index.html",
        url="",
        short_url="",
        query_string="",
        title=title,
        author="",
        domain="",
        prefix=prefix + "/",
        videoid="",
        current_mode=current_mode,
        likes_count=0,
        notes_count=0,
        notes_list=[],
        flag_content_count=0,
        search_query=search_query,
        no_results=True,
        no_results_cat=no_results_cat,
        feed_unavailable=feed_unavailable,
        reactions_dict=OrderedDict(),
        reactions_list=[],
        likes_total=0,
        next_link="",
        next_doc_url="",
        next_host="",
        categories=CATEGORIES,
        category_groups=CATEGORY_GROUPS,
        current_cat=current_cat,
        category_counts=category_counts or {},
        post_categories=[],
    )


def update_all():
    global \
        urls_cache, \
        urls_liked_cache, \
        urls_yt_cache, \
        urls_gh_cache, \
        urls_comic_cache, \
        urls_flagged_cache, \
        master_feed, \
        likes_dict, \
        liked_feed

    url = API_BASE + "/"

    try:
        logger.info("begin update_all")

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            check_feed = fastfeedparser.parse(resp.content)
            if check_feed.entries:
                master_feed = check_feed
        except requests.RequestException as e:
            logger.error("Failed to fetch master feed: %s", e)

        new_entries = update_entries(url + "?nso")  # no same origin sites feed

        if not urls_cache or new_entries:
            # Filter out YouTube URLs from main feed
            urls_cache = [
                entry
                for entry in new_entries
                if "youtube.com" not in entry.link and "youtu.be" not in entry.link
            ]

        new_entries = update_entries(url + "?yt")  # youtube sites

        if not urls_yt_cache or new_entries:
            # Filter out YouTube Shorts links
            urls_yt_cache = [
                entry for entry in new_entries if "/shorts/" not in entry.link
            ]

        new_entries = update_entries(url + "?gh")  # github sites

        if not urls_gh_cache or new_entries:
            urls_gh_cache = new_entries

        new_entries = update_entries(url + "?comic")  # comic sites

        if not urls_comic_cache or new_entries:
            urls_comic_cache = new_entries

        # Prune likes_dict to only include URLs present in urls_cache or urls_yt_cache
        current_urls = set(entry.link for entry in urls_cache + urls_yt_cache)
        likes_dict = {
            u: count for u, count in likes_dict.items() if u in current_urls
        }

        # Build urls_liked_cache from liked entries in urls_cache and urls_yt_cache
        urls_liked_cache = [
            e for e in (urls_cache + urls_yt_cache) if e.link in likes_dict
        ]

        # Build urls_flagged_cache from flagged entries in all caches
        urls_flagged_cache = [
            e
            for e in (urls_cache + urls_yt_cache + urls_gh_cache + urls_comic_cache)
            if e.link in flagged_content_dict
        ]

        # Generate the liked feed
        generate_liked_feed()

        # Update cached OPML
        global opml_cache
        opml_cache = generate_opml_feed()

    except Exception as e:
        logger.error("Error during update_all: %s", e)
    finally:
        logger.info("end update_all")


def _extract_content(entry):
    """Extract HTML from fastfeedparser's content list-of-dicts."""
    content = entry.get("content")
    if isinstance(content, list) and content:
        return content[0].get("value", "")
    return ""


def update_entries(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return []

    feed = fastfeedparser.parse(response.content)
    entries = feed.entries

    if entries:
        formatted_entries = []
        for entry in entries:
            link = entry.get("link", "")
            updated = datetime.now(timezone.utc).replace(tzinfo=None)
            updated_str = entry.get("updated") or entry.get("published")
            if updated_str:
                try:
                    updated = datetime.fromisoformat(
                        updated_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            # Parse category tags from Atom <category> elements
            categories = []
            for tag in entry.get("tags", []):
                term = tag.get("term", "")
                term = CATEGORY_REMAP.get(term, term)
                if term in CATEGORIES and term not in categories:
                    categories.append(term)

            # Extract source feed URL from <link rel="via"> if present
            via_url = ""
            for lnk in entry.get("links", []):
                if lnk.get("rel") == "via":
                    via_url = lnk.get("href", "")
                    break

            formatted_entries.append(
                FeedEntry(
                    link=link,
                    title=entry.get("title", ""),
                    author=entry.get("author", ""),
                    description=entry.get("description", "") or _extract_content(entry),
                    updated=updated,
                    categories=categories,
                    feed_url=via_url,
                )
            )

        cache = [e for e in formatted_entries if e.link.startswith("https://")]
        logger.info("%d entries from %s", len(cache), url)
        return cache
    else:
        return []


def load_public_suffix_list(file_path):
    public_suffix_list = set()
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                public_suffix_list.add(line)
    return public_suffix_list


# Load the list from your actual file path
public_suffix_list = load_public_suffix_list("public_suffix_list.dat")


def get_registered_domain(url):
    parsed_url = urlparse(url)
    netloc_parts = parsed_url.netloc.split(".")
    for i in range(len(netloc_parts)):
        possible_suffix = ".".join(netloc_parts[i:])
        if possible_suffix in public_suffix_list:
            return ".".join(netloc_parts[:i]) + "." + possible_suffix
    return parsed_url.netloc


@app.route("/")
def index():
    global urls_cache, urls_yt_cache, urls_liked_cache, urls_gh_cache, urls_flagged_cache

    url = request.args.get("url")
    should_redirect_to_chosen_url = not url
    search_query = request.args.get("search", "").lower()
    title = None
    post_cats = []
    current_mode = 0
    if "recent" in request.args:
        cache = sorted(urls_cache, key=lambda e: e.updated, reverse=True)
        current_mode = 6
    elif "yt" in request.args:
        cache = urls_yt_cache
        current_mode = 1
    # `?app` is kept as a legacy alias for older native-app builds.
    elif "liked" in request.args or "app" in request.args:
        cache = urls_liked_cache
        current_mode = 2
    elif "gh" in request.args:
        cache = urls_gh_cache
        current_mode = 3
    elif "comic" in request.args:
        cache = urls_comic_cache
        current_mode = 4
    elif "flagged" in request.args:
        cache = urls_flagged_cache
        current_mode = 5
    else:
        cache = urls_cache

    if (
        search_query.strip()
    ):  # Only perform search if query is not empty or just whitespace
        cache = [
            entry
            for entry in cache
            if (
                search_query in entry.link.lower()  # url
                or any(
                    search_query.lower() == word.lower() for word in entry.title.split()
                )  # title
                or any(
                    search_query.lower() == word.lower()
                    for word in entry.author.split()
                )  # author
                or any(
                    search_query.lower() == word.lower()
                    for word in entry.description.split()
                )
            )  # description
        ]
        if not cache:
            return _render_no_results(
                current_mode,
                title="No results found",
                search_query=search_query,
            )

    # Category counts (before filtering, so user sees totals)
    category_counts = {}
    if current_mode == 0:
        for entry in cache:
            for cat_slug in entry.categories:
                category_counts[cat_slug] = category_counts.get(cat_slug, 0) + 1
            if not entry.categories:
                category_counts["uncategorized"] = (
                    category_counts.get("uncategorized", 0) + 1
                )

    # Resolve category: URL param > sticky cookie (blog mode only)
    if "cat" in request.args:
        current_cat = request.args["cat"]
    elif current_mode == 0:
        cookie_cat = request.cookies.get("sw_sticky_cat", "")
        current_cat = cookie_cat if cookie_cat in CATEGORIES else ""
    else:
        current_cat = ""
    if current_cat != "spam":
        cache = [entry for entry in cache if "spam" not in entry.categories]

    # Exclude user-hidden categories (stored in cookie)
    excluded_cats_raw = request.cookies.get("sw_excluded_cats", "")
    excluded_cats = set(
        slug for slug in excluded_cats_raw.split(",") if slug in CATEGORIES
    )
    if excluded_cats and not current_cat:
        cache = [
            entry
            for entry in cache
            if not excluded_cats.intersection(entry.categories or ["uncategorized"])
        ]

    # Category filtering
    if current_cat and current_cat in CATEGORIES:
        if current_cat == "uncategorized":
            cache = [
                entry
                for entry in cache
                if not entry.categories or "uncategorized" in entry.categories
            ]
        else:
            cache = [entry for entry in cache if current_cat in entry.categories]

        if not cache:
            return _render_no_results(
                current_mode,
                current_cat=current_cat,
                category_counts=category_counts,
                no_results_cat=current_cat,
            )

    if url is not None:
        http_url = url.replace("https://", "http://")
        title, author, description, post_cats = next(
            (
                (e.title, e.author, e.description, e.categories)
                for e in cache
                if e.link == url or e.link == http_url
            ),
            (None, None, None, []),
        )

    seen = _get_seen(request)

    if title is None:
        if cache:
            if current_mode == 6:
                # Recent mode: pick the first (newest) entry
                chosen = cache[0]
            else:
                chosen = _pick_unseen(cache, seen)
            url, title, author, post_cats = (
                chosen.link,
                chosen.title,
                chosen.author,
                chosen.categories,
            )
        else:
            return _render_no_results(
                current_mode,
                current_cat=current_cat,
                category_counts=category_counts,
                feed_unavailable=True,
            )

    if should_redirect_to_chosen_url and url:
        params = request.args.to_dict(flat=True)
        params["url"] = url.replace("http://", "https://", 1)
        return redirect(prefix + "/?" + urlencode(params), code=302)

    # -------------------------------------------------
    # Build deterministic "next post" link and pre-load it
    # -------------------------------------------------
    next_link = None
    next_doc_url = None
    next_host = None
    if cache:
        if current_mode == 6:
            # Recent mode: next is the following entry in chronological order
            cur_idx = next((i for i, e in enumerate(cache) if e.link == url), -1)
            next_entry = cache[cur_idx + 1] if cur_idx >= 0 and cur_idx + 1 < len(cache) else None
        else:
            # Exclude current URL from next candidates, then pick unseen
            next_pool = [e for e in cache if e.link != url] or cache
            seen_plus = seen | {_hash_url(url)}
            next_candidates = [e for e in next_pool if _hash_url(e.link) not in seen_plus]
            if not next_candidates:
                next_candidates = next_pool
            # 7% chance next post comes from the liked pool (unseen)
            if current_mode != 2 and urls_liked_cache and random.random() < 0.07:
                liked_unseen = [e for e in urls_liked_cache if _hash_url(e.link) not in seen_plus and e.link != url]
                if liked_unseen:
                    next_entry = random.choice(liked_unseen)
                    next_candidates = None  # skip normal selection
            # 60% chance to stay in the same category when browsing all
            if next_candidates and not current_cat and post_cats and random.random() < 0.6:
                same_cat = [
                    e for e in next_candidates
                    if any(c in e.categories for c in post_cats)
                ]
                if same_cat:
                    next_candidates = same_cat
            if next_candidates:
                next_entry = random.choice(next_candidates)

        if next_entry:
            next_params = request.args.to_dict(flat=True)
            next_params["url"] = next_entry.link
            next_link = prefix + "/?" + urlencode(next_params)
            next_doc_url = next_entry.link
            host_parts = urlparse(next_doc_url)
            next_host = f"{host_parts.scheme}://{host_parts.netloc}"

    short_url = re.sub(r"^https?://(www\.)?", "", url)
    short_url = short_url.rstrip("/")

    domain = get_registered_domain(url)
    domain = re.sub(r"^(www\.)?", "", domain)

    videoid = ""

    if "youtube.com" in short_url:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if "v" in query_params:
            videoid = query_params["v"][0]
            current_mode = 1

    # get likes
    reactions_dict = likes_dict.get(url, OrderedDict())
    likes_total = sum(reactions_dict.values())

    # Preserve all query parameters except 'url'
    query_string = _build_redirect_params()
    if query_string:
        query_string = "?" + query_string

    # count notes
    notes_count = len(notes_dict.get(url, []))
    notes_list = notes_dict.get(url, [])

    # get flagged content
    flag_content_count = flagged_content_dict.get(url, 0)

    # Build (slug, label, emoji) tuples for the current post's categories
    post_categories = [
        (s, CATEGORIES[s][0], CATEGORIES[s][2]) for s in post_cats if s in CATEGORIES
    ]

    if url.startswith("http://"):
        url = url.replace(
            "http://", "https://"
        )  # force https as http will not work inside https iframe anyway

    # GitHub API enrichment for Code mode
    gh_meta = None
    if current_mode == 3:
        gh_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
        if gh_match:
            owner, repo = gh_match.group(1), gh_match.group(2)
            try:
                gh_resp = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    timeout=5,
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if gh_resp.status_code == 200:
                    data = gh_resp.json()
                    owner_data = data.get("owner") or {}
                    gh_meta = {
                        "description": data.get("description") or "",
                        "stargazers_count": data.get("stargazers_count", 0),
                        "language": data.get("language") or "",
                        "forks_count": data.get("forks_count", 0),
                        "topics": data.get("topics", []),
                        "open_issues_count": data.get("open_issues_count", 0),
                        "homepage": data.get("homepage") or "",
                        "avatar_url": owner_data.get("avatar_url") or "",
                        "owner": owner,
                        "repo": repo,
                    }
            except requests.RequestException:
                pass

    # Build feed URL for <link rel="alternate">
    if current_mode == 6:
        feed_url = prefix + "/feed?recent"
    elif current_mode == 1:
        feed_url = prefix + "/feed?yt"
    elif current_mode == 2:
        feed_url = prefix + "/feed?liked"
    elif current_mode == 3:
        feed_url = prefix + "/feed?gh"
    elif current_mode == 4:
        feed_url = prefix + "/feed?comic"
    elif current_cat:
        feed_url = prefix + "/feed?cat=" + current_cat
    else:
        feed_url = prefix + "/feed"

    # Calculate counts
    all_count = len(urls_cache) if urls_cache else 0
    liked_count = len(urls_liked_cache) if urls_liked_cache else 0
    videos_count = len(urls_yt_cache) if urls_yt_cache else 0
    code_count = len(urls_gh_cache) if urls_gh_cache else 0
    comics_count = len(urls_comic_cache) if urls_comic_cache else 0

    # NOTE(z64): Some invalid reactions may be left over in the pkl file; filter them out.
    reactions_list = []
    for emoji, count in reactions_dict.items():
        if emoji in like_emoji_list:
            reactions_list.append((emoji, count))

    resp = make_response(
        render_template(
            "index.html",
            url=url,
            short_url=short_url,
            query_string=query_string,
            title=title,
            author=author,
            domain=domain,
            prefix=prefix + "/",
            videoid=videoid,
            current_mode=current_mode,
            notes_count=notes_count,
            notes_list=notes_list,
            flag_content_count=flag_content_count,
            search_query=search_query,
            all_count=all_count,
            liked_count=liked_count,
            videos_count=videos_count,
            code_count=code_count,
            comics_count=comics_count,
            next_link=next_link,
            next_doc_url=next_doc_url,
            next_host=next_host,
            reactions_list=reactions_list,
            likes_total=likes_total,
            like_emoji_list=like_emoji_list,
            reactions_dict=reactions_dict,
            categories=CATEGORIES,
            category_groups=CATEGORY_GROUPS,
            current_cat=current_cat,
            category_counts=category_counts,
            post_categories=post_categories,
            feed_url=feed_url,
            gh_meta=gh_meta,
            has_embedding=(bool(embeddings_cache) and url in embeddings_cache),
        )
    )
    return _set_seen_cookie(resp, seen, url)


RIVER_PAGE_SIZE = 50


@app.route("/river")
@app.route(f"{prefix}/river")
def river():
    """River view: reverse-chronological card stream."""
    # Pick cache based on mode
    if "yt" in request.args:
        cache = sorted(urls_yt_cache, key=lambda e: e.updated, reverse=True)
        mode = "yt"
        feed_url = prefix + "/feed?yt"
    elif "gh" in request.args:
        cache = sorted(urls_gh_cache, key=lambda e: e.updated, reverse=True)
        mode = "gh"
        feed_url = prefix + "/feed?gh"
    elif "comic" in request.args:
        cache = sorted(urls_comic_cache, key=lambda e: e.updated, reverse=True)
        mode = "comic"
        feed_url = prefix + "/feed?comic"
    else:
        cache = sorted(urls_cache, key=lambda e: e.updated, reverse=True)
        mode = ""
        feed_url = prefix + "/feed"

    # Exclude spam
    cache = [e for e in cache if "spam" not in e.categories]

    # Topic filtering
    topic = request.args.get("topic", "")
    if topic and topic in CATEGORIES:
        if topic == "uncategorized":
            cache = [e for e in cache if not e.categories or "uncategorized" in e.categories]
        else:
            cache = [e for e in cache if topic in e.categories]
        feed_url = prefix + f"/feed?cat={topic}"

    # Pagination
    page = request.args.get("page", "1")
    try:
        page = max(1, int(page))
    except ValueError:
        page = 1

    total = len(cache)
    start = (page - 1) * RIVER_PAGE_SIZE
    end = start + RIVER_PAGE_SIZE
    entries = cache[start:end]
    has_next = end < total

    # Build cards with pre-computed display fields
    cards = []
    for entry in entries:
        domain = get_registered_domain(entry.link)
        domain = re.sub(r"^(www\.)?", "", domain)
        desc = entry.description or ""
        excerpt = make_excerpt(desc, 200)
        # Topic badge: first non-spam category
        badge = None
        for cat_slug in entry.categories:
            if cat_slug in CATEGORIES and cat_slug != "spam":
                badge = (cat_slug, CATEGORIES[cat_slug][0], CATEGORIES[cat_slug][2])
                break
        # Build Small Web URL: /?url=<post>&mode_param
        sw_params = {"url": entry.link}
        if mode == "yt":
            sw_params["yt"] = ""
        elif mode == "gh":
            sw_params["gh"] = ""
        sw_url = prefix + "/?" + urlencode(sw_params)
        cards.append({
            "link": entry.link,
            "sw_url": sw_url,
            "title": entry.title,
            "domain": domain,
            "date": river_date(entry.updated),
            "excerpt": excerpt,
            "badge": badge,
            "feed_url": entry.feed_url,
        })

    # Build next page URL preserving params
    next_page_url = None
    if has_next:
        params = {k: v for k, v in request.args.items() if k != "page"}
        params["page"] = str(page + 1)
        next_page_url = prefix + "/river?" + urlencode(params)

    return render_template(
        "river.html",
        cards=cards,
        page=page,
        has_next=has_next,
        next_page_url=next_page_url,
        mode=mode,
        topic=topic,
        prefix=prefix + "/",
        categories=CATEGORIES,
        category_groups=CATEGORY_GROUPS,
        feed_url=feed_url,
        total=total,
    )


@app.route("/similar")
@app.route(f"{prefix}/similar")
def similar():
    url = request.args.get("url", "")
    if not url or url not in embeddings_cache:
        return redirect(prefix + "/")

    # Use the same cache as mode 0 (websites)
    seen = _get_seen(request)
    result = find_similar(url, seen, urls_cache)

    # Build redirect params preserving cat filter
    params = {}
    cat = request.args.get("cat")
    if cat:
        params["cat"] = cat

    if result:
        params["url"] = result.link
    # If no similar found, redirect to random (no url param)

    return redirect(prefix + "/?" + urlencode(params) if params else prefix + "/")


@app.post("/like")
@app.post(f"{prefix}/like")
# Keep `/favorite` working until older clients switch to `/like`.
@app.post("/favorite")
@app.post(f"{prefix}/favorite")
def like():
    global likes_dict, time_saved_likes, urls_liked_cache, liked_feed
    url = request.form.get("url")

    emoji = "👍"
    emoji_from_form = request.form.get("emoji")
    if emoji_from_form and emoji_from_form in like_emoji_list:
        emoji = emoji_from_form

    if url:
        entry = likes_dict.get(url)
        if not isinstance(entry, OrderedDict):
            entry = OrderedDict()  # initialise
        # enforce max 3 distinct emojis (drop oldest)
        if emoji not in entry and len(entry) >= 3:
            entry.popitem(last=False)
        entry[emoji] = entry.get(emoji, 0) + 1
        likes_dict[url] = entry

        # Update urls_liked_cache with the new liked post from both regular and YouTube feeds
        urls_liked_cache = [
            e for e in (urls_cache + urls_yt_cache) if e.link in likes_dict
        ]

        # Regenerate the liked feed
        generate_liked_feed()

        # Save to disk immediately (multi-instance deployment requires immediate persistence)
        time_saved_likes = datetime.now()
        save_likes()

        # Always try to redirect to a similar post after a like
        if url in embeddings_cache:
            seen = _get_seen(request)
            sim = find_similar(url, seen, urls_cache)
            if sim:
                params = {"url": sim.link}
                cat = request.form.get("cat") or request.args.get("cat")
                if cat:
                    params["cat"] = cat
                return redirect(prefix + "/?" + urlencode(params))

        next_url = request.form.get("next")
        if next_url:
            return redirect(next_url)
        query_string = _build_redirect_params()
        redirect_path = f"{prefix}/?url={url}"
        if query_string:
            redirect_path += f"&{query_string}"
        return redirect(redirect_path)
    else:
        # If no URL, just redirect to prefix
        return redirect(prefix + "/")


@app.post("/note")
@app.post(f"{prefix}/note")
def note():
    global notes_dict, time_saved_notes
    url = request.form.get("url")
    note_content = request.form.get("note_content")

    # Add the new note to the notes list for this URL
    if url and note_content:
        timestamp = datetime.now()
        if url not in notes_dict:
            notes_dict[url] = []
        notes_dict[url].append((note_content, timestamp))

        # Save to disk
        if (datetime.now() - time_saved_notes).total_seconds() > 60:
            time_saved_notes = datetime.now()
            try:
                with open(PATH_NOTES, "w", encoding="utf-8") as file:
                    json.dump(serialize_notes(notes_dict), file)
            except OSError as e:
                logger.error("Cannot write notes file: %s", e)

    query_string = _build_redirect_params()
    redirect_path = f"{prefix}/?url={url}"
    if query_string:
        redirect_path += f"&{query_string}"
    return redirect(redirect_path)


@app.post("/flag_content")
@app.post(f"{prefix}/flag_content")
def flag_content():
    global flagged_content_dict, time_saved_flagged_content
    url = request.form.get("url")

    # Check if user has already flagged this URL using cookie
    flagged_urls_cookie = request.cookies.get("flagged_urls", "")
    flagged_urls = set(flagged_urls_cookie.split("|")) if flagged_urls_cookie else set()
    already_flagged = url in flagged_urls

    if url and not already_flagged:
        # Increment flagged content count
        flagged_content_dict[url] = flagged_content_dict.get(url, 0) + 1

        # Add URL to user's flagged set
        flagged_urls.add(url)

        # Save to disk
        if (datetime.now() - time_saved_flagged_content).total_seconds() > 60:
            time_saved_flagged_content = datetime.now()
            try:
                with open(PATH_FLAGGED, "w", encoding="utf-8") as file:
                    json.dump(flagged_content_dict, file)
            except OSError as e:
                logger.error("Cannot write flagged content file: %s", e)

    query_string = _build_redirect_params()

    # Create response with updated cookie
    response = make_response(redirect(f"{prefix}/?{query_string}"))

    # Store flagged URLs in cookie (max 100 URLs to prevent cookie size issues)
    flagged_urls_list = list(flagged_urls)[-100:]
    response.set_cookie(
        "flagged_urls",
        "|".join(flagged_urls_list),
        max_age=31536000,
        httponly=True,
        secure=True,
        samesite="Lax",
    )

    return response


@app.route("/get")
@app.route(f"{prefix}/get")
def get_page():
    return app.send_static_file("extension.html")


@app.route("/feed")
@app.route(f"{prefix}/feed")
def feed():
    """Per-mode Atom feed. Accepts the same query params as the main route."""
    if "recent" in request.args:
        cache = sorted(urls_cache, key=lambda e: e.updated, reverse=True)
        title = "Kagi Small Web - Recent"
        feed_url = "https://kagi.com/smallweb/feed?recent"
    elif "yt" in request.args:
        cache, title = urls_yt_cache, "Kagi Small Web - Videos"
        feed_url = "https://kagi.com/smallweb/feed?yt"
    # `?app` is kept as a legacy alias for older native-app builds.
    elif "liked" in request.args or "app" in request.args:
        cache, title = urls_liked_cache, "Kagi Small Web - Liked"
        feed_url = "https://kagi.com/smallweb/feed?liked"
    elif "gh" in request.args:
        cache, title = urls_gh_cache, "Kagi Small Web - Code"
        feed_url = "https://kagi.com/smallweb/feed?gh"
    elif "comic" in request.args:
        cache, title = urls_comic_cache, "Kagi Small Web - Comics"
        feed_url = "https://kagi.com/smallweb/feed?comic"
    else:
        cache, title = urls_cache, "Kagi Small Web"
        cat = request.args.get("cat", "")
        if cat and cat in CATEGORIES:
            title += f" - {CATEGORIES[cat][0]}"
            feed_url = f"https://kagi.com/smallweb/feed?cat={cat}"
            if cat == "uncategorized":
                cache = [
                    e
                    for e in cache
                    if not e.categories or "uncategorized" in e.categories
                ]
            else:
                cache = [e for e in cache if cat in e.categories]
        else:
            feed_url = "https://kagi.com/smallweb/feed"

    atom = AtomFeed(title, feed_url=feed_url)
    for entry in cache:
        atom.add(
            title=entry.title,
            content=entry.description,
            content_type="html",
            url=entry.link,
            updated=entry.updated,
            author=entry.author,
        )
    return Response(atom.to_string(), mimetype="application/atom+xml")


@app.route("/liked")
@app.route(f"{prefix}/liked")
# Keep `/appreciated` working for existing feed subscribers and older clients.
@app.route("/appreciated")
@app.route(f"{prefix}/appreciated")
def liked():
    global liked_feed
    return Response(liked_feed.to_string(), mimetype="application/atom+xml")


@app.route("/api/random")
@app.route(f"{prefix}/api/random")
def api_random():
    if "yt" in request.args:
        cache = urls_yt_cache
    # `?app` is kept as a legacy alias for older native-app builds.
    elif "liked" in request.args or "app" in request.args:
        cache = urls_liked_cache
    elif "gh" in request.args:
        cache = urls_gh_cache
    elif "comic" in request.args:
        cache = urls_comic_cache
    else:
        cache = urls_cache

    # Category filtering (blog mode only)
    cat = request.args.get("cat", "")
    if cat and cat in CATEGORIES and cache is urls_cache:
        if cat == "uncategorized":
            cache = [e for e in cache if not e.categories or "uncategorized" in e.categories]
        else:
            cache = [e for e in cache if cat in e.categories]

    if not cache:
        return jsonify({"error": "no posts available"}), 404

    seen = _get_seen(request)
    entry = _pick_unseen(cache, seen)
    domain = get_registered_domain(entry.link)
    domain = re.sub(r"^(www\.)?", "", domain)
    likes_total = sum(likes_dict.get(entry.link, OrderedDict()).values())

    response = jsonify({
        "url": entry.link,
        "title": entry.title,
        "author": entry.author,
        "domain": domain,
        "likes": likes_total,
        "categories": [
            [s, CATEGORIES[s][0], CATEGORIES[s][2]]
            for s in entry.categories if s in CATEGORIES
        ],
    })
    response.headers["Access-Control-Allow-Origin"] = "*"
    return _set_seen_cookie(response, seen, entry.link)


@app.route("/opml")
@app.route(f"{prefix}/opml")
def opml():
    global opml_cache
    if opml_cache is None:  # first call before update_all ran?
        opml_cache = generate_opml_feed()
    return Response(opml_cache, mimetype="text/x-opml+xml")


time_saved_likes = datetime.now()
time_saved_notes = datetime.now()
time_saved_flagged_content = datetime.now()

urls_cache = []
urls_yt_cache = []
urls_liked_cache = []
urls_gh_cache = []
urls_comic_cache = []
urls_flagged_cache = []

likes_dict = (
    _load_json(
        PATH_LIKES,
        lambda d: {url: OrderedDict(emojis) for url, emojis in d.items()},
    )
    or _load_json(
        PATH_FAVORITES_LEGACY,
        lambda d: {url: OrderedDict(emojis) for url, emojis in d.items()},
    )
    or {}
)
urls_liked_cache = []  # Initialize empty in case urls_cache isn't loaded yet
generate_liked_feed()  # Initialize the liked feed

notes_dict = _load_json(PATH_NOTES, deserialize_notes) or {}

flagged_content_dict = _load_json(PATH_FLAGGED) or {}


# get feeds
update_all()
update_embeddings()

opml_cache = generate_opml_feed()

# Update feeds every 5 minutes
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)
scheduler.add_job(update_embeddings, "interval", minutes=5)


def save_all_data():
    """Save all data before shutdown."""
    logger.info("Saving all data before shutdown...")
    try:
        save_likes()
        logger.info("Saved %d likes", len(likes_dict))
    except Exception as e:
        logger.error("Error saving likes: %s", e)

    try:
        with open(PATH_NOTES, "w", encoding="utf-8") as file:
            json.dump(serialize_notes(notes_dict), file)
            logger.info("Saved %d notes", len(notes_dict))
    except Exception as e:
        logger.error("Error saving notes: %s", e)

    try:
        with open(PATH_FLAGGED, "w", encoding="utf-8") as file:
            json.dump(flagged_content_dict, file)
            logger.info("Saved %d flagged items", len(flagged_content_dict))
    except Exception as e:
        logger.error("Error saving flagged content: %s", e)

atexit.register(save_all_data)
atexit.register(lambda: scheduler.shutdown())
