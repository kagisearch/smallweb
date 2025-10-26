# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r app/requirements.txt

# Run the Flask app locally
cd app
gunicorn --workers 1 --threads 4 sw:app
# Access at http://127.0.0.1:8000
```

### Docker Development
```bash
# Build and run with Docker
docker build -t smallweb .
docker run -p 8080:8080 smallweb
```

### Maintenance
```bash
# Crawl all feeds (expensive operation)
cd maintenance
./crawl.sh

# Process crawl results and clean up feeds
./process.sh
```

## Project Architecture

Kagi Small Web is a feed aggregation platform that curates and displays content from the "small web" - personal blogs, independent YouTube channels, and webcomics. The system operates as a Flask web application with background feed processing.

### Core Components

**Main Application (`app/sw.py`)**
- Flask web server serving random posts from curated feeds
- Background feed updates every 5 minutes using APScheduler
- User interaction features: emoji reactions, notes, content flagging
- Iframe embedding for seamless content viewing
- Multiple content modes: blogs, YouTube videos, GitHub projects, comics

**Feed Management System**
- `smallweb.txt`: Personal blog RSS/Atom feeds (~thousands of entries)
- `smallyt.txt`: YouTube channel feeds with subscriber/frequency limits
- `smallcomic.txt`: Independent webcomic feeds
- `yt_rejected.txt`: Rejected YouTube channels for reference

**Data Persistence**
- `data/favorites.pkl`: User emoji reactions stored as OrderedDict per URL
- `data/notes.pkl`: User notes with timestamps per URL  
- `data/flagged_content.pkl`: Content flagging counts

### Feed Processing Pipeline

1. **Ingestion**: Fetches from Kagi's Small Web API (`/api/v1/smallweb/feed/`)
2. **Filtering**: YouTube Shorts removal, image detection for comics
3. **Caching**: In-memory storage with periodic updates
4. **Generation**: Creates appreciated feed and OPML export

### User Features

- **Random Discovery**: Algorithmic selection from curated feeds
- **Content Types**: Blogs (`?mode=0`), YouTube (`?yt`), Appreciated (`?app`), GitHub (`?gh`), Comics (`?comic`)
- **Search**: Full-text search across titles, authors, descriptions
- **Reactions**: 14 emoji types with max 3 per URL, automatic feed inclusion
- **Personal Notes**: Timestamped annotations per URL
- **Content Moderation**: Community flagging system

## Deployment

The application deploys to Google Cloud Run with:
- GCS bucket mounting via gcsfuse for persistent data
- Cloud Build pipeline (`cloudbuild.yaml`)
- Service account with appropriate IAM permissions
- Auto-scaling with 2-4 instances