import atexit
import gzip
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


# Category definitions — slug → label · description · emoji
CATEGORIES = OrderedDict(
    [
        (
            "ai",
            (
                "AI",
                "LLMs · machine learning · AI tools · ethics · agents",
                "\U0001f916",
            ),
        ),
        (
            "programming",
            (
                "Programming",
                "Coding · languages · frameworks · devtools · APIs · databases",
                "\U0001f4bb",
            ),
        ),
        (
            "tech",
            (
                "Technology",
                "Tech news · apps · networking · social media",
                "\U0001f4f1",
            ),
        ),
        (
            "sysadmin",
            (
                "Sysadmin",
                "Deployment · cloud · containers · CI/CD · networking · hosting",
                "\u2601\ufe0f",
            ),
        ),
        (
            "hardware",
            ("Hardware", "Electronics · PCB design · gadgets · home lab", "\U0001f50c"),
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
            "security",
            (
                "Security",
                "Infosec · privacy · OSINT · encryption · vulnerabilities",
                "\U0001f510",
            ),
        ),
        (
            "science",
            (
                "Science",
                "Physics · biology · climate · math · space · medicine",
                "\U0001f52c",
            ),
        ),
        (
            "humanities",
            (
                "Humanities",
                "History · philosophy · language · linguistics · literature",
                "\U0001f4da",
            ),
        ),
        (
            "essays",
            (
                "Essays",
                "Long-form pieces · original arguments · in-depth analysis",
                "\U0001f4dd",
            ),
        ),
        (
            "art",
            (
                "Art & Design",
                "Visual art · illustration · architecture · graphic design",
                "\U0001f3a8",
            ),
        ),
        (
            "photography",
            (
                "Photography",
                "Cameras · photo essays · visual storytelling",
                "\U0001f4f7",
            ),
        ),
        (
            "culture",
            (
                "Pop Culture",
                "Film · TV · music · books · fandom · comics",
                "\U0001f37f",
            ),
        ),
        (
            "gaming",
            (
                "Gaming",
                "Video games · tabletop RPGs · game dev · interactive fiction",
                "\U0001f3ae",
            ),
        ),
        (
            "politics",
            (
                "Politics",
                "Government · policy · elections · law · political commentary",
                "\U0001f3db\ufe0f",
            ),
        ),
        (
            "economy",
            (
                "Economy",
                "Economics · finance · markets · business · labor · trade",
                "\U0001f4c8",
            ),
        ),
        (
            "society",
            (
                "Society",
                "Social issues · civil rights · current events · community",
                "\U0001f465",
            ),
        ),
        (
            "life",
            (
                "Life & Personal",
                "Health · parenting · pets · personal growth · relationships",
                "\U0001f49b",
            ),
        ),
        (
            "food",
            (
                "Food & Drink",
                "Recipes · cooking · restaurants · coffee · wine · baking",
                "\U0001f372",
            ),
        ),
        (
            "nature",
            (
                "Nature & Outdoors",
                "Hiking · travel · adventure · wildlife · gardening",
                "\U0001f333",
            ),
        ),
        (
            "indieweb",
            (
                "Indie web",
                "Personal publishing · blogs · digital gardens · federation",
                "\U0001f310",
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
                "sysadmin",
                "security",
            ],
        ),
        (
            "Culture & Creative",
            [
                "indieweb",
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
                "nature",
                "politics",
                "economy",
            ],
        ),
        ("Other", ["uncategorized"]),
    ]
)

appreciated_feed = None  # Initialize the variable to store the appreciated Atom feed
opml_cache = None  # will hold generated OPML xml

# Version tracking for appreciated feed (client-side random selection support)
appreciated_version = None  # sha1 hash of sorted URLs
appreciated_json_cache = None  # cached JSON response for /appreciated.json
appreciated_json_gzip = None  # gzipped version of JSON response

# NOTE(z64): List of emotes that can be used for favoriting.
# Used to build the list in the template, and perform validation on the server.
favorite_emoji_list = [
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


def compute_appreciated_version(urls_list):
    """Compute sha1 hash of sorted URLs for version tracking.

    The version changes whenever the appreciated feed contents change
    (add/remove URLs, or if the canonical ordering changes).
    """
    sorted_urls = sorted(entry.link for entry in urls_list)
    content = "\n".join(sorted_urls).encode("utf-8")
    return hashlib.sha1(content).hexdigest()[:16]


def generate_appreciated_json():
    """Generate and cache JSON representation of appreciated feed.

    Response format:
    {
        "version": "abc123...",  # sha1 hash of sorted URLs
        "urls": [
            {"id": "u1", "url": "https://...", "title": "...", "author": "..."},
            ...
        ]
    }
    """
    global appreciated_version, appreciated_json_cache, appreciated_json_gzip

    # Compute version from current appreciated list
    appreciated_version = compute_appreciated_version(urls_app_cache)

    # Build the urls array with minimal data per item
    urls_array = []
    for entry in urls_app_cache:
        # Generate stable ID from URL hash (consistent across restarts)
        item_id = hashlib.sha1(entry.link.encode("utf-8")).hexdigest()[:12]
        urls_array.append(
            {
                "id": item_id,
                "url": entry.link,
                "title": entry.title or "",
                "author": entry.author or "",
            }
        )

    # Build response object
    response_data = {
        "version": appreciated_version,
        "urls": urls_array,
    }

    # Cache JSON and gzipped version
    appreciated_json_cache = json.dumps(response_data, separators=(",", ":"))
    appreciated_json_gzip = gzip.compress(appreciated_json_cache.encode("utf-8"))

    return appreciated_json_cache


def generate_appreciated_feed():
    """Generate Atom feed for appreciated posts"""
    global appreciated_feed
    appreciated_feed = AtomFeed(
        "Kagi Small Web Appreciated", feed_url="https://kagi.com/smallweb/appreciated"
    )
    for entry in urls_app_cache:
        appreciated_feed.add(
            title=entry.title,
            content=entry.description,
            content_type="html",
            url=entry.link,
            updated=entry.updated,
            author=entry.author,
        )

    # Also regenerate JSON cache when feed changes
    generate_appreciated_json()


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
PATH_FAVORITES = os.path.join(DIR_DATA, "favorites.json")
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
        favorites_count=0,
        notes_count=0,
        notes_list=[],
        flag_content_count=0,
        search_query=search_query,
        no_results=True,
        no_results_cat=no_results_cat,
        reactions_dict=OrderedDict(),
        reactions_list=[],
        favorites_total=0,
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
        urls_app_cache, \
        urls_yt_cache, \
        urls_gh_cache, \
        urls_comic_cache, \
        urls_flagged_cache, \
        master_feed, \
        favorites_dict, \
        appreciated_feed

    url = "https://kagi.com/api/v1/smallweb/feed/"

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

        # Prune favorites_dict to only include URLs present in urls_cache or urls_yt_cache
        current_urls = set(entry.link for entry in urls_cache + urls_yt_cache)
        favorites_dict = {
            u: count for u, count in favorites_dict.items() if u in current_urls
        }

        # Build urls_app_cache from appreciated entries in urls_cache and urls_yt_cache
        urls_app_cache = [
            e for e in (urls_cache + urls_yt_cache) if e.link in favorites_dict
        ]

        # Build urls_flagged_cache from flagged entries in all caches
        urls_flagged_cache = [
            e
            for e in (urls_cache + urls_yt_cache + urls_gh_cache + urls_comic_cache)
            if e.link in flagged_content_dict
        ]

        # Generate the appreciated feed
        generate_appreciated_feed()

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
                if term in CATEGORIES:
                    categories.append(term)

            formatted_entries.append(
                FeedEntry(
                    link=link,
                    title=entry.get("title", ""),
                    author=entry.get("author", ""),
                    description=entry.get("description", "") or _extract_content(entry),
                    updated=updated,
                    categories=categories,
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
    global urls_cache, urls_yt_cache, urls_app_cache, urls_gh_cache, urls_flagged_cache

    url = request.args.get("url")
    search_query = request.args.get("search", "").lower()
    title = None
    post_cats = []
    current_mode = 0
    if "yt" in request.args:
        cache = urls_yt_cache
        current_mode = 1
    elif "app" in request.args:
        cache = urls_app_cache
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

    # Category filtering
    current_cat = request.args.get("cat", "")
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

    if title is None:
        if cache:
            chosen = random.choice(cache)
            url, title, author, post_cats = (
                chosen.link,
                chosen.title,
                chosen.author,
                chosen.categories,
            )
        else:
            url, title, author = (
                "https://blog.kagi.com/small-web",
                "Nothing to see",
                "Feed not active, try later",
            )

    # -------------------------------------------------
    # Build deterministic "next post" link and pre-load it
    # -------------------------------------------------
    next_link = None
    next_doc_url = None
    next_host = None
    if cache:
        next_candidates = [e for e in cache if e.link != url] or cache
        next_entry = random.choice(next_candidates)
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

    # get favorites
    reactions_dict = favorites_dict.get(url, OrderedDict())
    favorites_total = sum(reactions_dict.values())

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
    if current_mode == 1:
        feed_url = prefix + "/feed?yt"
    elif current_mode == 2:
        feed_url = prefix + "/feed?app"
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
    appreciated_count = len(urls_app_cache) if urls_app_cache else 0
    videos_count = len(urls_yt_cache) if urls_yt_cache else 0
    code_count = len(urls_gh_cache) if urls_gh_cache else 0
    comics_count = len(urls_comic_cache) if urls_comic_cache else 0

    # NOTE(z64): Some invalid reactions may be left over in the pkl file; filter them out.
    reactions_list = []
    for emoji, count in reactions_dict.items():
        if emoji in favorite_emoji_list:
            reactions_list.append((emoji, count))

    return render_template(
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
        appreciated_count=appreciated_count,
        videos_count=videos_count,
        code_count=code_count,
        comics_count=comics_count,
        next_link=next_link,
        next_doc_url=next_doc_url,
        next_host=next_host,
        reactions_list=reactions_list,
        favorites_total=favorites_total,
        favorite_emoji_list=favorite_emoji_list,
        reactions_dict=reactions_dict,
        categories=CATEGORIES,
        category_groups=CATEGORY_GROUPS,
        current_cat=current_cat,
        category_counts=category_counts,
        post_categories=post_categories,
        feed_url=feed_url,
        gh_meta=gh_meta,
    )


@app.post("/favorite")
@app.post(f"{prefix}/favorite")
def favorite():
    global favorites_dict, time_saved_favorites, urls_app_cache, appreciated_feed
    url = request.form.get("url")

    emoji = "👍"
    emoji_from_form = request.form.get("emoji")
    if emoji_from_form and emoji_from_form in favorite_emoji_list:
        emoji = emoji_from_form

    if url:
        entry = favorites_dict.get(url)
        if not isinstance(entry, OrderedDict):
            entry = OrderedDict()  # initialise
        # enforce max 3 distinct emojis (drop oldest)
        if emoji not in entry and len(entry) >= 3:
            entry.popitem(last=False)
        entry[emoji] = entry.get(emoji, 0) + 1
        favorites_dict[url] = entry

        # Update urls_app_cache with the new favorite from both regular and YouTube feeds
        urls_app_cache = [
            e for e in (urls_cache + urls_yt_cache) if e.link in favorites_dict
        ]

        # Regenerate the appreciated feed
        generate_appreciated_feed()

        # Save to disk immediately (multi-instance deployment requires immediate persistence)
        time_saved_favorites = datetime.now()
        try:
            with open(PATH_FAVORITES, "w", encoding="utf-8") as file:
                json.dump(
                    {u: dict(emojis) for u, emojis in favorites_dict.items()}, file
                )
        except OSError as e:
            logger.error("Cannot write favorites file: %s", e)

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


@app.route("/feed")
@app.route(f"{prefix}/feed")
def feed():
    """Per-mode Atom feed. Accepts the same query params as the main route."""
    if "yt" in request.args:
        cache, title = urls_yt_cache, "Kagi Small Web - Videos"
        feed_url = "https://kagi.com/smallweb/feed?yt"
    elif "app" in request.args:
        cache, title = urls_app_cache, "Kagi Small Web - Appreciated"
        feed_url = "https://kagi.com/smallweb/feed?app"
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


@app.route("/appreciated")
def appreciated():
    global appreciated_feed
    return Response(appreciated_feed.to_string(), mimetype="application/atom+xml")


@app.route("/smallweb/appreciated.json")
def appreciated_json():
    """Full appreciated feed as JSON for client-side random selection.

    Returns the complete list of appreciated URLs with version info.
    Supports ETag for conditional requests (304 Not Modified).

    Response:
    {
        "version": "abc123...",
        "urls": [
            {"id": "u1", "url": "https://...", "title": "...", "author": "..."},
            ...
        ]
    }
    """
    global appreciated_version, appreciated_json_cache, appreciated_json_gzip

    # Ensure cache exists
    if appreciated_json_cache is None:
        generate_appreciated_json()

    # Check for conditional request (ETag)
    etag = f'"{appreciated_version}"'
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and if_none_match == etag:
        response = make_response("", 304)
        response.headers["ETag"] = etag
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    # Check if client accepts gzip
    accept_encoding = request.headers.get("Accept-Encoding", "")
    if "gzip" in accept_encoding and appreciated_json_gzip:
        response = make_response(appreciated_json_gzip)
        response.headers["Content-Encoding"] = "gzip"
    else:
        response = make_response(appreciated_json_cache)

    response.headers["Content-Type"] = "application/json"
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"  # cache for 5 min
    response.headers["Access-Control-Allow-Origin"] = "*"  # CORS
    response.headers["Access-Control-Expose-Headers"] = "ETag"
    return response


@app.route("/api/random")
@app.route(f"{prefix}/api/random")
def api_random():
    if "yt" in request.args:
        cache = urls_yt_cache
    elif "app" in request.args:
        cache = urls_app_cache
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

    entry = random.choice(cache)
    domain = get_registered_domain(entry.link)
    domain = re.sub(r"^(www\.)?", "", domain)

    response = jsonify({
        "url": entry.link,
        "title": entry.title,
        "author": entry.author,
        "domain": domain,
        "categories": [
            [s, CATEGORIES[s][0], CATEGORIES[s][2]]
            for s in entry.categories if s in CATEGORIES
        ],
    })
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/opml")
@app.route(f"{prefix}/opml")
def opml():
    global opml_cache
    if opml_cache is None:  # first call before update_all ran?
        opml_cache = generate_opml_feed()
    return Response(opml_cache, mimetype="text/x-opml+xml")


time_saved_favorites = datetime.now()
time_saved_notes = datetime.now()
time_saved_flagged_content = datetime.now()

urls_cache = []
urls_yt_cache = []
urls_app_cache = []
urls_gh_cache = []
urls_comic_cache = []
urls_flagged_cache = []

favorites_dict = (
    _load_json(
        PATH_FAVORITES,
        lambda d: {url: OrderedDict(emojis) for url, emojis in d.items()},
    )
    or {}
)
urls_app_cache = []  # Initialize empty in case urls_cache isn't loaded yet
generate_appreciated_feed()  # Initialize the appreciated feed

notes_dict = _load_json(PATH_NOTES, deserialize_notes) or {}

flagged_content_dict = _load_json(PATH_FLAGGED) or {}


# get feeds
update_all()

opml_cache = generate_opml_feed()

# Update feeds every 5 minutes
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)


def save_all_data():
    """Save all data before shutdown."""
    logger.info("Saving all data before shutdown...")
    try:
        with open(PATH_FAVORITES, "w", encoding="utf-8") as file:
            json.dump({u: dict(emojis) for u, emojis in favorites_dict.items()}, file)
            logger.info("Saved %d favorites", len(favorites_dict))
    except Exception as e:
        logger.error("Error saving favorites: %s", e)

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
