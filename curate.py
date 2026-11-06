#!/usr/bin/env python3
"""
WideWeb Curate CLI (v3)
A local-first, durable web curation and bookmarking framework using the Content Sidecar pattern.
"""

import argparse
import csv
import email.utils
import gzip
import hashlib
import html
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import types
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, quote, unquote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from bs4 import BeautifulSoup
    from PIL import Image
    import trafilatura
    import blurhash
except ImportError as e:
    sys.exit(f"Missing dependency: {e}. Please run: python3 -m pip install requests beautifulsoup4 pillow trafilatura blurhash-python")

# Default vault path: ./vault or from environment variable
DEFAULT_VAULT = Path(os.environ.get("WIDEWEB_VAULT", os.environ.get("OPENCURATE_VAULT", Path(__file__).resolve().parent / "vault")))
DEFAULT_GCS_BUCKET = os.environ.get("WIDEWEB_GCS_BUCKET", "wideweb-assets-drew")
SCHEMA_URL = "https://raw.githubusercontent.com/dn0c/wideweb/main/schema/atom.schema.json"
SCHEMA_VERSION = 3

_HTTP_SESSION = None

def get_http_session() -> requests.Session:
    """Get or initialize a resilient HTTP session with connection pooling and exponential backoff retries."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
        _HTTP_SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 WideWeb/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=15, pool_maxsize=30)
        _HTTP_SESSION.mount("https://", adapter)
        _HTTP_SESSION.mount("http://", adapter)
    return _HTTP_SESSION


def sanitize_text(val) -> str | None:
    """Safely coerce any dict, list, or non-primitive object to clean string text."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("plain") or val.get("markdown") or val.get("html") or str(val)
    if isinstance(val, (list, tuple)):
        return ", ".join(str(x) for x in val)
    s = str(val).strip()
    return s if s else None


def get_db(vault_dir: Path) -> sqlite3.Connection:
    """Initialize or connect to the SQLite index database using the Clean Hybrid pattern with WAL mode."""
    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS atoms (
                -- System Envelope
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,           -- quote, note, link, image, video, file
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                
                -- Universal Curation
                atom_title TEXT NOT NULL,
                notes TEXT,
                tags TEXT,                    -- Stored as JSON array string: ["design", "systems"]
                collections TEXT,             -- Stored as JSON array string: ["reading-list"]
                visibility TEXT DEFAULT 'public', -- public, shared, private
                favorite INTEGER DEFAULT 0,
                
                -- Operational Anchors (Fast search, dedup, and existence checks)
                destination_url TEXT,
                cover_file_path TEXT,         -- Universal visual anchor (cover.png / cover.jpg)
                
                -- High-frequency Text Pointers
                text_content TEXT,
                source_url TEXT,
                author TEXT,
                
                -- Specialized & Descriptive Metadata JSON Bag
                metadata TEXT NOT NULL,
                
                -- Full Raw atom.json Document
                raw_json TEXT NOT NULL
            );
        """)
        # Ensure visibility column exists on older schemas
        cols = [c[1] for c in conn.execute("PRAGMA table_info(atoms);").fetchall()]
        if "visibility" not in cols:
            conn.execute("ALTER TABLE atoms ADD COLUMN visibility TEXT DEFAULT 'public';")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_kind ON atoms(kind);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_created ON atoms(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_dest_url ON atoms(destination_url) WHERE destination_url IS NOT NULL;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_source_url ON atoms(source_url) WHERE source_url IS NOT NULL;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_visibility ON atoms(visibility);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_fav ON atoms(favorite) WHERE favorite = 1;")
    return conn


def generate_atom_id() -> str:
    """Generate a chronological, unique atom ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_suffix = os.urandom(3).hex()
    return f"atm_{ts}_{rand_suffix}"


def normalize_tag(tag: str) -> str:
    """Normalize a single tag to universal lowercase kebab-style slug."""
    t = tag.strip().lstrip("#").lower()
    t = re.sub(r"[\s_]+", "-", t)
    t = re.sub(r"[^a-z0-9\.\-]", "", t)
    return t.strip("-")


def normalize_tags(tags_input) -> list[str]:
    """Normalize tags to universal lowercase tokens (hyphen-separated for multi-word)."""
    if not tags_input:
        return []
    if isinstance(tags_input, str):
        raw = [t.strip() for t in tags_input.split(",") if t.strip()]
    elif isinstance(tags_input, (list, tuple, set)):
        raw = [str(t).strip() for t in tags_input if str(t).strip()]
    else:
        return []

    cleaned = []
    seen = set()
    for t in raw:
        t_clean = normalize_tag(t)
        if t_clean and t_clean not in seen:
            seen.add(t_clean)
            cleaned.append(t_clean)
    return cleaned


def resolve_capture_provenance(args, default_method: str = "cli") -> dict:
    """Resolve capture_method, capture_id, and capture_url from command arguments or defaults."""
    method = getattr(args, "capture_method", None)
    cid = getattr(args, "capture_id", None)
    curl = getattr(args, "capture_url", None)

    # Backwards compatibility for arena_block_id
    if not cid and getattr(args, "arena_block_id", None):
        cid = str(args.arena_block_id)
        if not method:
            method = "arena"

    if not method:
        method = default_method

    if cid and not curl:
        if method == "arena":
            curl = f"https://www.are.na/block/{cid}"
        elif method == "instapaper":
            curl = f"https://www.instapaper.com/read/{cid}"

    return {
        "capture_method": method,
        "capture_id": str(cid) if cid is not None else None,
        "capture_url": curl
    }


def extract_dominant_colors(image_path: Path, num_colors: int = 3) -> list[str]:
    """Extract top dominant hex colors from an image using Pillow with safe mode normalization."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                background = Image.new("RGBA", img.size, (255, 255, 255))
                img = Image.alpha_composite(background, img).convert("RGB")
            else:
                img = img.convert("RGB")
            img.thumbnail((150, 150))
            quantized = img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
            palette = quantized.getpalette()[:num_colors * 3]
            hex_colors = []
            for i in range(0, len(palette), 3):
                r, g, b = palette[i], palette[i + 1], palette[i + 2]
                hex_colors.append(f"#{r:02X}{g:02X}{b:02X}")
            return hex_colors
    except Exception:
        return []


def compute_blurhash(image_path: Path) -> str | None:
    """Extract an ultra-compact blurhash string from an image with safe mode normalization."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                background = Image.new("RGBA", img.size, (255, 255, 255))
                img = Image.alpha_composite(background, img).convert("RGB")
            else:
                img = img.convert("RGB")
            img.thumbnail((100, 100))
            return blurhash.encode(img, x_components=4, y_components=3)
    except Exception:
        return None


def extract_article_content(html_text: str, url: str) -> dict:
    """Extract clean readable markdown article body and metadata using trafilatura."""
    try:
        extracted = trafilatura.extract(
            html_text,
            url=url,
            include_links=True,
            include_images=True,
            output_format="markdown"
        )
        meta = trafilatura.extract_metadata(html_text, default_url=url)
        word_count = len(extracted.split()) if extracted else 0
        return {
            "markdown": extracted,
            "word_count": word_count,
            "author": meta.author if meta else None,
            "published_at": meta.date if meta else None,
            "title": meta.title if meta else None
        }
    except Exception:
        return {"markdown": None, "word_count": 0, "author": None, "published_at": None, "title": None}


def scrape_url_metadata(url: str, extract_article: bool = True) -> dict:
    """Scrape Open Graph, favicon, and optionally article text from a URL with connection pooling and SSL fallback."""
    session = get_http_session()
    try:
        resp = session.get(url, timeout=(3.0, 12.0))
    except requests.exceptions.SSLError:
        resp = session.get(url, timeout=(3.0, 12.0), verify=False)
    resp.raise_for_status()

    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    domain = urlparse(url).netloc

    def get_meta(*names_or_props):
        for val in names_or_props:
            tag = soup.find("meta", attrs={"property": val}) or soup.find("meta", attrs={"name": val})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    # Title
    source_title = get_meta("og:title", "twitter:title")
    if not source_title and soup.title and soup.title.string:
        source_title = soup.title.string.strip()
    if not source_title:
        source_title = domain

    # Description
    description = get_meta("og:description", "twitter:description", "description")

    # Author
    author = get_meta("author", "article:author", "twitter:creator")

    # Site Name
    site_name = get_meta("og:site_name") or domain

    # Canonical URL
    canonical_tag = soup.find("link", rel="canonical")
    canonical_url = canonical_tag["href"] if canonical_tag and canonical_tag.get("href") else url

    # Favicon
    favicon_url = None
    icon_tag = soup.find("link", rel=lambda x: x and "icon" in x.lower())
    if icon_tag and icon_tag.get("href"):
        favicon_url = urljoin(url, icon_tag["href"])
    else:
        favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

    # Published date
    published_at = get_meta("article:published_time", "og:published_time", "date")

    # Primary Image URL
    image_url = get_meta("og:image", "twitter:image")
    if image_url:
        image_url = urljoin(url, image_url)

    # Clean Readability Article Body (Trafilatura)
    if extract_article:
        article_data = extract_article_content(html_text, url)
        if not author and article_data["author"]:
            author = article_data["author"]
        if not published_at and article_data["published_at"]:
            published_at = article_data["published_at"]
    else:
        article_data = {"markdown": None, "word_count": 0, "author": None, "published_at": None, "title": None}

    return {
        "source_title": source_title,
        "description": description,
        "author": author,
        "site_name": site_name,
        "canonical_url": canonical_url,
        "image_url": image_url,
        "favicon": favicon_url,
        "published_at": published_at,
        "article_markdown": article_data["markdown"],
        "article_word_count": article_data["word_count"]
    }


def download_image(image_url: str, dest_path: Path) -> dict:
    """Download an image asset and compute its metadata (dimensions, aspect ratio, blurhash, palette)."""
    session = get_http_session()
    try:
        resp = session.get(image_url, timeout=(3.0, 15.0))
    except requests.exceptions.SSLError:
        resp = session.get(image_url, timeout=(3.0, 15.0), verify=False)
    resp.raise_for_status()

    content = resp.content
    with open(dest_path, "wb") as f:
        f.write(content)

    file_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
    mime_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]

    dimensions = {"width": 0, "height": 0}
    aspect_ratio = None
    try:
        with Image.open(dest_path) as img:
            dimensions["width"], dimensions["height"] = img.size
            if dimensions["height"] > 0:
                aspect_ratio = round(dimensions["width"] / dimensions["height"], 3)
    except Exception:
        pass

    palette = extract_dominant_colors(dest_path, num_colors=3)
    blur_hash_str = compute_blurhash(dest_path)

    return {
        "hash": file_hash,
        "mime_type": mime_type,
        "dimensions": dimensions,
        "aspect_ratio": aspect_ratio,
        "blurhash": blur_hash_str,
        "color_palette": palette
    }


def extract_video_info(url: str) -> dict | None:
    """Detect if a URL is a video (YouTube, Vimeo) and fetch oEmbed metadata + thumbnail."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    # 1. YouTube
    if any(d in netloc for d in ["youtube.com", "youtu.be", "youtube-nocookie.com", "music.youtube.com"]):
        video_id = None
        if netloc == "youtu.be":
            video_id = parsed.path.lstrip("/").split("?")[0]
        elif parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            video_id = qs.get("v", [None])[0]
        elif parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                video_id = parts[1]

        if not video_id:
            return None

        clean_url = f"https://www.youtube.com/watch?v={video_id}"
        embed_url = f"https://www.youtube.com/embed/{video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={quote(clean_url)}&format=json"

        meta = {
            "provider": "YouTube",
            "video_id": video_id,
            "canonical_url": clean_url,
            "embed_url": embed_url,
            "title": "YouTube Video",
            "author": None,
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
            "favicon": "https://www.youtube.com/s/desktop/12d6b690/img/favicon_144x144.png"
        }

        try:
            session = get_http_session()
            resp = session.get(oembed_url, timeout=(3.0, 6.0))
            if resp.status_code == 200:
                d = resp.json()
                meta["title"] = d.get("title", meta["title"])
                meta["author"] = d.get("author_name")
                if d.get("thumbnail_url"):
                    meta["thumbnail_url"] = d["thumbnail_url"]
        except Exception as e:
            print(f"⚠️ YouTube oEmbed lookup warning: {e}")

        return meta

    # 2. Vimeo
    if "vimeo.com" in netloc:
        parts = [p for p in parsed.path.split("/") if p and p.isdigit()]
        video_id = parts[0] if parts else None
        clean_url = f"https://vimeo.com/{video_id}" if video_id else url
        oembed_url = f"https://vimeo.com/api/oembed.json?url={quote(clean_url)}"

        meta = {
            "provider": "Vimeo",
            "video_id": video_id,
            "canonical_url": clean_url,
            "embed_url": f"https://player.vimeo.com/video/{video_id}" if video_id else None,
            "title": "Vimeo Video",
            "author": None,
            "thumbnail_url": None,
            "favicon": "https://f.vimeocdn.com/images_v6/favicon_32.png"
        }

        try:
            session = get_http_session()
            resp = session.get(oembed_url, timeout=(3.0, 6.0))
            if resp.status_code == 200:
                d = resp.json()
                meta["title"] = d.get("title", meta["title"])
                meta["author"] = d.get("author_name")
                meta["thumbnail_url"] = d.get("thumbnail_url")
        except Exception:
            pass

        return meta

    return None


def fetch_youtube_transcript(video_id: str, cookies: str | None = None) -> dict | None:
    """Fetch subtitles/captions using youtube-transcript-api if available."""
    session = None
    if cookies and Path(cookies).exists():
        import http.cookiejar
        import requests
        session = requests.Session()
        cj = http.cookiejar.MozillaCookieJar(cookies)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
        except Exception as ce:
            print(f"⚠️ Cookie loading warning: {ce}")

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import IpBlocked
        ytt = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()
        transcript_list = ytt.list(video_id)

        # Priority: manual English -> any manual -> auto English -> any auto
        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except Exception:
            pass

        if not transcript:
            try:
                transcript = transcript_list.find_transcript(["en"])
            except Exception:
                pass

        if not transcript:
            for t in transcript_list:
                transcript = t
                break

        if not transcript:
            return None

        fetched = transcript.fetch()
        snippets = []
        plain_lines = []
        for s in fetched:
            sec = int(s.start)
            m, s_rem = divmod(sec, 60)
            h, m = divmod(m, 60)
            timestamp_str = f"{h}:{m:02d}:{s_rem:02d}" if h > 0 else f"{m}:{s_rem:02d}"
            clean_text = s.text.replace("\n", " ").strip()
            snippets.append({
                "start": round(s.start, 2),
                "duration": round(s.duration, 2),
                "timestamp": timestamp_str,
                "text": clean_text
            })
            plain_lines.append(f"[{timestamp_str}] {clean_text}")

        plain_text = "\n".join(plain_lines)
        speech_text = " ".join([s["text"] for s in snippets])

        return {
            "plain_text": plain_text,
            "speech_text": speech_text,
            "snippets": snippets,
            "language": transcript.language_code,
            "is_generated": transcript.is_generated
        }
    except IpBlocked:
        raise
    except Exception as e:
        return None


def transcribe_audio_whisper(audio_path: Path) -> dict | None:
    """Transcribe audio using faster-whisper if installed locally."""
    try:
        from faster_whisper import WhisperModel
        print("🧠 Running local speech-to-text with faster-whisper...")
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), beam_size=5)

        snippets = []
        plain_lines = []
        for segment in segments:
            sec = int(segment.start)
            m, s_rem = divmod(sec, 60)
            h, m = divmod(m, 60)
            timestamp_str = f"{h}:{m:02d}:{s_rem:02d}" if h > 0 else f"{m}:{s_rem:02d}"
            clean_text = segment.text.strip()
            snippets.append({
                "start": round(segment.start, 2),
                "duration": round(segment.end - segment.start, 2),
                "timestamp": timestamp_str,
                "text": clean_text
            })
            plain_lines.append(f"[{timestamp_str}] {clean_text}")

        return {
            "plain_text": "\n".join(plain_lines),
            "speech_text": " ".join([s["text"] for s in snippets]),
            "snippets": snippets,
            "language": info.language,
            "is_generated": True
        }
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️ Whisper transcription error: {e}")
        return None


def cmd_video(args):
    """Save a video stream (YouTube, Vimeo, etc.) with oEmbed metadata, embed link, and poster thumbnail."""
    vault_dir = Path(args.vault).resolve()
    print(f"🎬 Processing video from {args.url}...")
    video_info = extract_video_info(args.url)

    if not video_info:
        print("ℹ️ URL is not a recognized video provider. Falling back to web link.")
        return cmd_save_link(args)

    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    atom_title = args.title or video_info["title"]
    notes = getattr(args, "notes", None)
    if isinstance(notes, dict):
        notes = notes.get("plain") or notes.get("markdown") or str(notes)
    tags = normalize_tags(getattr(args, "tags", None))
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if getattr(args, "collection", None) else []

    # Prepare sidecar folder: vault/atoms/YYYY/MM/<atom_id>/
    now = datetime.now(timezone.utc)
    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Download Video Poster Thumbnail (Universal visual anchor)
    cover_meta = None
    cover_rel_path = None
    if video_info.get("thumbnail_url"):
        cover_filename = "cover.jpg"
        abs_cover_path = abs_folder / cover_filename
        try:
            print(f"📥 Downloading video poster thumbnail from {video_info['thumbnail_url']}...")
            downloaded = download_image(video_info["thumbnail_url"], abs_cover_path)
            cover_rel_path = str(rel_folder / cover_filename)
            cover_meta = {
                "file": cover_filename,
                "relative_path": cover_rel_path,
                "mime_type": downloaded["mime_type"],
                "hash": downloaded["hash"],
                "dimensions": downloaded["dimensions"],
                "aspect_ratio": downloaded["aspect_ratio"],
                "blurhash": downloaded["blurhash"],
                "color_palette": downloaded["color_palette"],
                "alt_text": atom_title
            }
        except Exception as e:
            print(f"⚠️ Failed to download poster thumbnail ({e})")

    # 2. Extract Transcript / Captions
    transcript_data = None
    if video_info.get("provider") == "YouTube" and video_info.get("video_id"):
        print(f"🎙️ Fetching captions/transcript for YouTube video {video_info['video_id']}...")
        transcript_data = fetch_youtube_transcript(video_info["video_id"])
        if transcript_data:
            print(f"✅ Found transcript: {len(transcript_data['snippets'])} snippets ({transcript_data['language']}, generated={transcript_data['is_generated']})")
        else:
            print("ℹ️ No captions or transcript available for this video.")

    transcript_txt_rel = None
    transcript_json_rel = None
    if transcript_data:
        txt_path = abs_folder / "transcript.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript_data["plain_text"])
        transcript_txt_rel = str(rel_folder / "transcript.txt")

        json_path = abs_folder / "transcript.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data["snippets"], f, indent=2)
        transcript_json_rel = str(rel_folder / "transcript.json")

    meta_bag = {
        "provider": video_info["provider"],
        "embed_url": video_info["embed_url"],
        "aspect_ratio": cover_meta["aspect_ratio"] if cover_meta else None,
        "blurhash": cover_meta["blurhash"] if cover_meta else None,
        "color_palette": cover_meta["color_palette"] if cover_meta else None,
        "favicon": video_info["favicon"],
        "has_transcript": bool(transcript_data),
        "transcript_snippets": len(transcript_data["snippets"]) if transcript_data else 0,
        "transcript_language": transcript_data["language"] if transcript_data else None
    }

    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

    cap_prov = resolve_capture_provenance(args, default_method="cli")

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": "video",
        "version": SCHEMA_VERSION,
        "created_at": now_iso,
        "updated_at": now_iso,
        "source": {
            "source_url": video_info.get("canonical_url") or args.url,
            "source_title": video_info["title"],
            "site_name": video_info["provider"],
            "author": video_info["author"],
            "published_at": None,
            "favicon": video_info["favicon"],
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "notes": notes,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": getattr(args, "favorite", False)
        },
        "content": {
            "cover_image": cover_meta,
            "text": None,
            "article": None,
            "video": {
                "provider": video_info["provider"],
                "embed_url": video_info["embed_url"],
                "duration_seconds": None,
                "transcript_file": transcript_txt_rel,
                "transcript_json": transcript_json_rel,
                "transcript_language": transcript_data["language"] if transcript_data else None,
                "transcript_is_generated": transcript_data["is_generated"] if transcript_data else None,
                "has_transcript": bool(transcript_data)
            },
            "file": None
        },
        "metadata_json": meta_bag
    }

    # Write atom.json
    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2)

    # Insert into SQLite
    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO atoms (
                id, kind, created_at, updated_at,
                atom_title, notes, tags, collections, visibility, favorite,
                destination_url, cover_file_path,
                text_content, source_url, author,
                metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "video", now_iso, now_iso,
            atom_title, notes, json.dumps(tags), json.dumps(collections),
            visibility, 1 if getattr(args, "favorite", False) else 0,
            video_info["canonical_url"], cover_rel_path,
            transcript_data["plain_text"] if transcript_data else None, args.url, video_info["author"],
            json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    print(f"\n🎬 Video atom saved successfully!")
    print(f"   ID:       {atom_id}")
    print(f"   Provider: {video_info['provider']}")
    print(f"   Title:    {atom_title}")
    print(f"   Channel:  {video_info['author'] or '—'}")
    print(f"   Folder:   {abs_folder}")
    return atom_doc


def cmd_bookmark(args):
    """Save a web bookmark (lightweight pointer with OG metadata and cover image, no article text)."""
    setattr(args, "target_kind", "bookmark")
    return cmd_save_link(args)


def cmd_article(args):
    """Save an article (full offline readability body, word count, reader view)."""
    setattr(args, "target_kind", "article")
    return cmd_save_link(args)


def cmd_save_link(args):
    """Save a URL into the vault, automatically detecting or respecting article vs bookmark."""
    # Auto-detect if this is a video URL (YouTube, Vimeo)
    if extract_video_info(args.url) and not getattr(args, "quote", None):
        return cmd_video(args)

    target_kind = getattr(args, "target_kind", None)
    if not target_kind:
        if getattr(args, "bookmark", False):
            target_kind = "bookmark"
        elif getattr(args, "article", False):
            target_kind = "article"

    want_article = (target_kind != "bookmark")
    vault_dir = Path(args.vault).resolve()
    print(f"🌐 Scraping {args.url} (extract_article={want_article})...")
    try:
        scraped = scrape_url_metadata(args.url, extract_article=want_article)
    except Exception as e:
        print(f"⚠️ Scraping failed ({e}), continuing with URL fallback.")
        scraped = {
            "source_title": urlparse(args.url).netloc,
            "description": None,
            "author": None,
            "site_name": urlparse(args.url).netloc,
            "canonical_url": args.url,
            "image_url": getattr(args, "image_url", None),
            "favicon": None,
            "published_at": None,
            "article_markdown": None,
            "article_word_count": 0
        }

    if getattr(args, "image_url", None):
        scraped["image_url"] = args.image_url

    # Determine kind
    if target_kind:
        kind = target_kind
    elif scraped.get("article_markdown") and scraped.get("article_word_count", 0) >= 100:
        kind = "article"
    else:
        kind = "bookmark"

    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    atom_title = args.title or scraped["source_title"]
    notes = args.notes or scraped["description"]
    if isinstance(notes, dict):
        notes = notes.get("plain") or notes.get("markdown") or str(notes)
    tags = normalize_tags(args.tags)
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []
    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

    # Prepare sidecar folder: vault/atoms/YYYY/MM/<atom_id>/
    now = datetime.now(timezone.utc)
    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # 1. Download Cover Image (The universal visual anchor)
    cover_meta = None
    cover_rel_path = None
    if scraped.get("image_url"):
        ext = os.path.splitext(urlparse(scraped["image_url"]).path)[1] or ".jpg"
        if len(ext) > 5 or not ext:
            ext = ".jpg"
        cover_filename = f"cover{ext}"
        abs_cover_path = abs_folder / cover_filename
        try:
            print(f"📥 Downloading cover image from {scraped['image_url']}...")
            downloaded = download_image(scraped["image_url"], abs_cover_path)
            cover_rel_path = str(rel_folder / cover_filename)
            cover_meta = {
                "file": cover_filename,
                "relative_path": cover_rel_path,
                "mime_type": downloaded["mime_type"],
                "hash": downloaded["hash"],
                "dimensions": downloaded["dimensions"],
                "aspect_ratio": downloaded["aspect_ratio"],
                "blurhash": downloaded["blurhash"],
                "color_palette": downloaded["color_palette"],
                "alt_text": scraped["source_title"]
            }
            print(f"🎨 Palette: {' '.join(downloaded['color_palette'])} | Ratio: {downloaded['aspect_ratio']}")
        except Exception as e:
            print(f"⚠️ Failed to download cover image: {e}")

    # 2. Save Offline Article Body (only for article kind)
    article_meta = None
    if kind == "article" and scraped.get("article_markdown") and scraped["article_word_count"] > 40:
        article_filename = "article.md"
        abs_article_path = abs_folder / article_filename
        with open(abs_article_path, "w", encoding="utf-8") as f:
            f.write(scraped["article_markdown"])
        article_meta = {
            "file": article_filename,
            "relative_path": str(rel_folder / article_filename),
            "word_count": scraped["article_word_count"],
            "byline": scraped["author"]
        }
        print(f"📖 Extracted offline article text ({scraped['article_word_count']} words -> article.md)")

    # 3. Text / Excerpt if provided
    text_meta = None
    quote_rel_path = None
    if getattr(args, "quote", None):
        quote_filename = "quote.md"
        abs_quote_path = abs_folder / quote_filename
        with open(abs_quote_path, "w", encoding="utf-8") as f:
            f.write(args.quote.strip())
        quote_rel_path = str(rel_folder / quote_filename)
        text_meta = {
            "file": quote_filename,
            "relative_path": quote_rel_path,
            "excerpt": args.quote.strip(),
            "word_count": len(args.quote.strip().split())
        }

    # Construct metadata JSON bag for specialized fields
    meta_bag = {
        "word_count": article_meta["word_count"] if article_meta else (text_meta["word_count"] if text_meta else None),
        "aspect_ratio": cover_meta["aspect_ratio"] if cover_meta else None,
        "blurhash": cover_meta["blurhash"] if cover_meta else None,
        "published_at": scraped.get("published_at"),
        "favicon": scraped.get("favicon")
    }

    cap_prov = resolve_capture_provenance(args, default_method="cli")

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": kind,
        "version": SCHEMA_VERSION,
        "created_at": now_iso,
        "updated_at": now_iso,
        "source": {
            "source_url": scraped.get("canonical_url") or args.url,
            "source_title": scraped["source_title"],
            "site_name": scraped["site_name"],
            "author": scraped["author"],
            "published_at": scraped.get("published_at"),
            "favicon": scraped.get("favicon"),
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "notes": notes,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": args.favorite
        },
        "content": {
            "cover_image": cover_meta,
            "text": text_meta,
            "article": article_meta,
            "video": None,
            "file": None
        },
        "metadata_json": meta_bag
    }

    # Write atom.json
    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2)

    # Insert into SQLite Clean Hybrid table
    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT INTO atoms (
                id, kind, created_at, updated_at, atom_title, notes, tags, collections,
                visibility, favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, kind, now_iso, now_iso, atom_title, notes, json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, args.url, cover_rel_path,
            args.quote.strip() if args.quote else None, args.url, scraped["author"],
            json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    emoji = "📖" if kind == "article" else "🔖"
    label = "Article" if kind == "article" else "Bookmark"
    print(f"\n{emoji} {label} atom saved successfully!")
    print(f"   ID:     {atom_id}")
    print(f"   Kind:   {kind}")
    print(f"   Title:  {atom_title}")
    print(f"   Folder: {abs_folder}")
    if tags:
        print(f"   Tags:   #{', #'.join(tags)}")
    return atom_doc


def cmd_quote(args):
    """Save a text quote / excerpt as an atom."""
    vault_dir = Path(args.vault).resolve()
    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)

    words = args.quote.strip().split()
    snippet_title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
    atom_title = args.title or snippet_title
    word_count = len(words)

    tags = normalize_tags(args.tags)
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []
    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Write quote.md
    quote_filename = "quote.md"
    abs_quote_path = abs_folder / quote_filename
    with open(abs_quote_path, "w", encoding="utf-8") as f:
        f.write(args.quote.strip())
    quote_rel_path = str(rel_folder / quote_filename)

    meta_bag = {
        "word_count": word_count,
        "author": args.author
    }

    cap_prov = resolve_capture_provenance(args, default_method="cli")

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": "quote",
        "version": SCHEMA_VERSION,
        "created_at": now_iso,
        "updated_at": now_iso,
        "source": {
            "source_url": args.source,
            "source_title": args.source_title,
            "site_name": urlparse(args.source).netloc if args.source else None,
            "author": args.author,
            "published_at": None,
            "favicon": None,
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "notes": args.notes,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": args.favorite
        },
        "content": {
            "cover_image": None,
            "text": {
                "file": quote_filename,
                "relative_path": quote_rel_path,
                "excerpt": args.quote.strip(),
                "word_count": word_count
            },
            "article": None,
            "video": None,
            "file": None
        },
        "metadata_json": meta_bag
    }

    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2)

    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT INTO atoms (
                id, kind, created_at, updated_at, atom_title, notes, tags, collections,
                visibility, favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "quote", now_iso, now_iso, atom_title, args.notes, json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, args.source, None,
            args.quote.strip(), args.source, args.author, json.dumps(meta_bag),
            json.dumps(atom_doc)
        ))

    print(f"\n✍️ Quote atom saved successfully!")
    print(f"   ID:     {atom_id}")
    print(f"   Kind:   quote ({word_count} words)")
    print(f"   Author: {args.author or 'Unknown'}")
    print(f"   Title:  {atom_title}")
    print(f"   Folder: {abs_folder}")
    return atom_doc


def cmd_note(args):
    """Save an original thought, reflection, or memo (no external source required)."""
    vault_dir = Path(args.vault).resolve()
    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)

    words = args.text.strip().split()
    snippet_title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
    atom_title = args.title or snippet_title
    word_count = len(words)

    tags = normalize_tags(args.tags)
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []
    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Write note.md
    note_filename = "note.md"
    abs_note_path = abs_folder / note_filename
    with open(abs_note_path, "w", encoding="utf-8") as f:
        f.write(args.text.strip())
    note_rel_path = str(rel_folder / note_filename)

    meta_bag = {"word_count": word_count}

    cap_prov = resolve_capture_provenance(args, default_method="cli")

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": "note",
        "version": SCHEMA_VERSION,
        "created_at": now_iso,
        "updated_at": now_iso,
        "source": {
            "source_url": None,
            "source_title": None,
            "site_name": None,
            "author": None,
            "published_at": None,
            "favicon": None,
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "notes": None,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": args.favorite
        },
        "content": {
            "cover_image": None,
            "text": {
                "file": note_filename,
                "relative_path": note_rel_path,
                "excerpt": args.text.strip(),
                "word_count": word_count
            },
            "article": None,
            "video": None,
            "file": None
        },
        "metadata_json": meta_bag
    }

    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2)

    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT INTO atoms (
                id, kind, created_at, updated_at, atom_title, notes, tags, collections,
                visibility, favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "note", now_iso, now_iso, atom_title, None, json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, None, None,
            args.text.strip(), None, None, json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    print(f"\n📝 Note atom saved successfully!")
    print(f"   ID:     {atom_id}")
    print(f"   Kind:   note ({word_count} words)")
    print(f"   Title:  {atom_title}")
    print(f"   Folder: {abs_folder}")
    return atom_doc


def cmd_image(args):
    """Save an image (photo, artwork, diagram) into the vault."""
    vault_dir = Path(args.vault).resolve()
    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    src = args.src.strip()
    is_url = src.startswith("http://") or src.startswith("https://")
    
    if is_url:
        ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
        if len(ext) > 5 or not ext:
            ext = ".jpg"
        cover_filename = f"cover{ext}"
        abs_cover_path = abs_folder / cover_filename
        downloaded = download_image(src, abs_cover_path)
    else:
        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            sys.exit(f"Image file not found: {src_path}")
        ext = src_path.suffix or ".jpg"
        cover_filename = f"cover{ext}"
        abs_cover_path = abs_folder / cover_filename
        with open(src_path, "rb") as fin, open(abs_cover_path, "wb") as fout:
            content = fin.read()
            fout.write(content)
        file_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
        with Image.open(abs_cover_path) as img:
            w, h = img.size
            ratio = round(w / h, 3) if h > 0 else None
        downloaded = {
            "hash": file_hash,
            "mime_type": f"image/{ext.lstrip('.')}",
            "dimensions": {"width": w, "height": h},
            "aspect_ratio": ratio,
            "blurhash": compute_blurhash(abs_cover_path),
            "color_palette": extract_dominant_colors(abs_cover_path)
        }

    cover_rel_path = str(rel_folder / cover_filename)
    atom_title = args.title or (Path(src).stem if not is_url else "Image")
    notes = getattr(args, "notes", None)
    if isinstance(notes, dict):
        notes = notes.get("plain") or notes.get("markdown") or str(notes)
    tags = normalize_tags(args.tags)
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []
    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

    meta_bag = {
        "aspect_ratio": downloaded["aspect_ratio"],
        "blurhash": downloaded["blurhash"],
        "color_palette": downloaded["color_palette"]
    }

    source_candidate = args.source or (src if is_url else None)
    author = args.author
    if not author and source_candidate:
        author = extract_author_from_url(source_candidate)

    # 1. Resolve or Auto-Generate Alt Text
    alt_text = getattr(args, "alt", None)
    try:
        import ai_enrich
        if not alt_text or ai_enrich.is_placeholder_alt(alt_text):
            generated_alt = ai_enrich.generate_image_alt_text(abs_cover_path)
            if generated_alt:
                alt_text = generated_alt
                print(f"   ✨ Auto-generated alt text: {alt_text}")
    except Exception as e:
        pass

    if not alt_text:
        alt_text = atom_title

    cap_prov = resolve_capture_provenance(args, default_method="cli")

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": "image",
        "version": SCHEMA_VERSION,
        "created_at": now_iso,
        "updated_at": now_iso,
        "source": {
            "source_url": source_candidate,
            "source_title": None,
            "site_name": author,
            "author": author,
            "published_at": None,
            "favicon": None,
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "notes": args.notes,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": args.favorite
        },
        "content": {
            "cover_image": {
                "file": cover_filename,
                "relative_path": cover_rel_path,
                "mime_type": downloaded["mime_type"],
                "hash": downloaded["hash"],
                "dimensions": downloaded["dimensions"],
                "aspect_ratio": downloaded["aspect_ratio"],
                "blurhash": downloaded["blurhash"],
                "color_palette": downloaded["color_palette"],
                "alt_text": alt_text
            },
            "text": None,
            "article": None,
            "video": None,
            "file": None
        },
        "metadata_json": meta_bag
    }

    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2)

    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT INTO atoms (
                id, kind, created_at, updated_at, atom_title, notes, tags, collections,
                visibility, favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "image", now_iso, now_iso, atom_title, args.notes, json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, args.source or source_candidate, cover_rel_path,
            None, source_candidate, author, json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    # 2. Sync to Are.na block if owned and connected
    try:
        import ai_enrich
        arena_bid = getattr(args, "arena_block_id", None) or ai_enrich.extract_arena_block_id(source_candidate)
        if arena_bid and alt_text:
            ok, msg = ai_enrich.push_arena_alt_text(arena_bid, alt_text)
            if ok:
                print(f"   ☁️ Synced alt text to Are.na block {arena_bid}")
            elif "cannot manage" not in msg:
                print(f"   ℹ️ Are.na sync: {msg}")
    except Exception:
        pass

    print(f"\n🖼️ Image atom saved successfully!")
    print(f"   ID:      {atom_id}")
    print(f"   Kind:    image")
    print(f"   Ratio:   {downloaded['aspect_ratio']} | Blurhash: {downloaded['blurhash']}")
    print(f"   Folder:  {abs_folder}")
    return atom_doc


def cmd_list(args):
    """List recent atoms in the vault, with optional filtering by kind, tag, or collection."""
    vault_dir = Path(args.vault).resolve()
    conn = get_db(vault_dir)
    query = "SELECT id, kind, created_at, atom_title, tags, cover_file_path, text_content, destination_url, metadata FROM atoms WHERE 1=1"
    params = []
    
    if args.kind:
        query += " AND kind = ?"
        params.append(args.kind)
    if args.tag:
        query += " AND tags LIKE ?"
        params.append(f"%{args.tag}%")
    if getattr(args, "visibility", None):
        query += " AND visibility = ?"
        params.append(args.visibility)
    if args.collection:
        query += " AND collections LIKE ?"
        params.append(f"%{args.collection}%")
    if getattr(args, "visibility", None):
        query += " AND visibility = ?"
        params.append(args.visibility)
        
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No matching atoms found in vault.")
        return

    kind_icons = {
        "quote": "✍️",
        "note": "📝",
        "link": "🔗",
        "image": "🖼️",
        "video": "🎬",
        "file": "📄"
    }

    print(f"\n📚 WideWeb Vault ({len(rows)} items shown):")
    print("─" * 80)
    for r in rows:
        icon = kind_icons.get(r["kind"], "📦")
        tags_list = json.loads(r["tags"]) if r["tags"] else []
        tag_str = " ".join([f"#{t}" for t in tags_list])
        
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        extras = []
        if meta.get("word_count"):
            extras.append(f"{meta['word_count']}w")
        if meta.get("aspect_ratio"):
            extras.append(f"{meta['aspect_ratio']} ratio")
        extra_str = f" ({', '.join(extras)})" if extras else ""

        print(f"{icon} [{r['kind'].upper()}] [{r['id']}]  {r['atom_title']}{extra_str}")
        if r["destination_url"]:
            print(f"    URL:  {r['destination_url']}")
        if tag_str:
            print(f"    Tags: {tag_str}")
        print(f"    Date: {r['created_at'][:10]}")
        print("─" * 80)


def get_atom_content_body(vault_dir: Path, r: sqlite3.Row) -> str:
    """Retrieve the primary textual body of an atom (article text, transcript, note, or quote)."""
    aid = r["id"]
    kind = r["kind"]
    created_at = r["created_at"]
    atom_folder = vault_dir / "atoms" / created_at[:4] / created_at[5:7] / aid

    if kind == "article":
        art_file = atom_folder / "article.md"
        if art_file.exists():
            try:
                with open(art_file, "r", encoding="utf-8") as af:
                    return af.read()
            except Exception:
                pass
    elif kind == "video":
        trans_file = atom_folder / "transcript.txt"
        if trans_file.exists():
            try:
                with open(trans_file, "r", encoding="utf-8") as tf:
                    return tf.read()
            except Exception:
                pass
    elif kind == "note":
        for fn in ("note.md", "note.txt"):
            nf = atom_folder / fn
            if nf.exists():
                try:
                    with open(nf, "r", encoding="utf-8") as nf_file:
                        return nf_file.read()
                except Exception:
                    pass
    elif kind == "quote":
        return r["text_content"] or ""

    return r["text_content"] or ""


def cmd_export(args):
    """Export atoms to third-party formats (NotebookLM, Obsidian, Bookmarks, Readwise, Are.na, Raindrop.io, Pinterest, RSS, BibTeX, JSONL, JSON)."""
    vault_dir = Path(args.vault).resolve()
    conn = get_db(vault_dir)
    query = "SELECT * FROM atoms WHERE 1=1"
    params = []
    if args.kind:
        query += " AND kind = ?"
        params.append(args.kind)
    if args.tag:
        query += " AND tags LIKE ?"
        params.append(f"%{args.tag}%")
    if getattr(args, "visibility", None):
        query += " AND visibility = ?"
        params.append(args.visibility)
    query += " ORDER BY created_at ASC"

    rows = conn.execute(query, params).fetchall()
    export_dir = vault_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    if args.target == "arena-csv":
        out_path = Path(args.out) if args.out else export_dir / "arena_export.csv"
        out_stream = open(out_path, "w", newline="", encoding="utf-8")
        writer = csv.writer(out_stream)
        writer.writerow(["Title", "Source", "Description"])

        for r in rows:
            title = r["atom_title"]
            source = r["destination_url"] or r["source_url"] or ""
            tags_list = json.loads(r["tags"]) if r["tags"] else []
            hashtags = " ".join([f"#{t}" for t in tags_list])
            parts = []
            if r["notes"]:
                parts.append(r["notes"])
            if r["text_content"]:
                parts.append(f'"{r["text_content"]}"')
            if hashtags:
                parts.append(hashtags)
            description = "\n\n".join(parts)
            writer.writerow([title, source, description])

        out_stream.close()
        print(f"✅ Exported {len(rows)} items for are.na/import/csv to: {out_path}")

    elif args.target in ("pinterest-csv", "pinterest"):
        out_path = Path(args.out) if args.out else export_dir / "pinterest_pins.csv"
        default_board = getattr(args, "board", None) or "WideWeb"

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"])

            for r in rows:
                title = (r["atom_title"] or "Untitled Pin")[:100]
                tags_list = json.loads(r["tags"]) if r["tags"] else []
                raw_json = json.loads(r["raw_json"])
                kind = r["kind"]
                dest_url = r["destination_url"] or r["source_url"] or ""

                if getattr(args, "board", None):
                    board = args.board
                elif tags_list:
                    board = f"{default_board}/{tags_list[0].replace('-', ' ').title()}"
                else:
                    board = default_board

                media_url = ""
                thumbnail = ""

                if kind == "video":
                    m = re.search(r"(?:v=|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", dest_url)
                    if m:
                        vid_id = m.group(1)
                        media_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                        thumbnail = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
                    else:
                        media_url = dest_url
                        thumbnail = "00:01"
                elif kind == "image":
                    media_url = r["source_url"] or dest_url
                else:
                    media_url = dest_url

                desc_text = r["notes"] or (r["text_content"][:490] if r["text_content"] else "")
                desc = (desc_text or title)[:500]
                keywords = ", ".join(tags_list)
                link = dest_url
                publish_date = ""

                writer.writerow([title, media_url, board, thumbnail, desc, link, publish_date, keywords])

        print(f"✅ Exported {len(rows)} items for Pinterest bulk upload to: {out_path}")

    elif args.target in ("raindrop-csv", "raindrop"):
        out_path = Path(args.out) if args.out else export_dir / "raindrop_export.csv"
        default_folder = getattr(args, "folder", None) or "WideWeb"

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["folder", "url", "title", "note", "tags", "created"])

            for r in rows:
                url = r["destination_url"] or r["source_url"] or ""
                if not url:
                    continue

                title = r["atom_title"] or "Untitled"

                cols = json.loads(r["collections"]) if r["collections"] else []
                if getattr(args, "folder", None):
                    folder = args.folder
                elif cols:
                    folder = f"{default_folder}/{cols[0].replace('-', ' ').title()}"
                else:
                    folder = f"{default_folder}/{r['kind'].capitalize()}s"

                parts = []
                if r["notes"]:
                    parts.append(r["notes"])
                if r["text_content"] and r["kind"] == "quote":
                    parts.append(f'"{r["text_content"]}"')
                note = "\n\n".join(parts) if parts else (r["notes"] or "")

                tags_list = json.loads(r["tags"]) if r["tags"] else []
                tags_str = ", ".join(tags_list)

                created = r["created_at"] or ""

                writer.writerow([folder, url, title, note, tags_str, created])

        print(f"✅ Exported {len(rows)} items for Raindrop.io CSV import to: {out_path}")

    elif args.target in ("digest", "llms", "notebooklm"):
        out_path = Path(args.out) if args.out else export_dir / "vault_digest.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# WideWeb Vault Knowledge Digest",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Total Curated Atoms: {len(rows)}",
            f"\n> This document is a unified compilation of curated articles, video transcripts, notes, quotes, and bookmarks from the WideWeb vault. Optimized for analysis, indexing, and synthesis in NotebookLM, Claude Projects, and local LLMs.\n",
            "---"
        ]

        for r in rows:
            aid = r["id"]
            kind = r["kind"]
            title = r["atom_title"]
            date_str = r["created_at"][:10]
            author = r["author"] or "—"
            url = r["destination_url"] or r["source_url"] or "—"
            tags_list = json.loads(r["tags"]) if r["tags"] else []
            tag_str = ", ".join([f"#{t}" for t in tags_list]) if tags_list else "None"
            notes = r["notes"]
            body = get_atom_content_body(vault_dir, r)

            kind_emoji = {
                "article": "📖",
                "bookmark": "🔖",
                "video": "🎬",
                "quote": "✍️",
                "note": "📝",
                "image": "🎨",
                "file": "📄"
            }.get(kind, "•")

            lines.append(f"\n## {kind_emoji} [{kind.upper()}] {title}")
            lines.append(f"- **Atom ID**: `{aid}`")
            lines.append(f"- **Date**: {date_str}")
            if author and author != "—":
                lines.append(f"- **Author / Channel**: {author}")
            if url and url != "—":
                lines.append(f"- **URL**: {url}")
            lines.append(f"- **Tags**: {tag_str}")
            if notes:
                lines.append(f"- **Curator Notes**: {notes}")

            if body:
                section_title = {
                    "article": "### Full Article Text",
                    "video": "### Spoken Dialogue & Transcript",
                    "note": "### Note Body",
                    "quote": "### Attributed Quote"
                }.get(kind, "### Content")
                lines.append(f"\n{section_title}\n\n{body.strip()}")

            lines.append("\n---")

        output_text = "\n".join(lines)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"✅ Generated NotebookLM/LLM Knowledge Digest: {out_path} ({len(rows)} atoms, {len(output_text.split())} words)")

    elif args.target == "llms-txt":
        out_path = Path(args.out) if args.out else export_dir / "llms.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# WideWeb Vault Index",
            f"> Curated knowledge base of articles, bookmarks, videos, and notes.\n"
        ]
        for r in rows:
            title = r["atom_title"]
            url = r["destination_url"] or r["source_url"] or f"atoms/{r['id']}"
            desc = r["notes"] or (r["text_content"][:120] if r["text_content"] else "")
            lines.append(f"- [{title}]({url}): {desc}")

        output_text = "\n".join(lines)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"✅ Generated standard llms.txt index: {out_path}")

    elif args.target in ("obsidian", "logseq"):
        out_zip = Path(args.out) if args.out else export_dir / "vault_obsidian.zip"
        obsidian_folder = export_dir / "obsidian"
        obsidian_folder.mkdir(parents=True, exist_ok=True)

        zip_files = []
        for r in rows:
            aid = r["id"]
            kind = r["kind"]
            title = r["atom_title"]
            clean_title = re.sub(r'[\/\\:\*\?"<>\|]+', '_', title).strip()
            filename = f"{clean_title[:60]}_{aid[-6:]}.md"
            tags_list = json.loads(r["tags"]) if r["tags"] else []

            fm = [
                "---",
                f"id: \"{aid}\"",
                f"title: \"{title.replace('\"', '\\\"')}\"",
                f"kind: {kind}",
                f"date: \"{r['created_at'][:10]}\"",
                f"created_at: \"{r['created_at']}\""
            ]
            url = r["destination_url"] or r["source_url"]
            if url:
                fm.append(f"url: \"{url}\"")
            if r["author"]:
                fm.append(f"author: \"{r['author'].replace('\"', '\\\"')}\"")
            if tags_list:
                fm.append("tags:")
                for t in tags_list:
                    fm.append(f"  - {t}")
            else:
                fm.append("tags: []")
            fm.append("---\n")

            content_lines = [
                "\n".join(fm),
                f"# {title}\n"
            ]
            if url:
                content_lines.append(f"> **Source**: [{url}]({url})\n")
            if r["notes"]:
                content_lines.append(f"### Curator Notes\n\n{r['notes']}\n")

            body = get_atom_content_body(vault_dir, r)
            if body:
                content_lines.append(f"### Content\n\n{body.strip()}\n")

            note_content = "\n".join(content_lines)
            note_path = obsidian_folder / filename
            with open(note_path, "w", encoding="utf-8") as nf:
                nf.write(note_content)
            zip_files.append((note_path, filename))

        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for n_path, z_name in zip_files:
                zf.write(n_path, arcname=z_name)

        print(f"✅ Exported {len(rows)} atoms to Obsidian/Logseq vault archive: {out_zip}")

    elif args.target in ("bookmarks-html", "bookmarks", "netscape"):
        out_path = Path(args.out) if args.out else export_dir / "bookmarks.html"
        lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            "<!-- This is an automatically generated file. -->",
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>WideWeb Bookmarks</TITLE>",
            "<H1>WideWeb Bookmarks</H1>",
            "<DL><p>"
        ]
        for r in rows:
            url = r["destination_url"] or r["source_url"]
            if not url:
                continue
            try:
                dt = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                ts = int(dt.timestamp())
            except Exception:
                ts = int(time.time())
            tags_list = json.loads(r["tags"]) if r["tags"] else []
            tag_str = html.escape(",".join(tags_list))
            title = html.escape(r["atom_title"])
            notes = html.escape(r["notes"] or (r["text_content"][:200] if r["text_content"] else ""))
            lines.append(f'    <DT><A HREF="{html.escape(url)}" ADD_DATE="{ts}" TAGS="{tag_str}">{title}</A>')
            if notes:
                lines.append(f'    <DD>{notes}')
        lines.append("</DL><p>")

        output_text = "\n".join(lines)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"✅ Exported universal Netscape HTML bookmarks: {out_path}")

    elif args.target == "readwise":
        out_path = Path(args.out) if args.out else export_dir / "readwise.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Highlight", "Title", "Author", "URL", "Note", "Location"])
            for r in rows:
                kind = r["kind"]
                body = get_atom_content_body(vault_dir, r)
                highlight = body[:1000] if body else (r["notes"] or r["atom_title"])
                title = r["atom_title"]
                author = r["author"] or ""
                url = r["destination_url"] or r["source_url"] or ""
                notes = r["notes"] or ""
                writer.writerow([highlight, title, author, url, notes, r["id"]])
        print(f"✅ Exported {len(rows)} items for Readwise to: {out_path}")

    elif args.target in ("rss", "feed"):
        out_path = Path(args.out) if args.out else export_dir / "feed.xml"
        now_rfc822 = email.utils.format_datetime(datetime.now(timezone.utc))
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            '  <channel>',
            '    <title>WideWeb Curation Vault</title>',
            '    <link>http://127.0.0.1:8080/</link>',
            '    <description>Personal local-first curation stream</description>',
            f'    <lastBuildDate>{now_rfc822}</lastBuildDate>'
        ]
        for r in rows:
            url = r["destination_url"] or r["source_url"] or f"http://127.0.0.1:8080/#atom-{r['id']}"
            try:
                dt = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                pub_date = email.utils.format_datetime(dt)
            except Exception:
                pub_date = now_rfc822
            tags_list = json.loads(r["tags"]) if r["tags"] else []
            body = get_atom_content_body(vault_dir, r)
            desc_parts = []
            if r["notes"]:
                desc_parts.append(f"<p><strong>Curator Notes:</strong> {html.escape(r['notes'])}</p>")
            if body:
                desc_parts.append(f"<div>{html.escape(body[:2000])}</div>")
            desc_html = "".join(desc_parts)

            lines.append('    <item>')
            lines.append(f'      <title>{html.escape(r["atom_title"])}</title>')
            lines.append(f'      <link>{html.escape(url)}</link>')
            lines.append(f'      <guid isPermaLink="false">{r["id"]}</guid>')
            lines.append(f'      <pubDate>{pub_date}</pubDate>')
            if r["author"]:
                lines.append(f'      <author>{html.escape(r["author"])}</author>')
            for t in tags_list:
                lines.append(f'      <category>{html.escape(t)}</category>')
            lines.append(f'      <description><![CDATA[{desc_html}]]></description>')
            lines.append('    </item>')

        lines.append('  </channel>')
        lines.append('</rss>')
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"✅ Generated RSS 2.0 syndication feed: {out_path}")

    elif args.target in ("bibtex", "bib"):
        out_path = Path(args.out) if args.out else export_dir / "vault.bib"
        bib_entries = []
        for r in rows:
            aid = r["id"]
            kind = r["kind"]
            title = r["atom_title"].replace("{", "\\{").replace("}", "\\}")
            author = (r["author"] or "WideWeb Vault").replace("{", "\\{").replace("}", "\\}")
            url = r["destination_url"] or r["source_url"] or ""
            year = r["created_at"][:4]
            tags_list = json.loads(r["tags"]) if r["tags"] else []
            keywords = ", ".join(tags_list)

            if kind == "article":
                entry = f"""@article{{{aid},
  title = {{{title}}},
  author = {{{author}}},
  year = {{{year}}},
  url = {{{url}}},
  keywords = {{{keywords}}}
}}"""
            elif kind == "video":
                entry = f"""@misc{{{aid},
  title = {{{title}}},
  author = {{{author}}},
  howpublished = {{Video Stream}},
  year = {{{year}}},
  url = {{{url}}},
  keywords = {{{keywords}}}
}}"""
            else:
                entry = f"""@misc{{{aid},
  title = {{{title}}},
  author = {{{author}}},
  year = {{{year}}},
  url = {{{url}}},
  note = {{{r['notes'] or ''}}},
  keywords = {{{keywords}}}
}}"""
            bib_entries.append(entry)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(bib_entries) + "\n")
        print(f"✅ Exported {len(rows)} BibTeX citations to: {out_path}")

    elif args.target == "jsonl":
        out_path = Path(args.out) if args.out else export_dir / "vault.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for r in rows:
                atom_doc = json.loads(r["raw_json"])
                f.write(json.dumps(atom_doc) + "\n")
        print(f"✅ Exported {len(rows)} atoms to JSONL: {out_path}")

    elif args.target == "json":
        out_path = Path(args.out) if args.out else export_dir / "vault_backup.json"
        atoms_list = [json.loads(r["raw_json"]) for r in rows]
        content = json.dumps(atoms_list, indent=2)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Exported {len(rows)} atoms to JSON: {out_path}")


BRAND_MAP = {
    "hypebeast.com": "Hypebeast",
    "hypb.st": "Hypebeast",
    "highsnobiety.com": "Highsnobiety",
    "flickr.com": "Flickr",
    "instagram.com": "Instagram",
    "pinterest.com": "Pinterest",
    "pinimg.com": "Pinterest",
    "drakes.com": "Drake's",
    "freundevonfreunden.com": "Freunde von Freunden",
    "gq.com": "GQ",
    "document-document.com": "Document Journal",
    "dieworkwear.com": "Die, Workwear!",
    "permanentstyle.com": "Permanent Style",
    "hodinkee.com": "Hodinkee",
    "sprezza.xyz": "Sprezza",
    "blackbirdspyplane.com": "Blackbird Spyplane",
    "themodernhouse.com": "The Modern House",
    "3sixteen.com": "3sixteen",
    "18east.co": "18 East",
    "noahny.com": "Noah",
    "dwell.com": "Dwell",
    "reddit.com": "Reddit",
    "imgur.com": "Imgur",
    "500px.com": "500px",
    "thecoolist.com": "The Coolist",
    "theradavist.com": "The Radavist",
    "acontinuouslean.com": "A Continuous Lean",
    "americantrench.com": "American Trench",
    "blessthisstuff.com": "Bless This Stuff",
    "buckmason.com": "Buck Mason",
    "evankinori.com": "Evan Kinori",
    "grailed.com": "Grailed",
    "heddels.com": "Heddels",
    "hoka.com": "Hoka",
    "mrporter.com": "MR PORTER",
    "oakstreetbootmakers.com": "Oak Street Bootmakers",
    "putthison.com": "Put This On",
    "ribbonfarm.com": "Ribbonfarm",
    "sneakernews.com": "Sneaker News",
    "sneakerbardetroit.com": "Sneaker Bar Detroit",
    "viberg.com": "Viberg",
    "well-spent.com": "Well Spent",
    "whitemountaineering.com": "White Mountaineering",
    "wornandwound.com": "Worn & Wound",
    "leica-camera.com": "Leica",
    "metalabel.com": "Metalabel",
    "maggieappleton.com": "Maggie Appleton",
    "drewshannon.net": "Drew Shannon",
    "chrisglass.com": "Chris Glass",
    "jonaspeterson.com": "Jonas Peterson",
    "bijansabet.com": "Bijan Sabet",
    "ricknunn.com": "Rick Nunn",
    "raindrop.io": "Raindrop",
    "exposure.co": "Exposure",
    "cargocollective.com": "Cargo",
    "deviantart.com": "DeviantArt",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "esquire.com": "Esquire",
    "revolution.watch": "Revolution Watch",
    "orologidiclasse.com": "Orologi di Classe",
    "watchesbysjx.com": "SJX Watches",
    "sehkelly.com": "S.E.H Kelly",
    "goodart.com": "Good Art HLYWD",
    "thesecondbutton.com": "The Second Button",
    "5280.com": "5280 Magazine",
    "tapperietbrus.dk": "BRUS",
    "conceptsurplus.com": "Concept Surplus",
    "constant-practice.com": "Constant Practice",
    "denimhunters.com": "Denimhunters",
    "profoundmagazine.com": "Profound Magazine",
    "rideyourbike.com": "Ride Your Bike",
    "theclassyissue.com": "The Classy Issue",
    "decolonialfutures.net": "Decolonial Futures",
    "nowdeveloping.photos": "Now Developing",
    "paynter.co.uk": "Paynter Jacket",
    "asahishoes.jp": "Asahi Shoes",
    "sattalivity.com": "Satta",
    "strato.co.jp": "Strato",
    "strato.jp": "Strato",
    "streetnine.com": "Street Nine",
    "nemcee.com": "Nemcee",
    "maxwangerblog.com": "Max Wanger",
    "baphotos.com": "BA Photos",
    "francescapia.com": "Galerie Francesca Pia",
    "shopnouveau.com": "Shop Nouveau",
    "squarespace-cdn.com": "Squarespace",
    "fashionsnap-assets.com": "Fashionsnap",
    "venkateshrao.com": "Venkatesh Rao",
    "shopify.com": "Shopify",
    "substackcdn.com": "Substack",
    "share.google": "Google",
    "arena-images-temp.s3.amazonaws.com": "Are.na",
    "35mmdoubles.blogspot.com": "35mm Doubles",
    "adamgoldberg.tumblr.com": "Adam Goldberg",
    "anastasiavolkova.blogspot.com": "Anastasia Volkova",
    "anders-neuman.exposure.co": "Anders Neuman",
    "brunopostigo.tumblr.com": "Bruno Postigo",
    "chrisozer.tumblr.com": "Chris Ozer",
    "craicandcharm.tumblr.com": "Craic & Charm",
    "jacoblambert.blogspot.com": "Jacob Lambert",
    "jcarrasquillo.blogspot.com": "J. Carrasquillo",
    "jonyeston.tumblr.com": "Jon Yeston",
    "marvaments.tumblr.com": "Marvaments",
    "mrelllis.tumblr.com": "Mr. Ellis",
    "nicoledeeblog.tumblr.com": "Nicole Dee",
    "photobyeve.blogspot.com": "Photo by Eve",
    "rogueterritory.tumblr.com": "Rogue Territory",
    "shawnbrackbill.tumblr.com": "Shawn Brackbill",
    "velvetnoise.substack.com": "Velvet Noise",
    "wmbrown.substack.com": "WM Brown",
    "yingangphoto.tumblr.com": "Ying Ang Photo",
    "fuckyeahvansshoes.tumblr.com": "Fuck Yeah Vans Shoes",
    "lingeredupon.blogspot.com": "Lingered Upon",
    "withlittlesound.blogspot.com": "With Little Sound",
    "m1kikey.deviantart.com": "m1kikey",
    "mail.google.com": "Gmail",
}


def clean_subdomain_name(name: str) -> str:
    name = re.sub(r"[-_]", " ", name)
    return name.title()


def extract_author_from_url(url: str | None) -> str | None:
    """Extract clean author, creator, or publisher brand name from a URL domain."""
    if not url:
        return None
    unquoted = urllib.parse.unquote(url)
    m = re.search(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s\"\'<>]*", unquoted[8:])
    if m and not ("s3.amazonaws.com" in m.group(0) or "cloudfront.net" in m.group(0)):
        target_url = m.group(0)
    else:
        target_url = url

    try:
        parsed = urllib.parse.urlparse(target_url)
        host = parsed.netloc.lower()
    except Exception:
        return None

    if not host:
        return None

    host = host.split(":")[0]

    # Explicit lookup
    if host in BRAND_MAP:
        return BRAND_MAP[host]

    # Subdomain platforms
    if host.endswith(".tumblr.com"):
        sub = host[:-11]
        if sub and not sub.isdigit() and sub not in ("media", "24.media", "28.media", "68.media"):
            return clean_subdomain_name(sub)
        return "Tumblr"

    if host.endswith(".blogspot.com"):
        sub = host[:-13]
        if sub and not sub.startswith("1.bp") and not sub.startswith("2.bp"):
            return clean_subdomain_name(sub)
        return "Blogspot"

    if host.endswith(".wordpress.com"):
        sub = host[:-14]
        if not sub.endswith(".files"):
            return clean_subdomain_name(sub)
        return "WordPress"

    if host.endswith(".substack.com"):
        sub = host[:-13]
        if sub and sub not in ("open", "cdn", "api"):
            return clean_subdomain_name(sub)
        return "Substack"

    if host.endswith(".deviantart.com"):
        sub = host[:-15]
        return clean_subdomain_name(sub)

    if host.endswith(".exposure.co"):
        sub = host[:-12]
        return clean_subdomain_name(sub)

    # Clean prefixes
    clean_host = re.sub(r"^(www|m|amp|cdn|images|media|static|assets|shop|blog|en|us|at|i|s-media-cache-ak0)\.", "", host)
    if clean_host in BRAND_MAP:
        return BRAND_MAP[clean_host]

    parts = clean_host.split(".")
    if len(parts) >= 2:
        root_2 = ".".join(parts[-2:])
        if root_2 in BRAND_MAP:
            return BRAND_MAP[root_2]
        if len(parts) >= 3:
            root_3 = ".".join(parts[-3:])
            if root_3 in BRAND_MAP:
                return BRAND_MAP[root_3]

    main_name = parts[0] if parts else clean_host
    return re.sub(r"[-_]", " ", main_name).title()


def extract_author_and_source_title(raw_title):
    """Extract clean title, author, and source publication from an Are.na block title."""
    if not raw_title:
        return None, None
    clean = raw_title.replace("**", "").strip()
    clean = re.sub(r'\(via\s+[^\)]+\)', '', clean, flags=re.IGNORECASE).strip()
    author = None
    # Check for " - Author"
    m = re.search(r'[\-–—]\s*([A-Z][a-zA-Z\s\.\'\-]+)$', clean)
    if m:
        author = m.group(1).strip()
        clean = clean[:m.start()].strip().strip('\'\"')
    else:
        # Check for " by Author"
        m2 = re.search(r'\bby\s+([A-Z][a-zA-Z\s\.\'\-]+)$', clean)
        if m2:
            author = m2.group(1).strip()
            clean = clean[:m2.start()].strip().strip('\'\"')
    return author, clean or raw_title


def cmd_import_arena(args):
    """Import blocks from an Are.na channel (remote slug/ID or JSON dump) into WideWeb atoms."""
    vault_dir = Path(args.vault).resolve()
    channel_input = args.channel.strip()

    blocks = []
    channel_title = "Are.na Import"

    # 1. Load from file if local path exists
    if Path(channel_input).exists():
        with open(channel_input, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            if isinstance(raw_data, dict) and "result" in raw_data and isinstance(raw_data["result"], dict) and "data" in raw_data["result"]:
                blocks = raw_data["result"]["data"]
                channel_title = Path(channel_input).stem.replace("arena_", "").replace("_", " ").replace("-", " ").title()
            elif isinstance(raw_data, dict) and "data" in raw_data:
                blocks = raw_data["data"]
                channel_title = Path(channel_input).stem.replace("arena_", "").replace("_", " ").replace("-", " ").title()
            elif isinstance(raw_data, dict) and "contents" in raw_data:
                blocks = raw_data["contents"]
                channel_title = raw_data.get("title", Path(channel_input).stem)
            elif isinstance(raw_data, list):
                blocks = raw_data
                channel_title = Path(channel_input).stem.replace("arena_", "").replace("_", " ").replace("-", " ").title()
    else:
        # 2. Fetch from Are.na API or local cached dump
        headers = {"User-Agent": "WideWeb/1.0"}
        token = os.environ.get("ARENA_TOKEN") or os.environ.get("ARENA_API_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_url = f"https://api.are.na/v2/channels/{channel_input}?per={args.limit}"
        print(f"📡 Fetching Are.na channel '{channel_input}' from API...")
        try:
            session = get_http_session()
            resp = session.get(api_url, headers=headers, timeout=(3.0, 15.0))
            if resp.status_code == 200:
                ch_data = resp.json()
                channel_title = ch_data.get("title", channel_input)
                blocks = ch_data.get("contents", [])
            elif resp.status_code in (401, 403):
                print(f"ℹ️ Channel '{channel_input}' is private (HTTP {resp.status_code}).")
                # Look for cached dump in vault/import/
                slug_variants = [
                    channel_input,
                    channel_input.replace("-", "_"),
                    channel_input.split("-")[0]
                ]
                dump_file = None
                for sv in slug_variants:
                    cand = vault_dir / "import" / f"arena_{sv}.json"
                    if cand.exists():
                        dump_file = cand
                        break
                if dump_file:
                    print(f"📂 Found local authenticated dump: {dump_file}")
                    with open(dump_file, "r", encoding="utf-8") as df:
                        raw_d = json.load(df)
                        blocks = raw_d.get("result", {}).get("data", []) or raw_d.get("contents", [])
                        channel_title = channel_input.replace("-", " ").title()
                else:
                    print("❌ Please provide ARENA_TOKEN or a JSON dump file.")
                    return
            else:
                print(f"❌ Error fetching Are.na channel: HTTP {resp.status_code}")
                return
        except Exception as e:
            print(f"❌ Network error: {e}")
            return

    if not blocks:
        print(f"ℹ️ No blocks found for channel '{channel_input}'.")
        return

    print(f"\n🧱 Ingesting {len(blocks)} blocks from Are.na channel '{channel_title}'...")
    conn = get_db(vault_dir)
    imported = 0
    skipped = 0

    clean_tag = re.sub(r'[^a-zA-Z0-9]+', '-', channel_title.lower()).strip('-') or "arena"
    base_tags = [clean_tag]
    if args.tag:
        base_tags.extend(normalize_tags(args.tag))

    # Determine default visibility for channel
    channel_vis = getattr(args, "visibility", None)
    if not channel_vis:
        ch_low = (args.collection or channel_title).lower()
        if "work (private)" in ch_low or "private" in ch_low:
            channel_vis = "private"
        elif any(k in ch_low for k in ("wishlist", "sarah", "mom & dad", "mom-dad")):
            channel_vis = "shared"
        else:
            channel_vis = "public"

    for b in blocks:
        b_class = b.get("class") or b.get("type") or "Block"
        b_title = b.get("title") or b.get("name")
        b_desc = sanitize_text(b.get("description") or b.get("description_html"))
        b_id = str(b["id"]) if b.get("id") else None
        b_url = f"https://www.are.na/block/{b_id}" if b_id else None

        # Determine block visibility (inherit channel visibility or override if block is private)
        block_vis = channel_vis
        if b.get("visibility") == "private" and channel_vis == "public":
            block_vis = "shared"

        source_url = None
        if b.get("source") and isinstance(b["source"], dict):
            source_url = b["source"].get("url")
            if source_url and "rdl.ink" in source_url and "/render/" in source_url:
                source_url = unquote(source_url.split("/render/", 1)[1])

        # Extract content if Text block
        content = None
        if b_class == "Text":
            content_raw = b.get("content") or b.get("content_html") or ""
            if isinstance(content_raw, dict):
                content = content_raw.get("plain") or content_raw.get("markdown") or content_raw.get("html") or str(content_raw)
            else:
                content = content_raw
            if content:
                content = content.strip()

        # Deduplication check
        if b_class == "Text" and content:
            # Deduplicate by matching text_content so multiple distinct quotes from the same source article are preserved
            existing = conn.execute("SELECT id, atom_title FROM atoms WHERE text_content = ?", (content,)).fetchone()
            if existing:
                print(f"   ℹ️ Already exists in vault: {existing['atom_title']} ({existing['id']})")
                skipped += 1
                continue
        elif source_url:
            existing = conn.execute("SELECT id, atom_title FROM atoms WHERE destination_url = ? OR source_url = ?", (source_url, source_url)).fetchone()
            if existing:
                print(f"   ℹ️ Already exists in vault: {existing['atom_title']} ({existing['id']})")
                skipped += 1
                continue

        # 1. Video / Embed
        if b_class in ("Media", "Embed") or (source_url and extract_video_info(source_url)):
            v_url = source_url or b.get("embed", {}).get("url")
            if v_url:
                v_args = types.SimpleNamespace(
                    url=v_url,
                    title=b_title,
                    notes=b_desc,
                    tags=",".join(base_tags),
                    collection=args.collection or channel_title,
                    visibility=block_vis,
                    favorite=False,
                    vault=str(vault_dir),
                    image_url=None,
                    quote=None,
                    target_kind=None,
                    capture_method="arena",
                    capture_id=b_id,
                    capture_url=b_url
                )
                try:
                    cmd_video(v_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Video import failed for {v_url}: {e}")

        # 2. Image
        elif b_class == "Image":
            img_url = None
            if b.get("image"):
                img_url = (b["image"].get("src") or 
                           b["image"].get("original", {}).get("url") or 
                           b["image"].get("display", {}).get("url"))
            if not img_url and source_url and any(source_url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
                img_url = source_url

            if img_url:
                img_title = b_title or (b.get("image", {}).get("filename") if b.get("image") else f"{channel_title} Image")
                effective_img_source = source_url
                if not effective_img_source and b_desc:
                    url_match = re.search(r"https?://[^\s<>\"'()\[\]]+", b_desc)
                    if url_match:
                        effective_img_source = html.unescape(re.sub(r"[\.,;:!?]+$", "", url_match.group(0)))

                img_args = types.SimpleNamespace(
                    src=img_url,
                    title=img_title,
                    source=effective_img_source,
                    author=b.get("user", {}).get("name") if b.get("user") else None,
                    notes=b_desc,
                    alt=b.get("image", {}).get("alt_text") if b.get("image") else None,
                    tags=",".join(base_tags),
                    collection=args.collection or channel_title,
                    visibility=block_vis,
                    favorite=False,
                    vault=str(vault_dir),
                    arena_block_id=b.get("id"),
                    capture_method="arena",
                    capture_id=b_id,
                    capture_url=b_url
                )
                try:
                    cmd_image(img_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Image import failed for {img_url}: {e}")

        # 3. Link (Article or Bookmark)
        elif b_class in ("Link", "Block"):
            if source_url:
                l_args = types.SimpleNamespace(
                    url=source_url,
                    title=b_title,
                    notes=b_desc,
                    tags=",".join(base_tags),
                    collection=args.collection or channel_title,
                    visibility=block_vis,
                    image_url=b.get("image", {}).get("original", {}).get("url") if b.get("image") else None,
                    quote=None,
                    favorite=False,
                    vault=str(vault_dir),
                    target_kind=None,
                    capture_method="arena",
                    capture_id=b_id,
                    capture_url=b_url
                )
                try:
                    cmd_save_link(l_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Link import failed for {source_url}: {e}")

        # 4. Text (Quote or Note)
        elif b_class == "Text":
            if content:
                extracted_author, clean_title = extract_author_and_source_title(b_title)
                # If channel or collection is a quote/highlight collection, or source_url exists, or quotes detected, treat as Quote
                is_quote = (
                    source_url is not None
                    or any(k in (args.collection or channel_title).lower() for k in ("quote", "highlight", "reading"))
                    or ('"' in content or '“' in content)
                    or extracted_author is not None
                    or "(via " in (b_title or "").lower()
                )
                final_title = clean_title or b_title
                if is_quote:
                    q_args = types.SimpleNamespace(
                        quote=content,
                        title=final_title,
                        source=source_url,
                        source_title=final_title,
                        author=extracted_author,
                        notes=b_desc,
                        tags=",".join(base_tags),
                        collection=args.collection or channel_title,
                        visibility=block_vis,
                        favorite=False,
                        vault=str(vault_dir),
                        capture_method="arena",
                        capture_id=b_id,
                        capture_url=b_url
                    )
                    cmd_quote(q_args)
                else:
                    n_args = types.SimpleNamespace(
                        text=content,
                        title=final_title,
                        tags=",".join(base_tags),
                        collection=args.collection or channel_title,
                        visibility=block_vis,
                        favorite=False,
                        vault=str(vault_dir),
                        capture_method="arena",
                        capture_id=b_id,
                        capture_url=b_url
                    )
                    cmd_note(n_args)
                imported += 1

        # 5. Connected Channel
        elif b_class == "Channel":
            ch_url = f"https://www.are.na/channel/{b.get('slug') or b.get('id')}"
            l_args = types.SimpleNamespace(
                url=ch_url,
                title=f"Channel: {b_title}",
                notes=b_desc or f"Connected Are.na channel ({b.get('length', 0)} blocks)",
                tags=",".join(base_tags + ["arena-channel"]),
                collection=args.collection or channel_title,
                visibility=block_vis,
                image_url=None,
                quote=None,
                favorite=False,
                vault=str(vault_dir),
                target_kind="bookmark"
            )
            try:
                cmd_save_link(l_args)
                imported += 1
            except Exception as e:
                print(f"   ⚠️ Channel block import failed: {e}")

        # 6. Attachment (PDFs, documents, media files)
        elif b_class == "Attachment" or b.get("attachment"):
            att_url = (b.get("attachment", {}) or {}).get("url") or source_url
            if att_url:
                att_title = b_title or (b.get("attachment", {}) or {}).get("filename") or "Attachment"
                img_thumb = b.get("image", {}).get("src") if b.get("image") else None
                l_args = types.SimpleNamespace(
                    url=att_url,
                    title=att_title,
                    notes=b_desc,
                    tags=",".join(base_tags + ["attachment"]),
                    collection=args.collection or channel_title,
                    visibility=block_vis,
                    image_url=img_thumb,
                    quote=None,
                    favorite=False,
                    vault=str(vault_dir),
                    target_kind="bookmark"
                )
                try:
                    cmd_save_link(l_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Attachment block import failed: {e}")

    # Regenerate viewer
    import viewer
    viewer.generate_viewer(vault_dir)
    print(f"\n✨ Completed Are.na import for '{channel_title}'!")
    print(f"   📥 Imported: {imported} new atoms")
    print(f"   ℹ️ Skipped:  {skipped} duplicates\n")


def cmd_reindex(args):
    """Rebuild SQLite vault.db from all atom.json files on disk (Disaster Recovery)."""
    vault_dir = Path(args.vault).resolve()
    atoms_root = vault_dir / "atoms"
    db_path = vault_dir / "vault.db"

    if not atoms_root.exists():
        sys.exit(f"No atoms folder found at {atoms_root}")

    if db_path.exists():
        os.remove(db_path)
        print(f"🗑️ Removed existing database {db_path}")

    conn = get_db(vault_dir)
    count = 0

    print(f"🔍 Scanning {atoms_root} for atom.json sidecars...")
    for root, dirs, files in os.walk(atoms_root):
        if "atom.json" in files:
            atom_file = Path(root) / "atom.json"
            try:
                with open(atom_file, "r", encoding="utf-8") as f:
                    doc = json.load(f)

                atom_id = doc["id"]
                now_iso = doc.get("created_at", datetime.now(timezone.utc).isoformat())
                prov = doc.get("source") or doc.get("provenance") or {}
                cur = doc.get("curation", {})
                content = doc.get("content") or doc.get("payload") or {}
                
                # Backwards compatibility: Read kind from root envelope (v2+), curation (v2-beta), or display_hint (v1)
                kind = doc.get("kind") or cur.get("kind")
                if not kind or kind == "link":
                    if (Path(root) / "article.md").exists() or (content.get("article") and content["article"].get("file")):
                        kind = "article"
                    elif cur.get("display_hint") == "text":
                        kind = "quote"
                    elif cur.get("display_hint") == "image":
                        kind = "image"
                    else:
                        kind = "bookmark"

                # Cover image mapping (handles v1 asset, v2 payload, v3 content)
                cover = content.get("cover_image") or content.get("asset") or {}
                if isinstance(cover, str):
                    cover = {"relative_path": cover}
                cover_rel_path = cover.get("relative_path")

                text = content.get("text") or {}
                if isinstance(text, str):
                    text_content = text
                    text = {"excerpt": text}
                else:
                    text_content = text.get("excerpt")

                article = content.get("article") or {}
                if not isinstance(article, dict):
                    article = {}
                if not text_content:
                    atom_dir = Path(root)
                    if (atom_dir / "transcript.txt").exists():
                        try:
                            with open(atom_dir / "transcript.txt", "r", encoding="utf-8") as tf:
                                text_content = tf.read()
                        except Exception:
                            pass
                    elif (atom_dir / "quote.md").exists():
                        try:
                            with open(atom_dir / "quote.md", "r", encoding="utf-8") as qf:
                                text_content = qf.read()
                        except Exception:
                            pass
                    elif (atom_dir / "quote.txt").exists():
                        try:
                            with open(atom_dir / "quote.txt", "r", encoding="utf-8") as qf:
                                text_content = qf.read()
                        except Exception:
                            pass
                    elif (atom_dir / "note.md").exists():
                        try:
                            with open(atom_dir / "note.md", "r", encoding="utf-8") as nf:
                                text_content = nf.read()
                        except Exception:
                            pass
                    elif (atom_dir / "note.txt").exists():
                        try:
                            with open(atom_dir / "note.txt", "r", encoding="utf-8") as nf:
                                text_content = nf.read()
                        except Exception:
                            pass

                meta_bag = doc.get("metadata_json") or {}
                if "word_count" not in meta_bag:
                    meta_bag["word_count"] = text.get("word_count") or article.get("word_count")
                if "aspect_ratio" not in meta_bag and cover.get("aspect_ratio"):
                    meta_bag["aspect_ratio"] = cover.get("aspect_ratio")
                if "blurhash" not in meta_bag and cover.get("blurhash"):
                    meta_bag["blurhash"] = cover.get("blurhash")

                atom_notes = cur.get("notes")
                if isinstance(atom_notes, dict):
                    atom_notes = atom_notes.get("plain") or atom_notes.get("markdown") or str(atom_notes)

                source_url_val = prov.get("source_url") or content.get("destination_url")

                with conn:
                    conn.execute("""
                        INSERT INTO atoms (
                            id, kind, created_at, updated_at, atom_title, notes, tags,
                            collections, visibility, favorite, destination_url, cover_file_path,
                            text_content, source_url, author, metadata, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        atom_id, kind, now_iso, doc.get("updated_at", now_iso),
                        cur.get("atom_title", "Untitled"), atom_notes,
                        json.dumps(normalize_tags(cur.get("tags", []))), json.dumps(cur.get("collections", [])),
                        cur.get("visibility", "public"),
                        1 if cur.get("favorite") else 0, source_url_val,
                        cover_rel_path, text_content, source_url_val,
                        prov.get("author"), json.dumps(meta_bag), json.dumps(doc)
                    ))
                count += 1
            except Exception as e:
                print(f"⚠️ Error parsing {atom_file}: {e}")

    print(f"🎉 Disaster Recovery complete! Successfully indexed {count} atoms into vault.db.")


def cmd_backfill_transcripts(args):
    """Enrich video atoms by fetching YouTube captions/transcripts with polite throttling."""
    vault_dir = Path(args.vault).resolve()
    conn = get_db(vault_dir)

    limit = args.limit
    delay = args.delay
    cookies_path = getattr(args, "cookies", None)

    rows = conn.execute("""
        SELECT id, atom_title, destination_url, source_url, cover_file_path, metadata, raw_json
        FROM atoms
        WHERE kind = 'video'
          AND (text_content IS NULL OR text_content = '')
        ORDER BY created_at ASC
    """).fetchall()

    candidates = []
    for r in rows:
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        if not meta.get("transcript_checked"):
            candidates.append(r)

    print(f"🔍 Found {len(candidates)} video atoms pending transcript extraction (processing up to {limit}).")
    if not candidates:
        print("✅ No video atoms require transcript backfill!")
        return

    to_process = candidates[:limit]
    success_count = 0
    unavailable_count = 0
    blocked = False

    for idx, r in enumerate(to_process, 1):
        atom_id = r["id"]
        title = r["atom_title"] or "Untitled Video"
        url = r["destination_url"] or r["source_url"] or ""

        # Extract YouTube video id
        video_id = None
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0].split("#")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0].split("#")[0]
        elif "/shorts/" in url:
            video_id = url.split("/shorts/")[1].split("?")[0].split("#")[0]

        if not video_id:
            print(f"[{idx}/{len(to_process)}] ⚠️ Could not parse video ID from {url} ({atom_id})")
            continue

        print(f"[{idx}/{len(to_process)}] 🎙️ Querying captions for '{title[:45]}' ({video_id})...")

        transcript_data = None
        try:
            transcript_data = fetch_youtube_transcript(video_id, cookies=cookies_path)
        except Exception as e:
            err_name = type(e).__name__
            if "IpBlocked" in err_name or "Blocked" in str(e):
                print(f"\n🛑 YouTube is currently rate-limiting this IP address (IpBlocked).")
                print("   Stopping run to let cooldown clear. Run again later or supply --cookies.")
                blocked = True
                break
            else:
                print(f"   ℹ️ Captions unavailable: {e}")

        # Locate atom directory
        rel_cover = r["cover_file_path"]
        atom_dir = None
        if rel_cover:
            candidate_dir = (vault_dir / rel_cover).parent
            if candidate_dir.exists():
                atom_dir = candidate_dir
        if not atom_dir:
            for p in (vault_dir / "atoms").glob(f"**/{atom_id}"):
                if p.is_dir():
                    atom_dir = p
                    break

        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}

        if transcript_data and atom_dir:
            txt_path = atom_dir / "transcript.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript_data["plain_text"])

            json_path = atom_dir / "transcript.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(transcript_data["snippets"], f, indent=2)

            rel_txt = str(txt_path.relative_to(vault_dir))
            rel_json = str(json_path.relative_to(vault_dir))

            meta["has_transcript"] = True
            meta["transcript_snippets"] = len(transcript_data["snippets"])
            meta["transcript_language"] = transcript_data["language"]
            meta["transcript_checked"] = True

            content_key = "content" if "content" in raw else ("payload" if "payload" in raw else "content")
            if content_key not in raw:
                raw[content_key] = {}
            if "video" not in raw[content_key] or not isinstance(raw[content_key]["video"], dict):
                raw[content_key]["video"] = {}
            raw[content_key]["video"]["has_transcript"] = True
            raw[content_key]["video"]["transcript_file"] = rel_txt
            raw[content_key]["video"]["transcript_json"] = rel_json
            raw[content_key]["video"]["transcript_language"] = transcript_data["language"]
            raw[content_key]["video"]["transcript_is_generated"] = transcript_data["is_generated"]

            with open(atom_dir / "atom.json", "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2, ensure_ascii=False)

            conn.execute("""
                UPDATE atoms
                SET text_content = ?, metadata = ?, raw_json = ?, updated_at = ?
                WHERE id = ?
            """, (
                transcript_data["speech_text"],
                json.dumps(meta),
                json.dumps(raw),
                datetime.now(timezone.utc).isoformat(),
                atom_id
            ))
            conn.commit()
            print(f"   ✅ Saved {len(transcript_data['snippets'])} captions ({transcript_data['language']})")
            success_count += 1
        elif not blocked:
            meta["transcript_checked"] = True
            meta["has_transcript"] = False
            conn.execute("UPDATE atoms SET metadata = ? WHERE id = ?", (json.dumps(meta), atom_id))
            conn.commit()
            if atom_dir and (atom_dir / "atom.json").exists():
                with open(atom_dir / "atom.json", "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            unavailable_count += 1
            print(f"   ℹ️ No captions found on YouTube for this video.")

        if idx < len(to_process) and not blocked:
            sleep_time = delay + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

    print(f"\n📊 Summary:")
    print(f"   ✅ Transcripts added: {success_count}")
    print(f"   ℹ️ No captions available: {unavailable_count}")
    if blocked:
        print(f"   ⏸️ Run paused early due to IP rate-limiting.")


def cmd_view(args):
    """Generate and open the local HTML masonry viewer with in-browser capture."""
    import webbrowser
    from viewer import generate_viewer, run_viewer_server
    
    vault_dir = Path(args.vault).resolve()
    if args.server:
        port = args.port or 8080
        run_viewer_server(vault_dir, port=port, open_browser=not args.no_open)
    else:
        index_html = generate_viewer(vault_dir)
        print(f"\n✨ WideWeb HTML viewer generated at: {index_html}")
        file_url = f"file://{index_html.resolve()}"
        if not args.no_open:
            print(f"🌐 Opening in default browser: {file_url}")
            webbrowser.open(file_url)
        else:
            print(f"💡 Open in your browser: open '{index_html}'")
        print("\n💡 Tip: Run `python3 curate.py view --server` to enable live 1-click capture and bookmarklet integration directly from the browser!")


def get_public_atoms(vault_dir: Path):
    """Retrieve all atoms marked with public visibility from SQLite."""
    conn = sqlite3.connect(vault_dir / "vault.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, notes, tags, collections,
               destination_url, cover_file_path, text_content, source_url,
               author, metadata, raw_json
        FROM atoms
        WHERE visibility = 'public'
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return rows


def prune_empty_schema_fields(d):
    """Recursively prune None values from dictionary to keep public manifest lightweight."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            sub = prune_empty_schema_fields(v)
            if sub:
                out[k] = sub
        else:
            out[k] = v
    return out


def generate_curation_export(vault_dir: Path, rows, bucket: str = DEFAULT_GCS_BUCKET):
    """Generate vault/export/curation_public.json for the public digital garden."""
    export_dir = vault_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    base_url = f"https://storage.googleapis.com/{bucket}"

    public_items = []
    raw_recent = []
    for r in rows:
        tags = json.loads(r["tags"]) if r["tags"] else []
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        cover_rel = r["cover_file_path"]

        # GCS public URL if cover exists
        cover_url = None
        if cover_rel:
            cover_url = f"{base_url}/{cover_rel}"

        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        prov = raw.get("source") or raw.get("provenance") or {}
        cur = raw.get("curation", {})
        content_layer = raw.get("content") or raw.get("payload") or {}
        collections = json.loads(r["collections"]) if r["collections"] else cur.get("collections", [])
        cover_content = content_layer.get("cover_image", {}) or {}
        alt_text = cover_content.get("alt_text")

        # Clean deprecated fields from raw content and source/provenance
        if raw and isinstance(raw, dict):
            for layer_key in ("content", "payload"):
                if layer_key in raw and isinstance(raw[layer_key], dict):
                    raw[layer_key].pop("destination_url", None)
                    if "cover_image" in raw[layer_key] and isinstance(raw[layer_key]["cover_image"], dict):
                        raw[layer_key]["cover_image"].pop("original_src_url", None)
            for src_key in ("source", "provenance"):
                if src_key in raw and isinstance(raw[src_key], dict):
                    raw[src_key].pop("author_url", None)
                    raw[src_key].pop("canonical_url", None)

        source_url_val = r["source_url"] or r["destination_url"]

        created_at = r["created_at"] or ""
        folder_rel = f"atoms/{created_at[:4]}/{created_at[5:7]}/{r['id']}"

        # atom.json public URL for on-demand lazy loading in schema explorer
        atom_url = None
        atom_file = vault_dir / folder_rel / "atom.json"
        if atom_file.exists():
            v_tag = int(atom_file.stat().st_mtime)
            atom_url = f"{base_url}/{folder_rel}/atom.json?v={v_tag}"

        # For articles, do not inline the full text in the public manifest (prevents 120MB+ bloat).
        # Supply article_url so client can lazy-load article.md on demand when opening reader modal.
        article_url = None
        content_val = None
        if r["kind"] == "article":
            if (vault_dir / folder_rel / "article.md").exists():
                article_url = f"{base_url}/{folder_rel}/article.md"
            content_val = None
        else:
            # For quotes, notes, bookmarks, videos, content is lightweight (< 1MB total across entire vault)
            content_val = r["text_content"]

        clean_raw = prune_empty_schema_fields(raw) if raw else {}

        # Streamlined item for high-performance public manifest
        item = {
            "id": r["id"],
            "kind": r["kind"],
            "title": r["atom_title"] or "Untitled",
            "notes": r["notes"],
            "tags": tags,
            "collections": collections,
            "alt_text": alt_text,
            "date": r["created_at"][:10] if r["created_at"] else "",
            "author": r["author"],
            "site_name": prov.get("site_name"),
            "source_url": source_url_val,
            "cover_url": cover_url,
            "article_url": article_url,
            "atom_url": atom_url,
            "excerpt": (r["text_content"][:300] + "...") if r["text_content"] and len(r["text_content"]) > 300 else r["text_content"],
            "content": content_val,
            "metadata": meta
        }
        public_items.append(item)
        if len(raw_recent) < 72:
            raw_recent.append(clean_raw)

    out_file = export_dir / "curation_public.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(public_items, f, separators=(",", ":"), ensure_ascii=False)

    # For curation_recent.json, embed raw on the top 72 items for instant zero-fetch inspection
    recent_items = []
    for it, raw_obj in zip(public_items[:72], raw_recent):
        cp = dict(it)
        cp["raw"] = raw_obj
        recent_items.append(cp)

    recent_file = export_dir / "curation_recent.json"
    with open(recent_file, "w", encoding="utf-8") as f:
        json.dump(recent_items, f, separators=(",", ":"), ensure_ascii=False)

    print(f"📄 Generated {out_file} ({len(public_items)} public atoms)")
    print(f"📄 Generated {recent_file} ({len(recent_items)} recent atoms with embedded raw schema)")
    return out_file


def get_gcs_access_token():
    """Retrieve and refresh OAuth access token from gcloud credentials.db."""
    cred_db = Path.home() / ".config" / "gcloud" / "credentials.db"
    if not cred_db.exists():
        return None
    try:
        conn = sqlite3.connect(cred_db)
        c = conn.cursor()
        row = c.execute("SELECT account_id, value FROM credentials").fetchone()
        conn.close()
        if not row:
            return None
        account_id, val = row
        cred = json.loads(val)
        token_resp = requests.post(
            cred["token_uri"],
            data={
                "client_id": cred["client_id"],
                "client_secret": cred["client_secret"],
                "refresh_token": cred["refresh_token"],
                "grant_type": "refresh_token"
            },
            timeout=10
        )
        if token_resp.status_code == 200:
            token_data = token_resp.json()
            access_token = token_data["access_token"]
            # Also update access_tokens.db so gcloud CLI remains authenticated
            try:
                atk_db = Path.home() / ".config" / "gcloud" / "access_tokens.db"
                if atk_db.exists():
                    atk_conn = sqlite3.connect(atk_db)
                    expiry = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 3600))
                    with atk_conn:
                        atk_conn.execute("REPLACE INTO access_tokens (account_id, access_token, token_expiry) VALUES (?, ?, ?)",
                                         (account_id, access_token, expiry))
                    atk_conn.close()
            except Exception:
                pass
            return access_token
    except Exception as e:
        print(f"⚠️ Could not refresh token from credentials.db: {e}")
    return None


def _upload_file_to_gcs(file_path: Path, bucket: str, token: str, gcloud_bin: str, max_age: int = 120):
    name = file_path.name
    base_url = f"https://storage.googleapis.com/{bucket}"
    with open(file_path, "rb") as f:
        raw_bytes = f.read()
    gz_bytes = gzip.compress(raw_bytes, compresslevel=9)

    if token:
        boundary = "===============7330832792=="
        meta = {
            "name": name,
            "contentType": "application/json",
            "contentEncoding": "gzip",
            "cacheControl": f"public, max-age={max_age}"
        }
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + json.dumps(meta) + "\r\n"
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
        ).encode("utf-8") + gz_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}"
        }
        upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=multipart"
        resp = requests.post(upload_url, headers=headers, data=body, timeout=120)
        if resp.status_code == 200:
            print(f"✅ Published {name} to {base_url}/{name} (gzipped: {len(gz_bytes)/1024:.1f} KB, raw: {len(raw_bytes)/1024/1024:.2f} MB)")
            return True
        else:
            print(f"⚠️ REST upload of {name} returned {resp.status_code}, falling back to gcloud CLI...")

    # Fallback to gcloud CLI
    cp_cmd = [
        gcloud_bin, "--quiet", "storage", "cp",
        str(file_path),
        f"gs://{bucket}/{name}",
        f"--cache-control=public, max-age={max_age}"
    ]
    res_json = subprocess.run(cp_cmd, capture_output=True, text=True)
    if res_json.returncode == 0:
        print(f"✅ Published {name} to {base_url}/{name}")
        return True
    else:
        print(f"⚠️ {name} upload warning: {res_json.stderr}")
        return False


def upload_manifest_to_gcs(vault_dir: Path, bucket: str = DEFAULT_GCS_BUCKET):
    """Upload curation_recent.json and curation_public.json directly to GCS with gzip compression."""
    export_dir = vault_dir / "export"
    files_to_upload = [
        export_dir / "curation_recent.json",
        export_dir / "curation_public.json"
    ]

    token = get_gcs_access_token()
    gcloud_bin = "/Users/drew/Documents/google-cloud-sdk/bin/gcloud"
    if not Path(gcloud_bin).exists():
        gcloud_bin = "gcloud"

    all_ok = True
    for f in files_to_upload:
        if f.exists():
            print(f"🚀 Uploading {f.name} to GCS root with gzip compression...")
            ok = _upload_file_to_gcs(f, bucket, token, gcloud_bin)
            if not ok:
                all_ok = False
        else:
            print(f"⚠️ {f} does not exist, skipping.")

    return all_ok


def sync_assets_to_gcs(vault_dir: Path, bucket: str = DEFAULT_GCS_BUCKET):
    """Sync public image assets and article markdown to GCS atoms directory."""
    print(f"🚀 Syncing public assets to gs://{bucket}/atoms/ ...")
    gcloud_bin = "/Users/drew/Documents/google-cloud-sdk/bin/gcloud"
    if not Path(gcloud_bin).exists():
        gcloud_bin = "gcloud"

    # Exclude non-article texts/notes, transcripts, and private atoms (syncs images, article.md, and atom.json)
    exclude_regex = ".*(transcript\\.json|\\.txt|note\\.md|quote\\.md|\\.DS_Store|atm_20261104210906_a7152e|atm_20261104210908_e2ecc1|atm_20261104210910_f82447|atm_20261104210911_9c6058|atm_20261104210912_f6a4da).*"

    cmd = [
        gcloud_bin, "storage", "rsync",
        str(vault_dir / "atoms"),
        f"gs://{bucket}/atoms",
        "--recursive",
        f"--exclude={exclude_regex}"
    ]

    print("Running asset sync...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("✅ Asset sync complete!")
        return True
    else:
        print(f"⚠️ Asset sync warning: {res.stderr}")
        return False


def cmd_sync(args):
    """Sync public atoms manifest and assets to Google Cloud Storage."""
    vault_dir = Path(args.vault).resolve()
    bucket = getattr(args, "bucket", None) or DEFAULT_GCS_BUCKET
    manifest_only = getattr(args, "manifest_only", False)

    rows = get_public_atoms(vault_dir)
    print(f"🔍 Found {len(rows)} public atoms in vault.")
    generate_curation_export(vault_dir, rows, bucket=bucket)
    upload_manifest_to_gcs(vault_dir, bucket=bucket)
    if not manifest_only:
        sync_assets_to_gcs(vault_dir, bucket=bucket)


def cmd_pull(args):
    """Pull newly captured items from Instapaper (unread) and Are.na (all channels)."""
    import inbound_sync
    vault_dir = Path(args.vault).resolve()
    service = getattr(args, "service", "all")
    limit = getattr(args, "limit", 25)
    visibility = getattr(args, "visibility", "public")
    inbound_sync.pull_all(vault_dir, service=service, limit=limit, visibility=visibility)


def cmd_enrich(args):
    """Enrich image atoms with AI-generated alt text and sync to Are.na."""
    import ai_enrich
    vault_dir = Path(args.vault).resolve()
    ai_enrich.batch_enrich_vault(
        vault_dir=vault_dir,
        limit=getattr(args, "limit", None),
        force=getattr(args, "force", False),
        push_to_arena=not getattr(args, "no_arena", False)
    )


def cmd_mcp(args):
    """Run the WideWeb Model Context Protocol (MCP) server for Claude Desktop / AI assistants."""
    import wideweb_mcp
    wideweb_mcp.main()


def main():
    parser = argparse.ArgumentParser(description="WideWeb Curate CLI - Local-first web curation framework")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Path to WideWeb vault directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_capture_args(p):
        p.add_argument("--capture-method", help="Ingest tool/pipeline name (e.g. arena, instapaper, cli, mcp)")
        p.add_argument("--capture-id", help="Upstream item ID on source platform")
        p.add_argument("--capture-url", help="Upstream item URL on source platform")

    # 1. Article command
    p_art = subparsers.add_parser("article", help="Save a longform article/essay with full offline text and reader view")
    p_art.add_argument("url", help="Webpage URL of the article")
    p_art.add_argument("--title", help="Custom atom title")
    p_art.add_argument("--notes", help="Personal curation notes")
    p_art.add_argument("--tags", help="Comma-separated tags")
    p_art.add_argument("--collection", help="Collection name")
    p_art.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_art.add_argument("--image-url", help="Override primary image URL")
    p_art.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_art.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_art)
    p_art.set_defaults(func=cmd_article)

    # 2. Bookmark command
    p_bm = subparsers.add_parser("bookmark", help="Save a lightweight web pointer (OG metadata only, no article body)")
    p_bm.add_argument("url", help="Webpage URL to bookmark")
    p_bm.add_argument("--title", help="Custom atom title")
    p_bm.add_argument("--notes", help="Personal curation notes")
    p_bm.add_argument("--tags", help="Comma-separated tags")
    p_bm.add_argument("--collection", help="Collection name")
    p_bm.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_bm.add_argument("--image-url", help="Override primary image URL")
    p_bm.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_bm.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_bm)
    p_bm.set_defaults(func=cmd_bookmark)

    # 3. Save / Link command (smart auto-detect)
    p_link = subparsers.add_parser("link", help="Save a link into the vault (auto-detects article vs bookmark)")
    p_link.add_argument("url", help="The webpage URL to capture")
    p_link.add_argument("--title", help="Custom atom title (defaults to page title)")
    p_link.add_argument("--notes", help="Personal curation notes")
    p_link.add_argument("--tags", help="Comma-separated tags (e.g. design,systems)")
    p_link.add_argument("--collection", help="Collection name")
    p_link.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_link.add_argument("--image-url", help="Override primary image URL")
    p_link.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_link.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_link)
    p_link.set_defaults(func=cmd_save_link)

    p_save = subparsers.add_parser("save", help="Alias for 'link' (smart auto-detect)")
    p_save.add_argument("url", help="The webpage URL to capture")
    p_save.add_argument("--title", help="Custom atom title (defaults to page title)")
    p_save.add_argument("--notes", help="Personal curation notes")
    p_save.add_argument("--tags", help="Comma-separated tags")
    p_save.add_argument("--collection", help="Collection name")
    p_save.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_save.add_argument("--image-url", help="Override primary image URL")
    p_save.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_save.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_save)
    p_save.set_defaults(func=cmd_save_link)

    # 2. Quote command
    p_quote = subparsers.add_parser("quote", help="Save an attributed text quote / excerpt")
    p_quote.add_argument("quote", help="The text body of the quote")
    p_quote.add_argument("--title", help="Custom title for the quote")
    p_quote.add_argument("--source", help="Source URL where the quote was found")
    p_quote.add_argument("--source-title", help="Original article title")
    p_quote.add_argument("--author", help="Author of the quote")
    p_quote.add_argument("--notes", help="Personal marginalia / notes")
    p_quote.add_argument("--tags", help="Comma-separated tags")
    p_quote.add_argument("--collection", help="Collection name")
    p_quote.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_quote.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_quote)
    p_quote.set_defaults(func=cmd_quote)

    # 3. Note command
    p_note = subparsers.add_parser("note", help="Save a personal thought or memo")
    p_note.add_argument("text", help="The body of the note/thought")
    p_note.add_argument("--title", help="Custom title for the note")
    p_note.add_argument("--tags", help="Comma-separated tags")
    p_note.add_argument("--collection", help="Collection name")
    p_note.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_note.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_note)
    p_note.set_defaults(func=cmd_note)

    # 4. Image command
    p_image = subparsers.add_parser("image", help="Save an image (file path or URL)")
    p_image.add_argument("src", help="Path to local image or direct image URL")
    p_image.add_argument("--title", help="Custom image title")
    p_image.add_argument("--source", help="Original webpage URL or credit link")
    p_image.add_argument("--author", help="Photographer, illustrator, or creator")
    p_image.add_argument("--alt", help="Accessibility alt text / visual description")
    p_image.add_argument("--notes", help="Personal notes on the image")
    p_image.add_argument("--tags", help="Comma-separated tags")
    p_image.add_argument("--collection", help="Collection name")
    p_image.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_image.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_image)
    p_image.set_defaults(func=cmd_image)

    # 5. Video command
    p_video = subparsers.add_parser("video", help="Save a video stream (YouTube, Vimeo, etc.)")
    p_video.add_argument("url", help="URL of the video to capture")
    p_video.add_argument("--title", help="Custom video title")
    p_video.add_argument("--notes", help="Personal curation notes")
    p_video.add_argument("--tags", help="Comma-separated tags")
    p_video.add_argument("--collection", help="Collection name")
    p_video.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier (public, shared, private)")
    p_video.add_argument("--favorite", action="store_true", help="Mark as favorite")
    add_capture_args(p_video)
    p_video.set_defaults(func=cmd_video)

    # 6. List command
    p_list = subparsers.add_parser("list", help="List atoms in the vault")
    p_list.add_argument("--kind", choices=["article", "bookmark", "video", "quote", "note", "image", "file"], help="Filter by kind")
    p_list.add_argument("--tag", help="Filter by tag")
    p_list.add_argument("--collection", help="Filter by collection")
    p_list.add_argument("--visibility", choices=["public", "shared", "private"], help="Filter by visibility tier")
    p_list.add_argument("--limit", type=int, default=20, help="Number of items to show")
    p_list.set_defaults(func=cmd_list)

    # 6. Export command
    p_export = subparsers.add_parser("export", help="Export atoms to platform formats")
    p_export.add_argument(
        "--target",
        choices=[
            "digest", "llms", "notebooklm", "llms-txt",
            "obsidian", "logseq",
            "bookmarks-html", "bookmarks", "netscape",
            "readwise",
            "arena-csv", "csv",
            "raindrop-csv", "raindrop",
            "pinterest-csv", "pinterest",
            "rss", "feed",
            "bibtex", "bib",
            "jsonl",
            "json"
        ],
        default="digest",
        help="Export target format (digest, llms-txt, obsidian, bookmarks-html, readwise, arena-csv, raindrop-csv, pinterest-csv, rss, bibtex, jsonl, json)"
    )
    p_export.add_argument("--kind", choices=["article", "bookmark", "video", "quote", "note", "image", "file"], help="Filter by kind")
    p_export.add_argument("--tag", help="Filter by tag")
    p_export.add_argument("--visibility", choices=["public", "shared", "private"], help="Filter by visibility tier (e.g. export only public atoms)")
    p_export.add_argument("--folder", help="Default Raindrop collection / folder name (default: WideWeb/<Kind>s)")
    p_export.add_argument("--board", help="Default Pinterest board name (default: WideWeb)")
    p_export.add_argument("--out", help="Output file path (default: stdout or vault/export/vault_digest.md)")
    p_export.set_defaults(func=cmd_export)

    # 7. Reindex command
    p_reindex = subparsers.add_parser("reindex", help="Rebuild SQLite database from folder sidecars")
    p_reindex.set_defaults(func=cmd_reindex)

    # 8. View command
    p_view = subparsers.add_parser("view", help="Generate and open local HTML masonry viewer")
    p_view.add_argument("--server", action="store_true", help="Run local HTTP server instead of file://")
    p_view.add_argument("--port", type=int, default=8080, help="Port for local HTTP server (default: 8080)")
    p_view.add_argument("--no-open", action="store_true", help="Do not automatically open browser")
    p_view.set_defaults(func=cmd_view)

    # 9. MCP command
    p_mcp = subparsers.add_parser("mcp", help="Run the WideWeb Model Context Protocol (MCP) server for Claude Desktop / AI tools")
    p_mcp.set_defaults(func=cmd_mcp)

    # 10. Import Are.na command
    p_import_arena = subparsers.add_parser("import-arena", help="Import blocks from an Are.na channel into WideWeb atoms")
    p_import_arena.add_argument("channel", help="Are.na channel slug, ID, or JSON file path")
    p_import_arena.add_argument("--limit", type=int, default=100, help="Max blocks to fetch (default: 100)")
    p_import_arena.add_argument("--tag", help="Additional tag to apply to imported atoms")
    p_import_arena.add_argument("--collection", help="Collection name (defaults to channel title)")
    p_import_arena.add_argument("--visibility", choices=["public", "shared", "private"], help="Explicitly set visibility tier (public, shared, private)")
    p_import_arena.set_defaults(func=cmd_import_arena)

    # 11. Backfill Transcripts command
    p_backfill = subparsers.add_parser("backfill-transcripts", help="Throttled background drip to fetch YouTube captions/transcripts")
    p_backfill.add_argument("--limit", type=int, default=30, help="Max videos to process in this run (default: 30)")
    p_backfill.add_argument("--delay", type=float, default=3.5, help="Base delay in seconds between requests (default: 3.5)")
    p_backfill.add_argument("--cookies", help="Path to cookies.txt exported from browser")
    p_backfill.set_defaults(func=cmd_backfill_transcripts)

    # 12. Sync command (Google Cloud Storage)
    p_sync = subparsers.add_parser("sync", help="Sync public atoms and image assets to Google Cloud Storage (GCS)")
    p_sync.add_argument("--bucket", default=DEFAULT_GCS_BUCKET, help=f"GCS bucket name (default: {DEFAULT_GCS_BUCKET})")
    p_sync.add_argument("--manifest-only", action="store_true", help="Only upload curation_public.json manifest without rsyncing images")
    p_sync.set_defaults(func=cmd_sync)

    # 13. Pull command (Instapaper & Are.na inbound sync)
    p_pull = subparsers.add_parser("pull", help="Pull new captures from Instapaper (unread) and Are.na (user feed)")
    p_pull.add_argument("--service", choices=["all", "instapaper", "arena"], default="all", help="Service to pull from (default: all)")
    p_pull.add_argument("--limit", type=int, default=25, help="Max items to fetch per service (default: 25)")
    p_pull.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Default visibility tier (default: public)")
    p_pull.set_defaults(func=cmd_pull)

    # 14. Enrich command (AI Vision Alt Text & Are.na Sync)
    p_enrich = subparsers.add_parser("enrich", help="Generate AI alt text for images using Gemini Flash and sync to Are.na")
    p_enrich.add_argument("--limit", type=int, default=None, help="Max images to enrich in this run")
    p_enrich.add_argument("--force", action="store_true", help="Re-generate alt text even if already present")
    p_enrich.add_argument("--no-arena", action="store_true", help="Skip syncing alt text to Are.na")
    p_enrich.set_defaults(func=cmd_enrich)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
