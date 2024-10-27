import pickle
import requests
import re
from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    jsonify,
    render_template,
    make_response,
    Response,
)
import feedparser
import feedparser
from dateutil.parser import parse
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
import atexit
from datetime import datetime
import os
import time
from urllib.parse import urlparse
from feedwerk.atom import AtomFeed, FeedEntry
#from opml import OpmlDocument

DIR_DATA = "data"
if not os.path.isdir(DIR_DATA):
    # trying to write a file in a non-existent dir
    # will fail, so we need to make sure this exists
    os.makedirs(DIR_DATA)
PATH_FAVORITES = os.path.join(DIR_DATA, "favorites.pkl")
PATH_NOTES = os.path.join(DIR_DATA, "notes.pkl")
PATH_FLAGGED = os.path.join(DIR_DATA, "flagged_content.pkl")


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
    global urls_cache, urls_app_cache, urls_yt_cache, urls_gh_cache, master_feed, favorites_dict

    #url = "http://127.0.0.1:4000"  # testing with local feed
    url = "https://kagi.com/api/v1/smallweb/feed/"

    try:
        print("begin update_all")
        check_feed = feedparser.parse(url)
        if check_feed and check_feed.entries and len(check_feed.entries):
            master_feed = check_feed

        new_entries = update_entries(url + "?nso")  # no same origin sites feed

        if not bool(urls_cache) or bool(new_entries):
            urls_cache = new_entries

        new_entries = update_entries(url + "?yt")  # youtube sites

        if not bool(urls_yt_cache) or bool(new_entries):
            urls_yt_cache = new_entries

        new_entries = update_entries(url + "?gh")  # github sitesgit push

        if not bool(urls_gh_cache) or bool(new_entries):
            urls_gh_cache = new_entries    
        
        # Prune favorites_dict to only include URLs present in urls_cache
        current_urls = set(entry[0] for entry in urls_cache)
        favorites_dict = {url: count for url, count in favorites_dict.items() if url in current_urls}
        
        # Build urls_app_cache from appreciated entries in urls_cache
        urls_app_cache = [entry for entry in urls_cache if entry[0] in favorites_dict]
       
    except:
        print("something went wrong during update_all")
    finally:
        print("end update_all")


def parse_date(date_string):
    # Manually parse the date string to handle the timezone offset
    date_format = "%a, %d %b %Y %H:%M:%S"
    date, offset_string = date_string.rsplit(" ", 1)
    offset_hours = int(offset_string[:-2])
    offset_minutes = int(offset_string[-2:])
    offset = timedelta(hours=offset_hours, minutes=offset_minutes)
    parsed_date = datetime.strptime(date, date_format)
    if offset_hours > 0:
        parsed_date -= offset
    else:
        parsed_date += offset
    return parsed_date.replace(tzinfo=timezone.utc)


def update_entries(url):
    feed = feedparser.parse(url)
    entries = feed.entries

    if len(entries):
        formatted_entries = []
        for entry in entries:
            domain = entry.link.split("//")[-1].split("/")[0]
            domain = domain.replace("www.", "")
            formatted_entries.append(
                {
                    "domain": domain,
                    "title": entry.title,
                    "link": entry.link,
                    "author": entry.author,
                    "description": entry.get('description', ''),
                }
            )

        cache = [
            (entry["link"], entry["title"], entry["author"], entry["description"])
            for entry in formatted_entries
        ]
        print(len(cache), "entries")
        return cache
    else:
        return False

def update_opml(get_urls=False):
    global opml_document

    print("Create OPML document")

    # metadata
    opml_document.date_created = datetime.now()
    opml_document.title = "Kagi Smallweb Feeds"

    with open("smallweb.txt") as f:
        for url in f:
            if get_urls:
                feed = feedparser.parse(url)
                desc = None
                title = None
                html_url = None
                if 'description' in feed['feed']:
                    desc = feed['feed']['description']
                if 'title' in feed['feed']:
                    title = feed['feed']['title']
                if 'link' in feed['feed']:
                    html_url = feed['feed']['link']
                opml_document.add_rss(url, url, title=title, description=desc, html_url=html_url, language="en_US")
            else:
                opml_document.add_rss(url, url, language="en_US")
    print("All OPML documents imported")

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
    else:
        cache = urls_cache

    if search_query.strip():  # Only perform search if query is not empty or just whitespace
        cache = [
            (url, title, author, description) for url, title, author, description in cache
            if search_query in url.lower() or 
            any(search_query.lower() == word.lower() for word in title.split()) or 
            any(search_query.lower() == word.lower() for word in author.split()) or 
            any(search_query.lower() == word.lower() for word in description.split())
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
                no_results=True
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
            url, title, author, description = random.choice(cache)
        else:
            url, title, author, description = (
                "https://blog.kagi.com/small-web",
                "Nothing to see",
                "Feed not active, try later",
                "",
            )

    short_url = re.sub(r"^https?://(www\.)?", "", url)
    short_url = short_url.rstrip("/")

    domain = get_registered_domain(url)
    domain = re.sub(r"^(www\.)?", "", domain)

    videoid = ""

    if "youtube.com" in short_url:
        parsed_url = urlparse(url)
        videoid = parse_qs(parsed_url.query)["v"][0]
        current_mode = 1

    # get favorites
    favorites_count = favorites_dict.get(url, 0)

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

    if url.startswith("http://"):
        url = url.replace(
            "http://", "https://"
        )  # force https as http will not work inside https iframe anyway

    # Calculate counts
    all_count = len(urls_cache) if urls_cache else 0
    appreciated_count = len(urls_app_cache) if urls_app_cache else 0
    videos_count = len(urls_yt_cache) if urls_yt_cache else 0
    code_count = len(urls_gh_cache) if urls_gh_cache else 0

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
        favorites_count=favorites_count,
        notes_count=notes_count,
        notes_list=notes_list,
        flag_content_count=flag_content_count,
        search_query=search_query,
        all_count=all_count,
        appreciated_count=appreciated_count,
        videos_count=videos_count,
        code_count=code_count,
    )


@app.post("/favorite")
def favorite():
    global favorites_dict, time_saved_favorites
    url = request.form.get("url")

    if url:
        # Increment favorites count
        favorites_dict[url] = favorites_dict.get(url, 0) + 1

        # Update urls_app_cache with the new favorite
        global urls_app_cache
        urls_app_cache = [entry for entry in urls_cache if entry[0] in favorites_dict]

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

    if url:
        # Increment favorites count
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
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

    # we do not want to redirect to same url
    # as that allows them to flag again
    return redirect(f"{prefix}/?{query_string}")


@app.route("/appreciated")
def appreciated():
    feed = AtomFeed(
        "Kagi Small Web Appreciated",
        feed_url="https://kagi.com/smallweb/appreciated"
    )

    # Add appreciated entries from urls_cache to the feed
    for url, title, author, description in urls_cache:
        if url in favorites_dict:
            feed.add(
                title=title,
                content=description,
                content_type="html",
                url=url,
                updated=datetime.utcnow(),
                author=author,
            )

    return Response(feed.to_string(), mimetype="application/atom+xml")

@app.route("/opml")
def opml():
    return Response(opml_document.dumps(), headers={"content-disposition":"attachment; filename=smallweb.opml"}, mimetype="text/x-opml")

time_saved_favorites = datetime.now()
time_saved_notes = datetime.now()
time_saved_flagged_content = datetime.now()

urls_cache = []
urls_yt_cache = []
urls_app_cache = []
urls_gh_cache = []

favorites_dict = {}  # Dictionary to store favorites count



try:
    with open(PATH_FAVORITES, "rb") as file:
        favorites_dict = pickle.load(file)
        print("Loaded favorites", len(favorites_dict))
except:
    print("No favorites data found.")
finally:
    # Initialize urls_app_cache based on favorites_dict
    urls_app_cache = []  # Initialize empty in case urls_cache isn't loaded yet


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


# get feeds
update_all()

# create opml document (only needs to run once)
#opml_document = OpmlDocument()
#update_opml()

# Update feeds every 1 hour
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)


atexit.register(lambda: scheduler.shutdown())
