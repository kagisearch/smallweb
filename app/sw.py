import pickle
import requests
import re
from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    jsonify,
    Markup,
    render_template,
    make_response,
    Response
)
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

master_feed=False

DEFAULT_URL = "https://blog.kagi.com/small-web"

def update_all():
    global urls_cache, urls_yt_cache, master_feed

    #url = "http://127.0.0.1:4000"  # testing with local feed
    url = "https://kagi.com/api/v1/smallweb/feed/"
    
    check_feed = feedparser.parse(url)
    if (check_feed):
        master_feed=check_feed
    
    new_entries=update_entries(url + "?nso")  # no same origin sites feed
    
    if not bool(urls_cache) or bool(new_entries):
        urls_cache = new_entries
    
    new_entries = update_entries(url + "?yt")   # youtube sites

    if not bool(urls_yt_cache) or bool(new_entries):    
        urls_yt_cache = new_entries


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
                }
            )

        cache= [
            (entry["link"], entry["title"], entry["author"]) for entry in formatted_entries
        ]
        print(len(cache), "entries")
        return cache
    else:
        return False
    


def load_public_suffix_list(file_path):
    public_suffix_list = set()
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('//'):
                public_suffix_list.add(line)
    return public_suffix_list

# Load the list from your actual file path
public_suffix_list = load_public_suffix_list('public_suffix_list.dat')


def get_registered_domain(url):
    parsed_url = urlparse(url)
    netloc_parts = parsed_url.netloc.split('.')
    for i in range(len(netloc_parts)):
        possible_suffix = '.'.join(netloc_parts[i:])
        if possible_suffix in public_suffix_list:
            return '.'.join(netloc_parts[:i]) + '.' + possible_suffix
            

@app.route("/next")
def next_item():
    global urls_cache, urls_yt_cache

    url = request.args.get("url")
    is_youtube = "yt" in request.args
    cache = urls_yt_cache if is_youtube else urls_cache

    if cache and len(cache):
        url, _, _ = random.choice(cache)
    else:
        url = DEFAULT_URL

    redirect_to = f"/?yt&url={url}" if is_youtube else f"/?url={url}"
    return app.redirect(redirect_to, code=307)

@app.route("/")
def index():
    global urls_cache, urls_yt_cache

    url = request.args.get("url")
    is_youtube = "yt" in request.args
    cache = urls_yt_cache if is_youtube else urls_cache
    title = None

    if url is not None:
        http_url = url.replace("https://", "http://")
        title, author = next(
            (
                (url_tuple[1], url_tuple[2])
                for url_tuple in cache
                if url_tuple[0] == url or url_tuple[0] == http_url
            ),
            (None, None),
        )

    if title is None:
        query_params = request.args.copy()
        query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
        return app.redirect(f"/next?{query_string}", code=307)

    short_url = re.sub(r"^https?://(www\.)?", "", url)
    short_url = short_url.rstrip("/")
    
    domain = get_registered_domain(url)
    domain = re.sub(r"^(www\.)?", "", domain)

    videoid = ""
    is_youtube = 0

    if "youtube.com" in short_url:
        is_youtube = 1
        parsed_url = urlparse(url)
        videoid = parse_qs(parsed_url.query)["v"][0]

    # get favorites
    favorites_count = favorites_dict.get(url, 0)

    # Preserve all query parameters except 'url'
    query_params = request.args.copy()
    query_params.pop("url", None)
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    if query_string:
        query_string='?'+query_string

    # count notes
    notes_count = len(notes_dict.get(url, []))
    notes_list = notes_dict.get(url, [])
    
    if url.startswith('http://'):
        url = url.replace('http://', 'https://') # force https as http will not work inside https iframe anyway

    return render_template(
        "index.html",
        url=url,
        short_url=short_url,
        query_string=query_string,
        title=title,
        author=author,
        domain=domain,
        prefix=prefix+'/',
        videoid=videoid,
        is_youtube=is_youtube,
        favorites_count=favorites_count,
        notes_count=notes_count,
        notes_list=notes_list,
    )


@app.route("/favorite")
def favorite():
    global favorites_dict, time_saved_favorites
    url = request.args.get("url")

    if url:
        # Increment favorites count
        favorites_dict[url] = favorites_dict.get(url, 0) + 1

        # Save to disk
        if (datetime.now() - time_saved_favorites).total_seconds() > 60:
            time_saved_favorites = time_saved_favorites
            try:
                with open("favorites.pkl", "wb") as file:
                    pickle.dump(favorites_dict, file)
            except:
                print("can not write fav file")

    # Preserve all query parameters except 'url'

    query_params = request.args.copy()
    query_params.pop("url")
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())

    return redirect(prefix+f"/?url={url}&{query_string}")


@app.route("/note")
def note():
    global notes_dict, time_saved_notes
    url = request.args.get("url")
    note_content = request.args.get("note_content")

    # Add the new note to the notes list for this URL
    if url and note_content:
        timestamp = datetime.now()
        if url not in notes_dict:
            notes_dict[url] = []
        notes_dict[url].append((note_content, timestamp))

        # Save to disk
        if (datetime.now() - time_saved_notes).total_seconds() > 60:
            time_saved_notes = time_saved_favorites
            try:
                with open("data/notes.pkl", "wb") as file:
                    pickle.dump(notes_dict, file)
            except:
                print("can not write notes file")
    # Preserve all query parameters except 'url' and 'note_content'
    query_params = request.args.copy()
    query_params.pop("url")
    query_params.pop("note_content", None)  # Remove the note content
    query_string = "&".join(f"{key}={value}" for key, value in query_params.items())
    if query_string:
        query_string='?'+query_string

    if query_string:
        return redirect(prefix+f"/?url={url}&{query_string}")
    else:
        return redirect(prefix+f"/?url={url}")

@app.route("/appreciated")
def appreciated():
    global master_feed
    
    feed = AtomFeed(
            "Kagi Small Web Appreciated", feed_url="https://kagi.com/smallweb/appreciated"
        )
    count = 1
    
    if master_feed:        
        for entry in master_feed.entries:
            url=entry.link
            http_url=url.replace("https://", "http://")
            
            if (url in favorites_dict or url in notes_dict) or (http_url in favorites_dict or http_url  in notes_dict):

            
                count = count + 1
                feed.add(
                    entry.title,
                    getattr(entry, "summary", ""),
                    content_type="html",
                    url=entry.link,
                    updated=parse(entry.updated),
                    published=parse(entry.published),
                    author=getattr(entry, "author", ""),
                )
            
    return Response(feed.to_string(), mimetype="application/atom+xml")

    


time_saved_favorites = datetime.now()
time_saved_notes = datetime.now()

urls_cache = []
urls_yt_cache = []

favorites_dict = {}  # Dictionary to store favorites count

try:
    with open("data/favorites.pkl", "rb") as file:
        favorites_dict = pickle.load(file)
        print("Loaded favorites", len(favorites_dict))
except:
    print("No favorites data found.")


notes_dict = {}  # Dictionary to store notes

try:
    with open("data/notes.pkl", "rb") as file:
        notes_dict = pickle.load(file)
        print("Loaded notes", len(notes_dict))
except:
    print("No notes data found.")


# get feeds
update_all()

# Update feeds every 1 hour
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)


atexit.register(lambda: scheduler.shutdown())
