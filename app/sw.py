import re
import hashlib
import gzip
from flask import (
    Flask,
    request,
    redirect,
    render_template,
    Response,
    jsonify,
    make_response,
)
from html import escape
import feedparser
import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from urllib.parse import urlencode
import atexit
import os
import time
from urllib.parse import urlparse
from feedwerk.atom import AtomFeed
from collections import OrderedDict
import uuid
import json

# Category definitions — slug → label · description
CATEGORIES = OrderedDict([
    ("ai",           ("AI",                "LLMs · machine learning · AI tools · ethics · agents")),
    ("programming",  ("Programming",       "Coding · languages · frameworks · devtools · APIs · databases")),
    ("tech",         ("Technology",         "Tech news · apps · networking · social media")),
    ("sysadmin",     ("Sysadmin",           "Deployment · cloud · containers · CI/CD · networking · self-hosting")),
    ("hardware",     ("Hardware",           "Electronics · DIY · 3D printing · gadgets · home lab")),
    ("retro",        ("Retro",              "Vintage computers · DOS · BBS · demoscene · old software")),
    ("security",     ("Security",           "Infosec · privacy · OSINT · encryption · vulnerabilities")),
    ("science",      ("Science",            "Physics · biology · climate · math · space · medicine")),
    ("humanities",   ("Humanities",         "History · philosophy · language · linguistics · literature")),
    ("essays",       ("Essays",             "Long-form pieces · original arguments · in-depth analysis")),
    ("art",          ("Art & Design",       "Visual art · illustration · architecture · graphic design")),
    ("photography",  ("Photography",        "Cameras · photo essays · visual storytelling")),
    ("culture",      ("Pop Culture",        "Film · TV · music · books · fandom · comics")),
    ("gaming",       ("Gaming",             "Video games · tabletop RPGs · game dev · interactive fiction")),
    ("politics",     ("Politics",           "Government · policy · elections · law · political commentary")),
    ("economy",      ("Economy",            "Economics · finance · markets · business · labor · trade")),
    ("society",      ("Society",            "Social issues · civil rights · current events · community")),
    ("daily",        ("Daily Life",         "Personal updates · diary entries · day-to-day · mundane life")),
    ("life",         ("Life & Personal",    "Health · parenting · pets · personal growth · relationships")),
    ("food",         ("Food & Drink",       "Recipes · cooking · restaurants · coffee · wine · baking")),
    ("nature",       ("Nature & Outdoors",  "Hiking · travel · adventure · wildlife · gardening")),
    ("uncategorized",("Uncategorized",      "Posts that don\u2019t fit neatly into any topic")),
])

# Groups for dropdown display
CATEGORY_GROUPS = OrderedDict([
    ("Tech & Science",    ["ai", "programming", "tech", "sysadmin", "hardware", "retro", "security", "science"]),
    ("Culture & Creative",["humanities", "essays", "art", "photography", "culture", "gaming"]),
    ("Life & World",      ["politics", "economy", "society", "daily", "life", "food", "nature"]),
    ("Other",             ["uncategorized"]),
])

CATEGORY_SCHEME = "https://kagi.com/smallweb/categories"

appreciated_feed = None  # Initialize the variable to store the appreciated Atom feed
opml_cache = None          # will hold generated OPML xml

# Version tracking for appreciated feed (client-side random selection support)
appreciated_version = None  # sha1 hash of sorted URLs
appreciated_json_cache = None  # cached JSON response for /appreciated.json
appreciated_json_gzip = None  # gzipped version of JSON response

# NOTE(z64): List of emotes that can be used for favoriting.
# Used to build the list in the template, and perform validation on the server.
favorite_emoji_list = ["👍","😍","😀","😘","😆","😜","🫶","😂","😱","🤔","👏","🚀","🥳","🔥"]

def compute_appreciated_version(urls_list):
    """Compute sha1 hash of sorted URLs for version tracking.
    
    The version changes whenever the appreciated feed contents change
    (add/remove URLs, or if the canonical ordering changes).
    """
    sorted_urls = sorted(entry[0] for entry in urls_list)
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
    for idx, entry in enumerate(urls_app_cache):
        url_item, title, author, description, updated = entry
        # Generate stable ID from URL hash (consistent across restarts)
        item_id = hashlib.sha1(url_item.encode("utf-8")).hexdigest()[:12]
        urls_array.append({
            "id": item_id,
            "url": url_item,
            "title": title or "",
            "author": author or "",
        })
    
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
        "Kagi Small Web Appreciated",
        feed_url="https://kagi.com/smallweb/appreciated"
    )
    for url_entry in urls_app_cache:
        url_item, title, author, description, updated = url_entry
        appreciated_feed.add(
            title=title,
            content=description,
            content_type="html",
            url=url_item,
            updated=updated,
            author=author,
        )
    
    # Also regenerate JSON cache when feed changes
    generate_appreciated_json()

def generate_opml_feed() -> str:
    """Return OPML text that lists all cached Small-Web posts as RSS items."""
    outlines, seen = [], set()
    for feed in (urls_cache, urls_yt_cache, urls_app_cache,
                 urls_gh_cache, urls_comic_cache):
        for link, title, *_ in feed or []:
            if link in seen:
                continue
            seen.add(link)
            safe_title = escape(title or link, quote=True)
            outlines.append(
                f'    <outline text="{safe_title}" title="{safe_title}" '
                f'type="rss" xmlUrl="{link}" htmlUrl="{link}"/>'
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="1.0">\n'
        '  <head>\n'
        '    <title>Kagi Small Web OPML</title>\n'
        '  </head>\n'
        '  <body>\n' + "\n".join(outlines) + '\n  </body>\n</opml>'
    )

DIR_DATA = "data"
if not os.path.isdir(DIR_DATA):
    # trying to write a file in a non-existent dir
    # will fail, so we need to make sure this exists
    os.makedirs(DIR_DATA)
PATH_FAVORITES = os.path.join(DIR_DATA, "favorites.json")
PATH_NOTES = os.path.join(DIR_DATA, "notes.json")
PATH_FLAGGED = os.path.join(DIR_DATA, "flagged_content.json")

# Legacy paths for one-time migration to JSON
PATH_FAVORITES_LEGACY = os.path.join(DIR_DATA, "favorites.pkl")
PATH_NOTES_LEGACY = os.path.join(DIR_DATA, "notes.pkl")
PATH_FLAGGED_LEGACY = os.path.join(DIR_DATA, "flagged_content.pkl")


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




random.seed(time.time())


prefix = os.environ.get("URL_PREFIX", "")
app = Flask(__name__, static_url_path=prefix + "/static")
app.jinja_env.filters["time_ago"] = time_ago

master_feed = False


def update_all():
    global urls_cache, urls_app_cache, urls_yt_cache, urls_gh_cache, urls_comic_cache, urls_flagged_cache, master_feed, favorites_dict, appreciated_feed

    #url = "http://127.0.0.1:4000"  # testing with local feed
    url = "https://kagi.com/api/v1/smallweb/feed/"

    try:
        print("begin update_all")
        check_feed = feedparser.parse(url)
        if check_feed and check_feed.entries and len(check_feed.entries):
            master_feed = check_feed

        new_entries = update_entries(url + "?nso")  # no same origin sites feed

        if not bool(urls_cache) or bool(new_entries):
            # Filter out YouTube URLs from main feed
            urls_cache = [entry for entry in new_entries
                         if "youtube.com" not in entry[0] and "youtu.be" not in entry[0]]

        new_entries = update_entries(url + "?yt")  # youtube sites

        if not bool(urls_yt_cache) or bool(new_entries):
            # Filter out YouTube Shorts links
            urls_yt_cache = [entry for entry in new_entries if "/shorts/" not in entry[0]]

        new_entries = update_entries(url + "?gh")  # github sites

        if not bool(urls_gh_cache) or bool(new_entries):
            urls_gh_cache = new_entries

        new_entries = update_entries(url + "?comic")  # comic sites

        if not bool(urls_comic_cache) or bool(new_entries):
            # Filter entries that have images in content
            urls_comic_cache = [
                entry for entry in new_entries
                if entry[3] and ('<img' in entry[3] or '.png' in entry[3] or '.jpg' in entry[3] or '.jpeg' in entry[3])
            ]

        # Prune favorites_dict to only include URLs present in urls_cache or urls_yt_cache
        current_urls = set(entry[0] for entry in urls_cache + urls_yt_cache)
        favorites_dict = {url: count for url, count in favorites_dict.items() if url in current_urls}

        # Build urls_app_cache from appreciated entries in urls_cache and urls_yt_cache
        urls_app_cache = [e for e in (urls_cache + urls_yt_cache)
                          if e[0] in favorites_dict]

        # Build urls_flagged_cache from flagged entries in all caches
        urls_flagged_cache = [e for e in (urls_cache + urls_yt_cache + urls_gh_cache + urls_comic_cache)
                              if e[0] in flagged_content_dict]

        # Generate the appreciated feed
        generate_appreciated_feed()

        # ---- NEW: update cached OPML ----
        global opml_cache
        opml_cache = generate_opml_feed()


    except:
        print("something went wrong during update_all")
    finally:
        print("end update_all")


def update_entries(url):
    feed = feedparser.parse(url)
    entries = feed.entries

    if len(entries):
        formatted_entries = []
        for entry in entries:
            domain = entry.link.split("//")[-1].split("/")[0]
            domain = domain.replace("www.", "")
            updated = datetime.utcnow()
            updated_time = entry.get("updated_parsed", entry.get("published_parsed"))
            if updated_time:
                try:
                    updated = datetime.fromtimestamp(time.mktime(updated_time))
                except Exception:
                    pass

            # Parse category tags from Atom <category> elements
            categories = []
            for tag in entry.get('tags', []):
                term = tag.get('term', '')
                scheme = tag.get('scheme', '')
                if scheme == CATEGORY_SCHEME and term in CATEGORIES:
                    categories.append(term)

            formatted_entries.append(
                {
                    "domain": domain,
                    "title": entry.title,
                    "link": entry.link,
                    "author": entry.author,
                    "description": entry.get('description', ''),
                    "updated": updated,
                    "categories": categories,
                }
            )

        cache = [
            (entry["link"], entry["title"], entry["author"], entry["description"], entry["updated"], entry["categories"])
            for entry in formatted_entries
            if entry["link"].startswith("https://")  # Only allow https:// URLs for iframe embedding
        ]
        print(len(cache), "entries")
        return cache
    else:
        return False


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
    elif "viewflagged" in request.args:
        cache = urls_flagged_cache
        current_mode = 5
    else:
        cache = urls_cache

    if search_query.strip():  # Only perform search if query is not empty or just whitespace
        cache = [
            entry for entry in cache
            if (search_query in entry[0].lower() or  # url
                any(search_query.lower() == word.lower() for word in entry[1].split()) or  # title
                any(search_query.lower() == word.lower() for word in entry[2].split()) or  # author
                any(search_query.lower() == word.lower() for word in entry[3].split()))  # description
        ]
        if not cache:
            return render_template(
                "index.html",
                url="",
                short_url="",
                query_string="",
                title="No results found",
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
                # --- NEW: satisfy template ---
                reactions_dict=OrderedDict(),
                reactions_list=[],
                favorites_total=0,
                next_link="",
                next_doc_url="",
                next_host="",
                categories=CATEGORIES,
                category_groups=CATEGORY_GROUPS,
                current_cat="",
                category_counts={},
                post_categories=[],
            )

    # Category counts (before filtering, so user sees totals)
    category_counts = {}
    if current_mode == 0:
        for entry in cache:
            for cat_slug in entry[5]:
                category_counts[cat_slug] = category_counts.get(cat_slug, 0) + 1
            if not entry[5]:
                category_counts["uncategorized"] = category_counts.get("uncategorized", 0) + 1

    # Category filtering
    current_cat = request.args.get("cat", "")
    if current_cat and current_cat in CATEGORIES:
        if current_cat == "uncategorized":
            cache = [entry for entry in cache if not entry[5] or "uncategorized" in entry[5]]
        else:
            cache = [entry for entry in cache if current_cat in entry[5]]

        if not cache:
            return render_template(
                "index.html",
                url="",
                short_url="",
                query_string="",
                title="",
                author="",
                domain="",
                prefix=prefix + "/",
                videoid="",
                current_mode=current_mode,
                favorites_count=0,
                notes_count=0,
                notes_list=[],
                flag_content_count=0,
                search_query="",
                no_results=True,
                no_results_cat=current_cat,
                reactions_dict=OrderedDict(),
                reactions_list=[],
                favorites_total=0,
                next_link="",
                next_doc_url="",
                next_host="",
                categories=CATEGORIES,
                category_groups=CATEGORY_GROUPS,
                current_cat=current_cat,
                category_counts=category_counts,
                post_categories=[],
            )

    if url is not None:
        http_url = url.replace("https://", "http://")
        title, author, description, post_cats = next(
            (
                (url_tuple[1], url_tuple[2], url_tuple[3], url_tuple[5])
                for url_tuple in cache
                if url_tuple[0] == url or url_tuple[0] == http_url
            ),
            (None, None, None, []),
        )

    if title is None:
        if cache and len(cache):
            url, title, author, _description, _date, post_cats = random.choice(cache)
        else:
            url, title, author = (
                "https://blog.kagi.com/small-web",
                "Nothing to see",
                "Feed not active, try later"
            )

    # -------------------------------------------------
    # Build deterministic “next post” link and pre-load it
    # -------------------------------------------------
    next_link = None
    next_doc_url = None        # add this line (default)
    next_host    = None
    if cache:                                     # we have something to show next
        # try to pick a different entry from the same cache
        next_candidates = [e for e in cache if e[0] != url] or cache
        next_entry     = random.choice(next_candidates)
        next_params    = request.args.to_dict(flat=True)
        next_params["url"] = next_entry[0]        # set the url of the next post
        next_link = prefix + "/?" + urlencode(next_params)
        next_doc_url = next_entry[0]                       # remote URL itself
        host_parts   = urlparse(next_doc_url)
        next_host    = f"{host_parts.scheme}://{host_parts.netloc}"

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
    query_params = request.args.copy()
    query_params.pop("url", None)
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    if query_string:
        query_string = "?" + query_string

    # count notes
    notes_count = len(notes_dict.get(url, []))
    notes_list = notes_dict.get(url, [])

    # get flagged content
    flag_content_count = flagged_content_dict.get(url, 0)

    # Build (slug, label) tuples for the current post's categories
    post_categories = [(s, CATEGORIES[s][0]) for s in post_cats if s in CATEGORIES]

    if url.startswith("http://"):
        url = url.replace(
            "http://", "https://"
        )  # force https as http will not work inside https iframe anyway

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
        next_doc_url=next_doc_url,      #  ← add
        next_host=next_host,            #  ← add
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
    )


@app.post("/favorite")
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
            entry = OrderedDict()                      # initialise
        # enforce max 3 distinct emojis (drop oldest)
        if emoji not in entry and len(entry) >= 3:
            entry.popitem(last=False)
        entry[emoji] = entry.get(emoji, 0) + 1
        favorites_dict[url] = entry

        # Update urls_app_cache with the new favorite from both regular and YouTube feeds
        urls_app_cache = [e for e in (urls_cache + urls_yt_cache)
                          if e[0] in favorites_dict]
        
        # Regenerate the appreciated feed
        generate_appreciated_feed()

        # Save to disk immediately (multi-instance deployment requires immediate persistence)
        time_saved_favorites = datetime.now()
        try:
            with open(PATH_FAVORITES, "w", encoding="utf-8") as file:
                json.dump({url: dict(emojis) for url, emojis in favorites_dict.items()}, file)
        except:
            print("can not write fav file")

        # Preserve all query parameters except 'url'
        query_params = request.args.copy()
        if "url" in query_params:
            del query_params["url"]
        query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

        redirect_path = f"{prefix}/?url={url}"
        if query_string:
            redirect_path += f"&{query_string}"
        return redirect(redirect_path)
    else:
        # If no URL, just redirect to prefix
        return redirect(prefix + "/")


@app.post("/note")
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
            except:
                print("can not write notes file")
    # Preserve all query parameters except 'url' and 'note_content'
    query_params = request.args.copy()
    if "url" in query_params:
        del query_params["url"]
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

    redirect_path = f"{prefix}/?url={url}"
    if query_string:
        redirect_path += f"&{query_string}"
    return redirect(redirect_path)


@app.post("/flag_content")
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
            except:
                print("can not write flagged content file")

    # Preserve all query parameters except 'url'
    query_params = request.args.copy()
    if "url" in query_params:
        del query_params["url"]

    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

    # Create response with updated cookie
    response = make_response(redirect(f"{prefix}/?{query_string}"))

    # Store flagged URLs in cookie (max 100 URLs to prevent cookie size issues)
    flagged_urls_list = list(flagged_urls)[-100:]
    response.set_cookie("flagged_urls", "|".join(flagged_urls_list), max_age=31536000)  # 1 year

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
                cache = [e for e in cache if not e[5] or "uncategorized" in e[5]]
            else:
                cache = [e for e in cache if cat in e[5]]
        else:
            feed_url = "https://kagi.com/smallweb/feed"

    atom = AtomFeed(title, feed_url=feed_url)
    for url_item, entry_title, author, description, updated, *_ in cache:
        atom.add(
            title=entry_title,
            content=description,
            content_type="html",
            url=url_item,
            updated=updated,
            author=author,
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


@app.route("/opml")
@app.route(f"{prefix}/opml")
def opml():
    global opml_cache
    if opml_cache is None:          # first call before update_all ran?
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

favorites_dict = {}  # Dictionary to store favorites count

def load_favorites():
    """Load favorites from JSON, falling back to legacy format for migration."""
    global favorites_dict
    # Try JSON first
    if os.path.exists(PATH_FAVORITES):
        try:
            with open(PATH_FAVORITES, "r", encoding="utf-8") as f:
                data = json.load(f)
                favorites_dict = {url: OrderedDict(emojis) for url, emojis in data.items()}
                print("Loaded favorites from JSON", len(favorites_dict))
                return
        except Exception as e:
            print(f"Error loading favorites JSON: {e}")

    # Fall back to legacy format for migration
    if os.path.exists(PATH_FAVORITES_LEGACY):
        try:
            import pickle as pkl_migrate
            with open(PATH_FAVORITES_LEGACY, "rb") as f:
                favorites_dict = pkl_migrate.load(f)
                print("Migrating favorites from legacy format", len(favorites_dict))
                # Migrate old int-only data to emoji dict
                for u, v in list(favorites_dict.items()):
                    if isinstance(v, int):
                        favorites_dict[u] = OrderedDict({"👍": v})
                # Save as JSON immediately
                with open(PATH_FAVORITES, "w", encoding="utf-8") as jf:
                    json.dump({url: dict(emojis) for url, emojis in favorites_dict.items()}, jf)
                print("Migrated favorites to JSON format")
                return
        except Exception as e:
            print(f"Error migrating favorites: {e}")

    print("No favorites data found.")

load_favorites()
urls_app_cache = []  # Initialize empty in case urls_cache isn't loaded yet
generate_appreciated_feed()  # Initialize the appreciated feed


notes_dict = {}  # Dictionary to store notes

def load_notes():
    """Load notes from JSON, falling back to legacy format for migration."""
    global notes_dict
    # Try JSON first
    if os.path.exists(PATH_NOTES):
        try:
            with open(PATH_NOTES, "r", encoding="utf-8") as f:
                data = json.load(f)
                notes_dict = deserialize_notes(data)
                print("Loaded notes from JSON", len(notes_dict))
                return
        except Exception as e:
            print(f"Error loading notes JSON: {e}")

    # Fall back to legacy format for migration
    if os.path.exists(PATH_NOTES_LEGACY):
        try:
            import pickle as pkl_migrate
            with open(PATH_NOTES_LEGACY, "rb") as f:
                notes_dict = pkl_migrate.load(f)
                print("Migrating notes from legacy format", len(notes_dict))
                # Save as JSON immediately
                with open(PATH_NOTES, "w", encoding="utf-8") as jf:
                    json.dump(serialize_notes(notes_dict), jf)
                print("Migrated notes to JSON format")
                return
        except Exception as e:
            print(f"Error migrating notes: {e}")

    print("No notes data found.")

load_notes()

flagged_content_dict = {}  # Dictionary to store flagged content count

def load_flagged():
    """Load flagged content from JSON, falling back to legacy format for migration."""
    global flagged_content_dict
    # Try JSON first
    if os.path.exists(PATH_FLAGGED):
        try:
            with open(PATH_FLAGGED, "r", encoding="utf-8") as f:
                flagged_content_dict = json.load(f)
                print("Loaded flagged content from JSON", len(flagged_content_dict))
                return
        except Exception as e:
            print(f"Error loading flagged content JSON: {e}")

    # Fall back to legacy format for migration
    if os.path.exists(PATH_FLAGGED_LEGACY):
        try:
            import pickle as pkl_migrate
            with open(PATH_FLAGGED_LEGACY, "rb") as f:
                flagged_content_dict = pkl_migrate.load(f)
                print("Migrating flagged content from legacy format", len(flagged_content_dict))
                # Save as JSON immediately
                with open(PATH_FLAGGED, "w", encoding="utf-8") as jf:
                    json.dump(flagged_content_dict, jf)
                print("Migrated flagged content to JSON format")
                return
        except Exception as e:
            print(f"Error migrating flagged content: {e}")

    print("No flagged content data found.")

load_flagged()


# get feeds
update_all()

opml_cache = generate_opml_feed()

# Update feeds every 1 hour
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)


def save_all_data():
    """Save all data before shutdown"""
    print("[DEBUG] Saving all data before shutdown...")
    try:
        with open(PATH_FAVORITES, "w", encoding="utf-8") as file:
            json.dump({url: dict(emojis) for url, emojis in favorites_dict.items()}, file)
            print(f"[DEBUG] Saved {len(favorites_dict)} favorites")
    except Exception as e:
        print(f"Error saving favorites: {e}")

    try:
        with open(PATH_NOTES, "w", encoding="utf-8") as file:
            json.dump(serialize_notes(notes_dict), file)
            print(f"[DEBUG] Saved {len(notes_dict)} notes")
    except Exception as e:
        print(f"Error saving notes: {e}")

    try:
        with open(PATH_FLAGGED, "w", encoding="utf-8") as file:
            json.dump(flagged_content_dict, file)
            print(f"[DEBUG] Saved {len(flagged_content_dict)} flagged items")
    except Exception as e:
        print(f"Error saving flagged content: {e}")
    

atexit.register(save_all_data)
atexit.register(lambda: scheduler.shutdown())
