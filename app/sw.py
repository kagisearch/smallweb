import pickle
import re
from flask import (
    Flask,
    request,
    redirect,
    render_template,
    Response,
    jsonify,
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

appreciated_feed = None  # Initialize the variable to store the appreciated Atom feed
opml_cache = None          # will hold generated OPML xml

# NOTE(z64): List of emotes that can be used for favoriting.
# Used to build the list in the template, and perform validation on the server.
favorite_emoji_list = ["👍","😍","😀","😘","😆","😜","🫶","😂","😱","🤔","👏","🚀","🥳","🔥"]

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
PATH_FAVORITES = os.path.join(DIR_DATA, "favorites.pkl")
PATH_NOTES = os.path.join(DIR_DATA, "notes.pkl")
PATH_FLAGGED = os.path.join(DIR_DATA, "flagged_content.pkl")
PATH_COMMENTS = os.path.join(DIR_DATA, "comments.pkl")
PATH_RATE_LIMITS = os.path.join(DIR_DATA, "rate_limits.pkl")
PATH_BANNED_IPS = os.path.join(DIR_DATA, "banned_ips.pkl")


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


def get_client_ip(request):
    """Get client IP, considering proxy headers"""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0]
    elif request.environ.get('HTTP_X_REAL_IP'):
        return request.environ['HTTP_X_REAL_IP']
    else:
        return request.environ.get('REMOTE_ADDR', '')


def detect_xss_attempt(content):
    """Detect potential XSS attempts in user content"""
    if not content:
        return False

    content_lower = content.lower()

    # Check for HTML tags commonly used in XSS
    xss_patterns = [
        '<script',
        '</script',
        '<iframe',
        '<embed',
        '<object',
        '<applet',
        '<meta',
        '<link',
        '<style',
        'javascript:',
        'data:text/html',
        'vbscript:',
        'onload=',
        'onerror=',
        'onclick=',
        'onmouseover=',
        'onfocus=',
        'onblur=',
        'onchange=',
        'onsubmit=',
        'onkeyup=',
        'onkeydown=',
        'onkeypress=',
        '<img',
        'src=',
        '<svg',
        '<body',
        '<input',
        '<form',
        '<button',
        'alert(',
        'confirm(',
        'prompt(',
        'document.',
        'window.',
        'eval(',
        '.cookie',
        '.location',
        'innerHTML',
        'outerHTML',
        'expression(',
        'import(',
        'fromcharcode',
        'string.fromcharcode',
        '&#x',  # Hex entities
        '&#0',  # Decimal entities
        '%3c',  # URL encoded <
        '%3e',  # URL encoded >
        '&lt;script',  # HTML entity encoded
        '&gt;',
        '&quot;',
        '&#39;',
        '&#x27;',
    ]

    # Check for suspicious patterns
    for pattern in xss_patterns:
        if pattern in content_lower:
            return True

    # Check for excessive HTML-like content (even if escaped)
    html_tag_count = content_lower.count('&lt;') + content_lower.count('&gt;')
    if html_tag_count > 10:  # Arbitrary threshold for excessive HTML
        return True

    # Check for base64 encoded content that might be malicious
    if 'base64,' in content_lower:
        return True

    return False


def check_rate_limit(ip):
    """Check if IP is rate limited"""
    global rate_limits_dict
    if ip in rate_limits_dict:
        time_diff = (datetime.now() - rate_limits_dict[ip]).total_seconds()
        if time_diff < 30:  # 30 second cooldown
            return False
    return True


def update_rate_limit(ip):
    """Update rate limit for IP and clean old entries"""
    global rate_limits_dict, time_saved_rate_limits
    rate_limits_dict[ip] = datetime.now()
    
    # Clean old entries (older than 1 hour)
    cutoff = datetime.now() - timedelta(hours=1)
    rate_limits_dict = {k: v for k, v in rate_limits_dict.items() if v > cutoff}
    
    # Save to disk periodically
    if (datetime.now() - time_saved_rate_limits).total_seconds() > 300:  # Save every 5 mins
        time_saved_rate_limits = datetime.now()
        try:
            with open(PATH_RATE_LIMITS, "wb") as file:
                pickle.dump(rate_limits_dict, file)
        except:
            print("Cannot write rate limits file")


def is_moderator(request):
    """Check if current user is a moderator"""
    mod_key = request.args.get('mod') or request.form.get('mod')
    secret_key = os.environ.get('MOD_SECRET_KEY', 'default_secret_key_change_me')
    return mod_key == secret_key


def get_all_recent_comments(limit=50):
    """Get recent comments across all URLs"""
    global comments_dict
    all_comments = []

    # Build a set of all current URLs in caches for quick lookup
    current_urls = set()
    for cache in [urls_cache, urls_yt_cache, urls_app_cache, urls_gh_cache, urls_comic_cache]:
        if cache:
            current_urls.update(entry[0] for entry in cache)
            # Also add http versions if https exists and vice versa
            for entry in cache:
                url = entry[0]
                if url.startswith("https://"):
                    current_urls.add(url.replace("https://", "http://"))
                elif url.startswith("http://"):
                    current_urls.add(url.replace("http://", "https://"))

    for url, url_comments in comments_dict.items():
        # Skip if URL is not in any cache
        if url not in current_urls:
            continue

        for comment in url_comments:
            if not comment.get('hidden', False) and not comment.get('mod_hidden', False):
                # Get title from cache
                title = "Unknown Page"
                for cache in [urls_cache, urls_yt_cache, urls_app_cache, urls_gh_cache, urls_comic_cache]:
                    for entry in cache:
                        if entry[0] == url or (url.startswith("http://") and entry[0] == url.replace("http://", "https://")) or (url.startswith("https://") and entry[0] == url.replace("https://", "http://")):
                            title = entry[1]
                            break
                    if title != "Unknown Page":
                        break

                all_comments.append({
                    **comment,
                    'url': url,
                    'page_title': title
                })

    # Sort by timestamp descending
    all_comments.sort(key=lambda x: x['timestamp'], reverse=True)
    return all_comments[:limit]


random.seed(time.time())


prefix = os.environ.get("URL_PREFIX", "")
app = Flask(__name__, static_url_path=prefix + "/static")
app.jinja_env.filters["time_ago"] = time_ago

master_feed = False


def cleanup_orphaned_comments():
    """Remove comments for URLs that are no longer in any cache"""
    global comments_dict, time_saved_comments

    # Build a set of all current URLs in caches
    current_urls = set()
    for cache in [urls_cache, urls_yt_cache, urls_app_cache, urls_gh_cache, urls_comic_cache]:
        if cache:
            for entry in cache:
                url = entry[0]
                current_urls.add(url)
                # Also add http/https variants
                if url.startswith("https://"):
                    current_urls.add(url.replace("https://", "http://"))
                elif url.startswith("http://"):
                    current_urls.add(url.replace("http://", "https://"))

    # Remove comments for URLs not in cache
    orphaned_urls = []
    for url in comments_dict.keys():
        if url not in current_urls:
            orphaned_urls.append(url)

    if orphaned_urls:
        print(f"Removing comments for {len(orphaned_urls)} URLs no longer in cache")
        for url in orphaned_urls:
            del comments_dict[url]

        # Save updated comments to disk
        try:
            with open(PATH_COMMENTS, "wb") as file:
                pickle.dump(comments_dict, file)
                print(f"Saved comments after cleanup")
        except Exception as e:
            print(f"Cannot write comments file during cleanup: {e}")

    return len(orphaned_urls)


def update_all():
    global urls_cache, urls_app_cache, urls_yt_cache, urls_gh_cache, urls_comic_cache, master_feed, favorites_dict, appreciated_feed, comments_dict

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

        # Generate the appreciated feed
        generate_appreciated_feed()

        # ---- NEW: update cached OPML ----
        global opml_cache
        opml_cache = generate_opml_feed()

        # Clean up orphaned comments
        cleanup_orphaned_comments()

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

            formatted_entries.append(
                {
                    "domain": domain,
                    "title": entry.title,
                    "link": entry.link,
                    "author": entry.author,
                    "description": entry.get('description', ''),
                    "updated": updated,
                }
            )

        cache = [
            (entry["link"], entry["title"], entry["author"], entry["description"], entry["updated"])
            for entry in formatted_entries
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


@app.route("/")
def index():
    global urls_cache, urls_yt_cache, urls_app_cache, urls_gh_cache

    url = request.args.get("url")
    search_query = request.args.get("search", "").lower()
    title = None
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
            )

    if url is not None:
        http_url = url.replace("https://", "http://")
        title, author, description = next(
            (
                (url_tuple[1], url_tuple[2], url_tuple[3])
                for url_tuple in cache
                if url_tuple[0] == url or url_tuple[0] == http_url
            ),
            (None, None, None),
        )

    if title is None:
        if cache and len(cache):
            url, title, author, _description, _date = random.choice(cache)
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
    
    # get comments for this URL - check both http and https versions
    url_comments = comments_dict.get(url, [])
    if not url_comments and url.startswith("https://"):
        # Try http version
        url_comments = comments_dict.get(url.replace("https://", "http://"), [])
    elif not url_comments and url.startswith("http://"):
        # Try https version
        url_comments = comments_dict.get(url.replace("http://", "https://"), [])
    
    visible_comments = [c for c in url_comments if not c.get('hidden', False) and not c.get('mod_hidden', False)]
    comments_count = len(visible_comments)
    
    # Debug logging
    print(f"[DEBUG] Looking for comments for URL: {url}")
    print(f"[DEBUG] Found {len(url_comments)} total comments, {len(visible_comments)} visible")
    if comments_dict:
        print(f"[DEBUG] URLs in comments_dict: {list(comments_dict.keys())[:5]}")
    
    # get recent comments
    recent_comments = get_all_recent_comments(50)
    
    # check if user is moderator
    is_mod = is_moderator(request)

    if url.startswith("http://"):
        url = url.replace(
            "http://", "https://"
        )  # force https as http will not work inside https iframe anyway

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
        comments=visible_comments,
        comments_count=comments_count,
        recent_comments=recent_comments,
        is_moderator=is_mod,
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

        # Save to disk
        if (datetime.now() - time_saved_favorites).total_seconds() > 60:
            time_saved_favorites = datetime.now()
            try:
                with open(PATH_FAVORITES, "wb") as file:
                    pickle.dump(favorites_dict, file)
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
                with open(PATH_NOTES, "wb") as file:
                    pickle.dump(notes_dict, file)
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

    # Check if user has already flagged this URL (prevent multiple flags)
    already_flagged = request.args.get("flagged") == url

    if url and not already_flagged:
        # Increment flagged content count
        flagged_content_dict[url] = flagged_content_dict.get(url, 0) + 1

        # Save to disk
        if (datetime.now() - time_saved_flagged_content).total_seconds() > 60:
            time_saved_flagged_content = datetime.now()
            try:
                with open(PATH_FLAGGED, "wb") as file:
                    pickle.dump(flagged_content_dict, file)
            except:
                print("can not write flagged content file")

    # Preserve all query parameters except 'url'
    query_params = request.args.copy()
    if "url" in query_params:
        del query_params["url"]
    
    # Add flagged parameter to prevent multiple flags for the same URL
    query_params["flagged"] = url if url else ""
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

    # we do not want to redirect to same url
    # as that allows them to flag again
    return redirect(f"{prefix}/?{query_string}")


@app.route("/appreciated")
def appreciated():
    global appreciated_feed
    return Response(appreciated_feed.to_string(), mimetype="application/atom+xml")

@app.route("/opml")
@app.route(f"{prefix}/opml")
def opml():
    global opml_cache
    if opml_cache is None:          # first call before update_all ran?
        opml_cache = generate_opml_feed()
    return Response(opml_cache, mimetype="text/x-opml+xml")


@app.post("/comment")
def add_comment():
    """Add a new comment"""
    global comments_dict, time_saved_comments
    
    # Check honeypot field (anti-spam)
    if request.form.get('website'):  # Honeypot field - should be empty
        return jsonify({'error': 'Invalid request'}), 400
    
    # Get client IP for rate limiting
    client_ip = get_client_ip(request)
    
    # Check if IP is banned
    if client_ip in banned_ips_dict:
        return jsonify({'error': 'You are not allowed to comment'}), 403
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        return jsonify({'error': 'Please wait 30 seconds between comments'}), 429
    
    # Get form data
    url = request.form.get('url')
    # Normalize URL to always use https for consistency
    if url and url.startswith("http://"):
        url = url.replace("http://", "https://")
    author = request.form.get('author', '').strip()
    content = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id')
    
    # Validate content
    if not content or len(content) < 3:
        return jsonify({'error': 'Comment too short'}), 400
    if len(content) > 2000:
        return jsonify({'error': 'Comment too long (max 2000 characters)'}), 400

    # Check for minimum word count (at least 2 words)
    word_count = len(content.split())
    if word_count < 2:
        return jsonify({'error': 'Comment must contain at least 2 words'}), 400

    # Check for XSS attempts
    if detect_xss_attempt(content) or detect_xss_attempt(author):
        # Log the attempt for monitoring
        print(f"[SECURITY] XSS attempt blocked from IP: {client_ip}")
        print(f"[SECURITY] Content: {content[:100]}...")  # Log first 100 chars

        # Add IP to banned list for persistent XSS attempts
        banned_ips_dict.add(client_ip)
        try:
            with open(PATH_BANNED_IPS, "wb") as file:
                pickle.dump(banned_ips_dict, file)
        except:
            print("Cannot write banned IPs file")

        return jsonify({'error': 'Invalid content detected. This incident has been logged.'}), 400

    # Default author name
    if not author:
        author = "Anonymous"
    
    # Create comment
    comment_id = str(uuid.uuid4())
    comment = {
        'id': comment_id,
        'author': escape(author),
        'content': escape(content),
        'timestamp': datetime.now(),
        'parent_id': parent_id,
        'reports': 0,
        'hidden': False,
        'mod_hidden': False
    }
    
    # Add to comments dict
    if url not in comments_dict:
        comments_dict[url] = []
    comments_dict[url].append(comment)
    
    # Update rate limit
    update_rate_limit(client_ip)
    
    # Save to disk immediately
    time_saved_comments = datetime.now()
    try:
        with open(PATH_COMMENTS, "wb") as file:
            pickle.dump(comments_dict, file)
            print(f"[DEBUG] Saved {len(comments_dict[url])} comments for {url}")
    except Exception as e:
        print(f"Cannot write comments file: {e}")
    
    # Redirect back to the page
    query_params = request.args.copy()
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    redirect_path = f"{prefix}/?url={url}"
    if query_string:
        redirect_path += f"&{query_string}"
    redirect_path += f"#comment-{comment_id}"
    return redirect(redirect_path)


@app.post("/report_comment")
def report_comment():
    """Report a comment as spam/inappropriate"""
    global comments_dict, time_saved_comments
    
    url = request.form.get('url')
    # Normalize URL
    if url and url.startswith("http://"):
        url = url.replace("http://", "https://")
    comment_id = request.form.get('comment_id')
    
    if url in comments_dict:
        for comment in comments_dict[url]:
            if comment['id'] == comment_id:
                comment['reports'] = comment.get('reports', 0) + 1
                # Auto-hide after 3 reports
                if comment['reports'] >= 3:
                    comment['hidden'] = True
                
                # Save to disk immediately
                try:
                    with open(PATH_COMMENTS, "wb") as file:
                        pickle.dump(comments_dict, file)
                        print(f"[DEBUG] Saved comments after report")
                except Exception as e:
                    print(f"Cannot write comments file: {e}")
                break
    
    # Redirect back
    query_params = request.args.copy()
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    redirect_path = f"{prefix}/?url={url}"
    if query_string:
        redirect_path += f"&{query_string}"
    return redirect(redirect_path)


@app.post("/moderate_comment")
def moderate_comment():
    """Moderate a comment (delete/hide) - requires mod access"""
    global comments_dict, time_saved_comments
    
    if not is_moderator(request):
        return jsonify({'error': 'Unauthorized'}), 403
    
    url = request.form.get('url')
    # Normalize URL
    if url and url.startswith("http://"):
        url = url.replace("http://", "https://")
    comment_id = request.form.get('comment_id')
    action = request.form.get('action')  # 'delete', 'hide', 'unhide'
    
    if url in comments_dict:
        if action == 'delete':
            # Remove comment entirely
            comments_dict[url] = [c for c in comments_dict[url] if c['id'] != comment_id]
        else:
            # Hide/unhide comment
            for comment in comments_dict[url]:
                if comment['id'] == comment_id:
                    if action == 'hide':
                        comment['mod_hidden'] = True
                    elif action == 'unhide':
                        comment['mod_hidden'] = False
                        comment['hidden'] = False  # Also clear user reports
                        comment['reports'] = 0
                    break
        
        # Save to disk immediately
        try:
            with open(PATH_COMMENTS, "wb") as file:
                pickle.dump(comments_dict, file)
                print(f"[DEBUG] Saved comments after moderation")
        except Exception as e:
            print(f"Cannot write comments file: {e}")
    
    # Redirect back
    query_params = request.args.copy()
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    redirect_path = f"{prefix}/?url={url}"
    if query_string:
        redirect_path += f"&{query_string}"
    return redirect(redirect_path)


@app.route("/recent_comments")
def recent_comments_json():
    """Get recent comments as JSON for dynamic loading"""
    recent = get_all_recent_comments(50)
    # Convert datetime objects to strings
    for comment in recent:
        comment['timestamp'] = comment['timestamp'].isoformat()
    return jsonify(recent)


time_saved_favorites = datetime.now()
time_saved_notes = datetime.now()
time_saved_flagged_content = datetime.now()
time_saved_comments = datetime.now()
time_saved_rate_limits = datetime.now()

urls_cache = []
urls_yt_cache = []
urls_app_cache = []
urls_gh_cache = []
urls_comic_cache = []

favorites_dict = {}  # Dictionary to store favorites count



try:
    with open(PATH_FAVORITES, "rb") as file:
        favorites_dict = pickle.load(file)
        print("Loaded favorites", len(favorites_dict))
        # ---- migrate old int-only data to emoji dict -------------------
        for u, v in list(favorites_dict.items()):
            if isinstance(v, int):
                favorites_dict[u] = OrderedDict({"👍": v})
except:
    print("No favorites data found.")
finally:
    # Initialize urls_app_cache based on favorites_dict
    urls_app_cache = []  # Initialize empty in case urls_cache isn't loaded yet
    generate_appreciated_feed()  # Initialize the appreciated feed


notes_dict = {}  # Dictionary to store notes

try:
    with open(PATH_NOTES, "rb") as file:
        notes_dict = pickle.load(file)
        print("Loaded notes", len(notes_dict))
except:
    print("No notes data found.")

flagged_content_dict = {}  # Dictionary to store favorites count

try:
    with open(PATH_FLAGGED, "rb") as file:
        flagged_content_dict = pickle.load(file)
        print("Loaded flagged content", len(flagged_content_dict))
except:
    print("No flagged content data found.")

comments_dict = {}  # Dictionary to store comments

try:
    with open(PATH_COMMENTS, "rb") as file:
        comments_dict = pickle.load(file)
        print("Loaded comments", sum(len(v) for v in comments_dict.values()))
except:
    print("No comments data found.")

rate_limits_dict = {}  # Dictionary to store rate limits

try:
    with open(PATH_RATE_LIMITS, "rb") as file:
        rate_limits_dict = pickle.load(file)
        print("Loaded rate limits", len(rate_limits_dict))
except:
    print("No rate limits data found.")

banned_ips_dict = set()  # Set to store banned IPs

try:
    with open(PATH_BANNED_IPS, "rb") as file:
        banned_ips_dict = pickle.load(file)
        print("Loaded banned IPs", len(banned_ips_dict))
except:
    print("No banned IPs data found.")


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
        with open(PATH_FAVORITES, "wb") as file:
            pickle.dump(favorites_dict, file)
            print(f"[DEBUG] Saved {len(favorites_dict)} favorites")
    except Exception as e:
        print(f"Error saving favorites: {e}")
    
    try:
        with open(PATH_NOTES, "wb") as file:
            pickle.dump(notes_dict, file)
            print(f"[DEBUG] Saved {len(notes_dict)} notes")
    except Exception as e:
        print(f"Error saving notes: {e}")
    
    try:
        with open(PATH_FLAGGED, "wb") as file:
            pickle.dump(flagged_content_dict, file)
            print(f"[DEBUG] Saved {len(flagged_content_dict)} flagged items")
    except Exception as e:
        print(f"Error saving flagged content: {e}")
    
    try:
        with open(PATH_COMMENTS, "wb") as file:
            pickle.dump(comments_dict, file)
            total_comments = sum(len(v) for v in comments_dict.values())
            print(f"[DEBUG] Saved {total_comments} comments across {len(comments_dict)} URLs")
    except Exception as e:
        print(f"Error saving comments: {e}")
    
    try:
        with open(PATH_RATE_LIMITS, "wb") as file:
            pickle.dump(rate_limits_dict, file)
            print(f"[DEBUG] Saved {len(rate_limits_dict)} rate limits")
    except Exception as e:
        print(f"Error saving rate limits: {e}")

atexit.register(save_all_data)
atexit.register(lambda: scheduler.shutdown())
