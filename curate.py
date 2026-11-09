#!/usr/bin/env python3
"""
Webtack Curate CLI (v3)
A local-first, durable web curation and bookmarking framework using the Content Sidecar pattern.
https://webtack.net
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
import shutil
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
def _load_dotenv():
    """Load key-value pairs from .env into os.environ if not already set."""
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

_load_dotenv()

DEFAULT_VAULT = Path(os.environ.get("WEBTACK_VAULT", os.environ.get("WIDEWEB_VAULT", os.environ.get("OPENCURATE_VAULT", Path(__file__).resolve().parent / "vault"))))
DEFAULT_GCS_BUCKET = os.environ.get("WEBTACK_GCS_BUCKET", os.environ.get("WIDEWEB_GCS_BUCKET", ""))
SCHEMA_URL = "https://raw.githubusercontent.com/dn0c/webtack/main/schema/atom.schema.json"
SCHEMA_VERSION = 3

_HTTP_SESSION = None

def get_http_session() -> requests.Session:
    """Get or initialize a resilient HTTP session with connection pooling and exponential backoff retries."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
        _HTTP_SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Webtack/1.0",
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


def parse_transcript_input(transcript_input: str | Path) -> dict | None:
    """Parse user-supplied transcript from a file path (.txt, .vtt, .srt, .json) or raw text.
    
    Supports:
    - WebVTT (.vtt) cues and timestamps
    - SubRip (.srt) cues and timestamps
    - JSON snippet array ([{"start": ..., "text": ...}])
    - YouTube web player "Show transcript" copy-paste (alternating timestamps and lines)
    - Bracketed timestamps [01:23] Dialogue line
    - Plain raw text
    """
    if not transcript_input:
        return None

    raw_text = ""
    file_path = None
    try:
        p = Path(transcript_input)
        if p.is_file():
            file_path = p
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
    except Exception:
        pass

    if not raw_text:
        raw_text = str(transcript_input).strip()

    if not raw_text:
        return None

    ext = file_path.suffix.lower() if file_path else ""

    # 1. JSON format (e.g. [{'start': 0.0, 'duration': 2.5, 'text': '...'}] or Supadata JSON)
    if ext == ".json" or (raw_text.startswith("[") and raw_text.endswith("]")):
        try:
            data = json.loads(raw_text)
            if isinstance(data, list) and data:
                snippets = []
                plain_lines = []
                for item in data:
                    start = float(item.get("start", item.get("offset", 0.0)))
                    dur = float(item.get("duration", 0.0))
                    text = str(item.get("text", "")).strip()
                    sec = int(start)
                    m, s_rem = divmod(sec, 60)
                    h, m = divmod(m, 60)
                    timestamp_str = f"{h}:{m:02d}:{s_rem:02d}" if h > 0 else f"{m}:{s_rem:02d}"
                    snippets.append({
                        "start": round(start, 2),
                        "duration": round(dur, 2),
                        "timestamp": timestamp_str,
                        "text": text
                    })
                    plain_lines.append(f"[{timestamp_str}] {text}")
                return {
                    "plain_text": "\n".join(plain_lines),
                    "speech_text": " ".join(s["text"] for s in snippets),
                    "snippets": snippets,
                    "language": "en",
                    "is_generated": False
                }
        except Exception:
            pass

    # 2. WebVTT (.vtt)
    if ext == ".vtt" or "WEBVTT" in raw_text[:50]:
        snippets = []
        plain_lines = []
        vtt_regex = re.compile(r"((?:(\d{1,2}):)?(\d{2}):(\d{2})[\.,](\d{3}))\s*-->\s*((?:(\d{1,2}):)?(\d{2}):(\d{2})[\.,](\d{3}))")
        lines = raw_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            match = vtt_regex.search(line)
            if match:
                h1 = int(match.group(2) or 0)
                m1 = int(match.group(3))
                s1 = int(match.group(4))
                ms1 = int(match.group(5))
                start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0

                h2 = int(match.group(7) or 0)
                m2 = int(match.group(8))
                s2 = int(match.group(9))
                ms2 = int(match.group(10))
                end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

                timestamp_str = f"{h1}:{m1:02d}:{s1:02d}" if h1 > 0 else f"{m1}:{s1:02d}"

                cue_text = []
                i += 1
                while i < len(lines) and lines[i].strip() and not vtt_regex.search(lines[i]):
                    cue_text.append(lines[i].strip())
                    i += 1
                clean_text = " ".join(cue_text)
                clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()
                if clean_text:
                    snippets.append({
                        "start": round(start_sec, 2),
                        "duration": round(max(0.0, end_sec - start_sec), 2),
                        "timestamp": timestamp_str,
                        "text": clean_text
                    })
                    plain_lines.append(f"[{timestamp_str}] {clean_text}")
                continue
            i += 1
        if snippets:
            return {
                "plain_text": "\n".join(plain_lines),
                "speech_text": " ".join(s["text"] for s in snippets),
                "snippets": snippets,
                "language": "en",
                "is_generated": False
            }

    # 3. SubRip (.srt)
    if ext == ".srt" or re.search(r"\d+\r?\n\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", raw_text):
        snippets = []
        plain_lines = []
        srt_regex = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
        lines = raw_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            match = srt_regex.search(line)
            if match:
                h1, m1, s1, ms1 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
                h2, m2, s2, ms2 = int(match.group(5)), int(match.group(6)), int(match.group(7)), int(match.group(8))
                end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
                timestamp_str = f"{h1}:{m1:02d}:{s1:02d}" if h1 > 0 else f"{m1}:{s1:02d}"

                cue_text = []
                i += 1
                while i < len(lines) and lines[i].strip() and not srt_regex.search(lines[i]):
                    if not (len(cue_text) == 0 and lines[i].strip().isdigit()):
                        cue_text.append(lines[i].strip())
                    i += 1
                clean_text = " ".join(cue_text)
                clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()
                if clean_text:
                    snippets.append({
                        "start": round(start_sec, 2),
                        "duration": round(max(0.0, end_sec - start_sec), 2),
                        "timestamp": timestamp_str,
                        "text": clean_text
                    })
                    plain_lines.append(f"[{timestamp_str}] {clean_text}")
                continue
            i += 1
        if snippets:
            return {
                "plain_text": "\n".join(plain_lines),
                "speech_text": " ".join(s["text"] for s in snippets),
                "snippets": snippets,
                "language": "en",
                "is_generated": False
            }

    # 4. Text or YouTube Web player "Show transcript" copy-paste
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    ts_bracket_re = re.compile(r"^\[?((?:(\d{1,2}):)?(\d{1,2}):(\d{2}))\]?\s*(.*)$")
    bare_ts = re.compile(r"^((?:(\d{1,2}):)?(\d{1,2}):(\d{2}))$")
    snippets = []
    plain_lines = []

    # Check for alternating timestamp / text pattern
    is_alternating = False
    if len(lines) >= 2:
        sample_even = [bool(bare_ts.match(lines[k])) for k in range(0, min(10, len(lines)), 2)]
        sample_odd = [not bool(bare_ts.match(lines[k])) for k in range(1, min(10, len(lines)), 2)]
        if all(sample_even) and all(sample_odd) and len(sample_even) >= 2:
            is_alternating = True

    if is_alternating:
        for idx in range(0, len(lines) - 1, 2):
            ts_str = lines[idx]
            text = lines[idx + 1]
            match = ts_bracket_re.match(ts_str)
            if match:
                h = int(match.group(2) or 0)
                m = int(match.group(3))
                s = int(match.group(4))
                start_sec = h * 3600 + m * 60 + s
                snippets.append({
                    "start": float(start_sec),
                    "duration": 0.0,
                    "timestamp": ts_str,
                    "text": text
                })
                plain_lines.append(f"[{ts_str}] {text}")
    else:
        for line in lines:
            match = ts_bracket_re.match(line)
            if match and match.group(5):
                ts_str = match.group(1)
                h = int(match.group(2) or 0)
                m = int(match.group(3))
                s = int(match.group(4))
                start_sec = h * 3600 + m * 60 + s
                text = match.group(5).strip()
                snippets.append({
                    "start": float(start_sec),
                    "duration": 0.0,
                    "timestamp": ts_str,
                    "text": text
                })
                plain_lines.append(f"[{ts_str}] {text}")
            else:
                plain_lines.append(line)

    if snippets:
        return {
            "plain_text": "\n".join(plain_lines),
            "speech_text": " ".join(s["text"] for s in snippets),
            "snippets": snippets,
            "language": "en",
            "is_generated": False
        }

    # Fallback: un-timestamped plain text
    return {
        "plain_text": raw_text,
        "speech_text": " ".join(raw_text.split()),
        "snippets": [{"start": 0.0, "duration": 0.0, "timestamp": "0:00", "text": raw_text}],
        "language": "en",
        "is_generated": False
    }


def fetch_youtube_transcript(video_id: str, cookies: str | None = None, api_key: str | None = None, force_api: bool = False) -> dict | None:
    """Fetch transcript via optional external API (e.g. Supadata) if configured, or None."""
    supadata_key = api_key or os.environ.get("SUPADATA_API_KEY")
    if not supadata_key:
        return None

    try:
        import requests
        url = f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}&text=false"
        headers = {"x-api-key": supadata_key}
        resp = requests.get(url, headers=headers, timeout=25.0)
        if resp.status_code == 200:
            data = resp.json()
            raw_content = data.get("content")
            if isinstance(raw_content, list) and raw_content:
                snippets = []
                plain_lines = []
                for s in raw_content:
                    offset_ms = float(s.get("offset", 0))
                    dur_ms = float(s.get("duration", 0))
                    start_sec = offset_ms / 1000.0
                    dur_sec = dur_ms / 1000.0
                    sec = int(start_sec)
                    m, s_rem = divmod(sec, 60)
                    h, m = divmod(m, 60)
                    timestamp_str = f"{h}:{m:02d}:{s_rem:02d}" if h > 0 else f"{m}:{s_rem:02d}"
                    clean_text = str(s.get("text", "")).replace("\n", " ").strip()
                    snippets.append({
                        "start": round(start_sec, 2),
                        "duration": round(dur_sec, 2),
                        "timestamp": timestamp_str,
                        "text": clean_text
                    })
                    plain_lines.append(f"[{timestamp_str}] {clean_text}")

                return {
                    "plain_text": "\n".join(plain_lines),
                    "speech_text": " ".join([s["text"] for s in snippets]),
                    "snippets": snippets,
                    "language": data.get("lang", "en"),
                    "is_generated": True
                }
            elif isinstance(raw_content, str) and raw_content.strip():
                clean_text = raw_content.strip()
                return {
                    "plain_text": clean_text,
                    "speech_text": clean_text,
                    "snippets": [{"start": 0.0, "duration": 0.0, "timestamp": "0:00", "text": clean_text}],
                    "language": data.get("lang", "en"),
                    "is_generated": True
                }
    except Exception as se:
        print(f"⚠️ Transcript API fetch error: {se}")

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
    notes = getattr(args, "description", None) or getattr(args, "notes", None)
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
    transcript_arg = getattr(args, "transcript", None)
    if transcript_arg:
        transcript_data = parse_transcript_input(transcript_arg)
        if transcript_data:
            print(f"✅ Loaded user-supplied transcript: {len(transcript_data['snippets'])} segments")
        else:
            print("⚠️ Could not parse provided transcript.")
    elif video_info.get("provider") == "YouTube" and video_info.get("video_id"):
        # Check if an external API key (e.g. Supadata) is configured
        transcript_data = fetch_youtube_transcript(video_info["video_id"])
        if transcript_data:
            print(f"✅ Found transcript: {len(transcript_data['snippets'])} snippets ({transcript_data['language']})")
        else:
            print("ℹ️ No transcript provided. Pass --transcript <file|text> or use 'attach-transcript' to add one.")

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
            "author": getattr(args, "author", None) or video_info["author"],
            "published_at": None,
            "favicon": video_info["favicon"],
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "description": notes,
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

    if getattr(args, "no_enrich", False):
        print(f"📌 Fast save without enrichment: {args.url}")
        parsed_netloc = urlparse(args.url).netloc
        scraped = {
            "source_title": getattr(args, "title", None) or parsed_netloc,
            "description": None,
            "author": getattr(args, "author", None),
            "site_name": parsed_netloc,
            "canonical_url": args.url,
            "image_url": getattr(args, "image_url", None),
            "favicon": None,
            "published_at": None,
            "article_markdown": None,
            "article_word_count": 0
        }
    else:
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

    # If client passed in pre-extracted article markdown (e.g. from bookmarklet):
    client_markdown = getattr(args, "article_markdown", None)
    if client_markdown and len(client_markdown.strip()) > 50:
        if not scraped.get("article_markdown") or len(client_markdown) > len(scraped["article_markdown"]):
            scraped["article_markdown"] = client_markdown.strip()
            scraped["article_word_count"] = len(client_markdown.strip().split())
            print(f"📖 Using in-browser extracted article text ({scraped['article_word_count']} words)")

    # Determine kind
    if target_kind:
        kind = target_kind
    elif scraped.get("article_markdown") and scraped.get("article_word_count", 0) >= 100:
        kind = "article"
    else:
        kind = "bookmark"

    # Check if an existing atom already matches this URL with empty article text (Backfill support)
    target_url = scraped.get("canonical_url") or args.url
    conn = get_db(vault_dir)
    existing_row = None
    with conn:
        existing_row = conn.execute("""
            SELECT id, created_at, cover_file_path, raw_json
            FROM atoms
            WHERE (source_url = ? OR destination_url = ?)
              AND kind = 'article'
            ORDER BY created_at DESC LIMIT 1
        """, (target_url, target_url)).fetchone()

    if existing_row:
        atom_id = existing_row["id"]
        now_iso = existing_row["created_at"]
        print(f"🔄 Updating existing article atom {atom_id} with full article text...")
        rel_folder = Path("atoms") / now_iso[:4] / now_iso[5:7] / atom_id
    else:
        atom_id = generate_atom_id()
        now_iso = datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc)
        rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id

    atom_title = args.title or scraped["source_title"]
    notes = getattr(args, "description", None) or getattr(args, "notes", None) or scraped.get("description")
    if isinstance(notes, dict):
        notes = notes.get("plain") or notes.get("markdown") or str(notes)
    tags = normalize_tags(args.tags)
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []
    visibility = getattr(args, "visibility", None) or "public"
    if visibility not in ("public", "shared", "private"):
        visibility = "public"

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

        # AI Article Summarization (Level 3 Multi-Provider, skipped if --no-enrich)
        if not getattr(args, "no_enrich", False):
            try:
                from scripts import enrich
                ai_sum, prov = enrich.generate_ai_article_summary(
                    scraped["article_markdown"],
                    title=atom_title
                )
                if ai_sum and prov:
                    labeled_sum = enrich.format_ai_summary(ai_sum, prov)
                    user_notes = getattr(args, "description", None) or getattr(args, "notes", None)
                    if user_notes:
                        notes = f"{user_notes}\n\n{labeled_sum}"
                    else:
                        notes = labeled_sum
                    print(f"   ✨ [{prov.upper()}] Generated article summary: {labeled_sum[:70]}...")
            except Exception as e:
                print(f"   ⚠️ AI summary generation failed ({e}), retaining default notes.")

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
            "site_name": getattr(args, "site_name", None) or scraped["site_name"],
            "author": getattr(args, "author", None) or scraped["author"],
            "published_at": getattr(args, "published_at", None) or scraped.get("published_at"),
            "favicon": scraped.get("favicon"),
            "capture_method": cap_prov["capture_method"],
            "capture_id": cap_prov["capture_id"],
            "capture_url": cap_prov["capture_url"]
        },
        "curation": {
            "atom_title": atom_title,
            "description": notes,
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

    # Insert or update SQLite Clean Hybrid table
    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            INSERT INTO atoms (
                id, kind, created_at, updated_at, atom_title, notes, tags, collections,
                visibility, favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                atom_title = excluded.atom_title,
                notes = excluded.notes,
                tags = excluded.tags,
                text_content = excluded.text_content,
                author = excluded.author,
                metadata = excluded.metadata,
                raw_json = excluded.raw_json
        """, (
            atom_id, kind, now_iso, datetime.now(timezone.utc).isoformat(), atom_title, notes, json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, args.url, cover_rel_path,
            args.quote.strip() if getattr(args, "quote", None) else (scraped.get("article_markdown") if kind == "article" else None), args.url, getattr(args, "author", None) or scraped["author"],
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
            "description": getattr(args, "description", None) or getattr(args, "notes", None),
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
            atom_id, "quote", now_iso, now_iso, atom_title, getattr(args, "description", None) or getattr(args, "notes", None), json.dumps(tags),
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
            "description": getattr(args, "description", None) or getattr(args, "notes", None),
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
    notes = getattr(args, "description", None) or getattr(args, "notes", None)
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
    if not getattr(args, "no_enrich", False):
        try:
            from scripts import enrich
            if not alt_text or enrich.is_placeholder_alt(alt_text):
                resolved_alt, method = enrich.resolve_image_alt_text(
                    image_path=abs_cover_path,
                    source_url=source_candidate,
                    upstream_img_url=src if is_url else None,
                    fallback_title=atom_title
                )
                if resolved_alt:
                    alt_text = resolved_alt
                    print(f"   ✨ [{method.upper()}] Alt text: {alt_text}")
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
            "description": getattr(args, "description", None) or getattr(args, "notes", None),
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
            atom_id, "image", now_iso, now_iso, atom_title, getattr(args, "description", None) or getattr(args, "notes", None), json.dumps(tags),
            json.dumps(collections), visibility, 1 if args.favorite else 0, args.source or source_candidate, cover_rel_path,
            None, source_candidate, author, json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    print(f"\n🖼️ Image atom saved successfully!")
    print(f"   ID:      {atom_id}")
    print(f"   Kind:    image")
    print(f"   Ratio:   {downloaded['aspect_ratio']} | Blurhash: {downloaded['blurhash']}")
    print(f"   Folder:  {abs_folder}")
    return atom_doc


def delete_atom(vault_dir: Path, atom_id: str) -> bool:
    """Delete an atom from the vault by removing its sidecar directory and database entry."""
    vault_dir = Path(vault_dir).resolve()
    atom_id = atom_id.strip()

    # 1. Remove from SQLite database
    conn = get_db(vault_dir)
    with conn:
        conn.execute("DELETE FROM atoms WHERE id = ?", (atom_id,))

    # 2. Find and delete sidecar directory: vault/atoms/YYYY/MM/<atom_id>
    atoms_root = vault_dir / "atoms"
    deleted = False
    if atoms_root.exists():
        for root, dirs, files in os.walk(atoms_root):
            if atom_id in dirs:
                target_dir = Path(root) / atom_id
                shutil.rmtree(target_dir)
                deleted = True
                print(f"🗑️ Deleted atom folder {target_dir}")
                break

    return deleted


def cmd_delete(args):
    """Delete an atom by ID."""
    vault_dir = Path(args.vault).resolve()
    success = delete_atom(vault_dir, args.atom_id)
    if success:
        print(f"✨ Successfully deleted atom {args.atom_id}")
    else:
        print(f"ℹ️ Atom {args.atom_id} removed from database (no on-disk folder found).")


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

    print(f"\n📚 Webtack Vault ({len(rows)} items shown):")
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
        default_board = getattr(args, "board", None) or "Webtack"

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
        default_folder = getattr(args, "folder", None) or "Webtack"

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
            f"# Webtack Vault Knowledge Digest",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Total Curated Atoms: {len(rows)}",
            f"\n> This document is a unified compilation of curated articles, video transcripts, notes, quotes, and bookmarks from the Webtack vault. Optimized for analysis, indexing, and synthesis in NotebookLM, Claude Projects, and local LLMs.\n",
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
            f"# Webtack Vault Index",
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

            escaped_title = title.replace('"', '\\"')
            fm = [
                "---",
                f"id: \"{aid}\"",
                f"title: \"{escaped_title}\"",
                f"kind: {kind}",
                f"date: \"{r['created_at'][:10]}\"",
                f"created_at: \"{r['created_at']}\""
            ]
            url = r["destination_url"] or r["source_url"]
            if url:
                fm.append(f"url: \"{url}\"")
            if r["author"]:
                escaped_author = r["author"].replace('"', '\\"')
                fm.append(f"author: \"{escaped_author}\"")
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
            "<TITLE>Webtack Bookmarks</TITLE>",
            "<H1>Webtack Bookmarks</H1>",
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
            '    <title>Webtack Curation Vault</title>',
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
            author = (r["author"] or "Webtack Vault").replace("{", "\\{").replace("}", "\\}")
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
    """Import blocks from an Are.na channel into Webtack atoms (delegates to integrations/arena/import_channel.py)."""
    from integrations.arena.import_channel import import_channel
    import_channel(
        channel_input=args.channel,
        vault_dir=Path(args.vault),
        limit=getattr(args, "limit", 100),
        tag=getattr(args, "tag", None),
        collection=getattr(args, "collection", None),
        visibility=getattr(args, "visibility", None)
    )


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

                atom_notes = cur.get("description") or cur.get("notes")
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


def cmd_validate(args):
    """Validate atom.json sidecars against formal atom.schema.json specification and verify sidecar integrity."""
    vault_dir = Path(args.vault).resolve()
    atoms_root = vault_dir / "atoms"
    schema_path = Path(__file__).resolve().parent / "schema" / "atom.schema.json"

    if not schema_path.exists():
        sys.exit(f"❌ Schema definition not found at {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    try:
        import jsonschema
        has_jsonschema = True
    except ImportError:
        has_jsonschema = False

    target_atom = getattr(args, "atom", None)
    atom_files = []
    if target_atom:
        for root, dirs, files in os.walk(atoms_root):
            if "atom.json" in files and Path(root).name == target_atom:
                atom_files.append(Path(root) / "atom.json")
                break
        if not atom_files:
            sys.exit(f"❌ Atom '{target_atom}' not found in {atoms_root}")
    else:
        for root, dirs, files in os.walk(atoms_root):
            if "atom.json" in files:
                atom_files.append(Path(root) / "atom.json")

    print(f"🔍 Validating {len(atom_files)} atoms against {schema_path.name} (jsonschema engine: {'active' if has_jsonschema else 'built-in fallback'})...")
    errors = 0
    warnings = 0

    for af in atom_files:
        atom_dir = af.parent
        try:
            with open(af, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            print(f"❌ [{atom_dir.name}] Invalid JSON: {e}")
            errors += 1
            continue

        # 1. JSON Schema validation
        if has_jsonschema:
            try:
                jsonschema.validate(instance=doc, schema=schema)
            except jsonschema.ValidationError as ve:
                err_path = "/".join(str(p) for p in ve.path) or "root"
                print(f"❌ [{atom_dir.name}] Schema error at '{err_path}': {ve.message}")
                errors += 1
                continue
        else:
            for req in ("id", "kind", "created_at", "curation", "source", "content"):
                if req not in doc:
                    print(f"❌ [{atom_dir.name}] Missing required field: '{req}'")
                    errors += 1
                    break

        # 2. Sidecar integrity checks
        def _check_sidecar(rel_p: str) -> bool:
            return (atom_dir / rel_p).exists() or (vault_dir / rel_p).exists()

        content = doc.get("content", {})
        if isinstance(content, dict):
            cover = content.get("cover_image")
            if isinstance(cover, dict) and cover.get("relative_path"):
                if not _check_sidecar(cover["relative_path"]):
                    print(f"⚠️  [{atom_dir.name}] Missing cover image sidecar: {cover['relative_path']}")
                    warnings += 1

            article = content.get("article")
            if isinstance(article, dict) and article.get("relative_path"):
                if not _check_sidecar(article["relative_path"]):
                    print(f"⚠️  [{atom_dir.name}] Missing article markdown sidecar: {article['relative_path']}")
                    warnings += 1

            text = content.get("text")
            if isinstance(text, dict) and text.get("relative_path"):
                if not _check_sidecar(text["relative_path"]):
                    print(f"⚠️  [{atom_dir.name}] Missing text markdown sidecar: {text['relative_path']}")
                    warnings += 1

            video = content.get("video")
            if isinstance(video, dict) and video.get("transcript_file"):
                if not _check_sidecar(video["transcript_file"]):
                    print(f"⚠️  [{atom_dir.name}] Missing transcript sidecar: {video['transcript_file']}")
                    warnings += 1

    print("\n" + "─" * 60)
    if errors == 0 and warnings == 0:
        print(f"🎉 Perfect! All {len(atom_files)} atoms passed validation with zero errors or warnings.")
    elif errors == 0:
        print(f"✅ Schema valid: All {len(atom_files)} atoms conform to schema ({warnings} sidecar file warnings).")
    else:
        print(f"❌ Validation failed: {errors} schema errors, {warnings} warnings across {len(atom_files)} atoms.")
        sys.exit(1)


def cmd_attach_transcript(args):
    """Attach a user-supplied transcript (.txt, .vtt, .srt, .json) or text to a video atom."""
    vault_dir = Path(args.vault).resolve()
    conn = get_db(vault_dir)
    target = args.atom_id_or_url.strip()

    row = conn.execute("""
        SELECT id, atom_title, cover_file_path, metadata, raw_json
        FROM atoms
        WHERE id = ? OR source_url = ? OR destination_url = ?
    """, (target, target, target)).fetchone()

    if not row:
        row = conn.execute("""
            SELECT id, atom_title, cover_file_path, metadata, raw_json
            FROM atoms
            WHERE id LIKE ? OR source_url LIKE ? OR destination_url LIKE ?
        """, (f"{target}%", f"%{target}%", f"%{target}%")).fetchone()

    if not row:
        print(f"❌ Could not find atom matching '{target}' in vault.")
        sys.exit(1)

    atom_id = row["id"]
    title = row["atom_title"] or "Untitled"

    transcript_data = parse_transcript_input(args.transcript)
    if not transcript_data:
        print(f"❌ Failed to parse transcript from '{args.transcript}'.")
        sys.exit(1)

    # Locate atom directory
    rel_cover = row["cover_file_path"]
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

    if not atom_dir:
        print(f"❌ Atom folder on disk not found for {atom_id}.")
        sys.exit(1)

    # Write transcript sidecars
    txt_path = atom_dir / "transcript.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(transcript_data["plain_text"])

    json_path = atom_dir / "transcript.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data["snippets"], f, indent=2)

    rel_txt = str(txt_path.relative_to(vault_dir))
    rel_json = str(json_path.relative_to(vault_dir))

    # Update atom.json
    raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
    content_key = "content" if "content" in raw else ("payload" if "payload" in raw else "content")
    if content_key not in raw:
        raw[content_key] = {}
    if "video" not in raw[content_key] or not isinstance(raw[content_key]["video"], dict):
        raw[content_key]["video"] = {}
    raw[content_key]["video"]["has_transcript"] = True
    raw[content_key]["video"]["transcript_file"] = rel_txt
    raw[content_key]["video"]["transcript_json"] = rel_json
    raw[content_key]["video"]["transcript_language"] = transcript_data.get("language", "en")
    raw[content_key]["video"]["transcript_is_generated"] = transcript_data.get("is_generated", False)

    atom_json_path = atom_dir / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)

    # Update SQLite database
    meta = json.loads(row["metadata"]) if row["metadata"] else {}
    meta["has_transcript"] = True
    meta["transcript_snippets"] = len(transcript_data["snippets"])
    meta["transcript_language"] = transcript_data.get("language", "en")
    meta["transcript_checked"] = True

    conn.execute("""
        UPDATE atoms
        SET metadata = ?, text_content = ?, raw_json = ?, updated_at = ?
        WHERE id = ?
    """, (
        json.dumps(meta),
        transcript_data["plain_text"],
        json.dumps(raw),
        datetime.now(timezone.utc).isoformat(),
        atom_id
    ))
    conn.commit()

    print(f"🎉 Successfully attached transcript to [{atom_id}] '{title}' ({len(transcript_data['snippets'])} segments)!")


def cmd_backfill_transcripts(args):
    """Enrich video atoms with transcripts from a local folder or optional API."""
    vault_dir = Path(args.vault).resolve()
    conn = get_db(vault_dir)

    limit = args.limit
    delay = args.delay
    input_dir = getattr(args, "dir", None)
    api_key = getattr(args, "api_key", None) or os.environ.get("SUPADATA_API_KEY")

    transcripts_dir = Path(input_dir).resolve() if input_dir else None
    if transcripts_dir and not transcripts_dir.is_dir():
        print(f"❌ Transcripts directory '{input_dir}' not found.")
        sys.exit(1)

    if not transcripts_dir and not api_key:
        print("ℹ️ No transcript source provided.")
        print("   Use --dir <folder> to bulk-attach local transcript files (.txt, .vtt, .srt, .json),")
        print("   or attach individual transcripts using: curate.py attach-transcript <atom_id> <file>")
        return

    if api_key:
        print("⚡ High-throughput mode active: Using configured Transcript API.")
        if delay == 3.5:
            delay = 0.3

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

    to_process = candidates[:limit] if (limit and limit > 0) else candidates
    print(f"🔍 Found {len(candidates)} video atoms pending transcript extraction (processing {len(to_process)}).")
    if not to_process:
        print("✅ No video atoms require transcript backfill!")
        return

    success_count = 0
    unavailable_count = 0

    for idx, r in enumerate(to_process, 1):
        atom_id = r["id"]
        title = r["atom_title"] or "Untitled Video"
        url = r["destination_url"] or r["source_url"] or ""
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}

        # Extract YouTube video id
        video_id = None
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0].split("#")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0].split("#")[0]
        elif "/shorts/" in url:
            video_id = url.split("/shorts/")[1].split("?")[0].split("#")[0]

        transcript_data = None

        # Check local directory first
        if transcripts_dir:
            file_candidates = []
            if video_id:
                file_candidates.extend([
                    transcripts_dir / f"{video_id}.txt",
                    transcripts_dir / f"{video_id}.vtt",
                    transcripts_dir / f"{video_id}.srt",
                    transcripts_dir / f"{video_id}.json",
                ])
            file_candidates.extend([
                transcripts_dir / f"{atom_id}.txt",
                transcripts_dir / f"{atom_id}.vtt",
                transcripts_dir / f"{atom_id}.srt",
                transcripts_dir / f"{atom_id}.json",
            ])
            for cand in file_candidates:
                if cand.exists():
                    transcript_data = parse_transcript_input(cand)
                    if transcript_data:
                        print(f"[{idx}/{len(to_process)}] 📄 Loaded local transcript: {cand.name}")
                        break

        # Fallback to API if configured
        if not transcript_data and api_key and video_id:
            print(f"[{idx}/{len(to_process)}] 🎙️ Querying captions for '{title[:45]}' ({video_id})...")
            try:
                transcript_data = fetch_youtube_transcript(video_id, api_key=api_key)
            except Exception as e:
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
            meta["transcript_language"] = transcript_data.get("language", "en")
            meta["transcript_checked"] = True

            content_key = "content" if "content" in raw else ("payload" if "payload" in raw else "content")
            if content_key not in raw:
                raw[content_key] = {}
            if "video" not in raw[content_key] or not isinstance(raw[content_key]["video"], dict):
                raw[content_key]["video"] = {}
            raw[content_key]["video"]["has_transcript"] = True
            raw[content_key]["video"]["transcript_file"] = rel_txt
            raw[content_key]["video"]["transcript_json"] = rel_json
            raw[content_key]["video"]["transcript_language"] = transcript_data.get("language", "en")
            raw[content_key]["video"]["transcript_is_generated"] = transcript_data.get("is_generated", False)

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
        else:
            meta["transcript_checked"] = True
            meta["has_transcript"] = False
            conn.execute("UPDATE atoms SET metadata = ? WHERE id = ?", (json.dumps(meta), atom_id))
            conn.commit()
            if atom_dir and (atom_dir / "atom.json").exists():
                with open(atom_dir / "atom.json", "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            unavailable_count += 1

        if idx < len(to_process) and api_key and transcript_data:
            time.sleep(delay)

    print(f"\n📊 Summary:")
    print(f"   ✅ Transcripts added: {success_count}")
    print(f"   ℹ️ Skipped / unavailable: {unavailable_count}")


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
        print(f"\n✨ Webtack HTML viewer generated at: {index_html}")
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
            if "curation" in raw and isinstance(raw["curation"], dict):
                if "notes" in raw["curation"] and "description" not in raw["curation"]:
                    raw["curation"]["description"] = raw["curation"].pop("notes")

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
            "description": r["notes"],
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


def get_gcloud_bin() -> str:
    """Find gcloud binary from environment, standard SDK locations, or system PATH."""
    custom = os.environ.get("GCLOUD_BIN")
    if custom and Path(custom).exists():
        return custom
    home = Path.home()
    for candidate in [
        home / "Documents/google-cloud-sdk/bin/gcloud",
        home / "google-cloud-sdk/bin/gcloud",
        Path("/opt/homebrew/bin/gcloud"),
        Path("/usr/local/bin/gcloud"),
    ]:
        if candidate.exists():
            return str(candidate)
    return shutil.which("gcloud") or "gcloud"


def get_non_public_atom_ids(vault_dir: Path) -> list[str]:
    """Retrieve IDs of all atoms marked with shared or private visibility."""
    db_path = vault_dir / "vault.db"
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT id FROM atoms WHERE visibility != 'public'").fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def upload_manifest_to_gcs(vault_dir: Path, bucket: str = DEFAULT_GCS_BUCKET):
    """Upload curation_recent.json and curation_public.json directly to GCS with gzip compression."""
    if not bucket:
        print("❌ Error: No GCS bucket specified. Set WEBTACK_GCS_BUCKET in .env or pass --bucket <name>.")
        return False

    export_dir = vault_dir / "export"
    files_to_upload = [
        export_dir / "curation_recent.json",
        export_dir / "curation_public.json"
    ]

    token = get_gcs_access_token()
    gcloud_bin = get_gcloud_bin()

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
    if not bucket:
        print("❌ Error: No GCS bucket specified. Set WEBTACK_GCS_BUCKET in .env or pass --bucket <name>.")
        return False

    print(f"🚀 Syncing public assets to gs://{bucket}/atoms/ ...")
    gcloud_bin = get_gcloud_bin()

    # Dynamically exclude all non-public (private/shared) atom directories, plus non-article texts and transcripts
    exclude_patterns = ["transcript\\.json", "\\.txt", "note\\.md", "quote\\.md", "\\.DS_Store"]
    non_public_ids = get_non_public_atom_ids(vault_dir)
    if non_public_ids:
        exclude_patterns.extend([re.escape(aid) for aid in non_public_ids])

    exclude_regex = f".*({'|'.join(exclude_patterns)}).*"

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


def get_or_prompt_bucket(args_bucket: str | None = None) -> str | None:
    """Resolve GCS bucket from argument, environment (.env), or prompt user interactively."""
    bucket = (args_bucket or os.environ.get("WEBTACK_GCS_BUCKET", os.environ.get("WIDEWEB_GCS_BUCKET", ""))).strip()
    if bucket:
        return bucket

    if sys.stdin.isatty():
        print("\n☁️  Google Cloud Storage Sync")
        try:
            val = input("Enter your GCS bucket name (e.g. my-garden-assets): ").strip()
            if val:
                save_env = input(f"Save '{val}' to .env as WEBTACK_GCS_BUCKET for future runs? [Y/n]: ").strip().lower()
                if save_env in ("", "y", "yes"):
                    env_path = Path(__file__).resolve().parent / ".env"
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\nWEBTACK_GCS_BUCKET={val}\n")
                    os.environ["WEBTACK_GCS_BUCKET"] = val
                    print(f"✅ Saved WEBTACK_GCS_BUCKET={val} to .env")
                return val
        except (KeyboardInterrupt, EOFError):
            print("\nSync aborted.")
            return None
    return None


def cmd_sync(args):
    """Sync public atoms manifest and assets to Google Cloud Storage."""
    vault_dir = Path(args.vault).resolve()
    bucket = get_or_prompt_bucket(getattr(args, "bucket", None))
    if not bucket:
        sys.exit("❌ Error: No GCS bucket provided. Pass --bucket <name>, set WEBTACK_GCS_BUCKET in .env, or enter it at the prompt.")

    manifest_only = getattr(args, "manifest_only", False)

    rows = get_public_atoms(vault_dir)
    print(f"🔍 Found {len(rows)} public atoms in vault.")
    generate_curation_export(vault_dir, rows, bucket=bucket)
    upload_manifest_to_gcs(vault_dir, bucket=bucket)
    if not manifest_only:
        sync_assets_to_gcs(vault_dir, bucket=bucket)


def cmd_pull(args):
    """Pull newly captured items from Instapaper (unread) and Are.na (all channels)."""
    from integrations.pull import pull_all
    vault_dir = Path(args.vault).resolve()
    service = getattr(args, "service", "all")
    limit = getattr(args, "limit", 25)
    visibility = getattr(args, "visibility", "public")
    pull_all(vault_dir, service=service, limit=limit, visibility=visibility)


def cmd_enrich(args):
    """Enrich image atoms with alt text and/or article atoms with AI summaries."""
    from scripts import enrich
    vault_dir = Path(args.vault).resolve()
    enrich.batch_enrich_vault(
        vault_dir=vault_dir,
        target=getattr(args, "target", "all"),
        limit=getattr(args, "limit", None),
        force=getattr(args, "force", False)
    )


def cmd_mcp(args):
    """Run the Webtack Model Context Protocol (MCP) server for Claude Desktop / AI assistants."""
    try:
        import webtack_mcp as wideweb_mcp
    except ImportError:
        import wideweb_mcp
    wideweb_mcp.main()


def main():
    parser = argparse.ArgumentParser(description="Webtack Curate CLI - Local-first web curation framework")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Path to Webtack vault directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_capture_args(p):
        p.add_argument("--capture-method", help="Ingest tool/pipeline name (e.g. arena, instapaper, cli, mcp)")
        p.add_argument("--capture-id", help="Upstream item ID on source platform")
        p.add_argument("--capture-url", help="Upstream item URL on source platform")
        p.add_argument("--no-enrich", action="store_true", help="Skip automatic metadata, image, and vision enrichment (pure lightweight pointer)")

    # 1. Article command
    p_art = subparsers.add_parser("article", help="Save a longform article/essay with full offline text and reader view")
    p_art.add_argument("url", help="Webpage URL of the article")
    p_art.add_argument("--title", help="Custom atom title")
    p_art.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_bm.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_link.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_save.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_quote.add_argument("--description", "--notes", dest="description", help="Curator description or marginalia")
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
    p_note.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_image.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
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
    p_video.add_argument("--description", "--notes", dest="description", help="Curator description or notes")
    p_video.add_argument("--tags", help="Comma-separated tags")
    p_video.add_argument("--collection", help="Collection name")
    p_video.add_argument("--transcript", help="Path to transcript file (.txt, .vtt, .srt, .json) or raw transcript text")
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
    p_export.add_argument("--folder", help="Default Raindrop collection / folder name (default: Webtack/<Kind>s)")
    p_export.add_argument("--board", help="Default Pinterest board name (default: Webtack)")
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
    p_mcp = subparsers.add_parser("mcp", help="Run the Webtack Model Context Protocol (MCP) server for Claude Desktop / AI tools")
    p_mcp.set_defaults(func=cmd_mcp)

    # 10. Import Are.na command
    p_import_arena = subparsers.add_parser("import-arena", help="Import blocks from an Are.na channel into Webtack atoms")
    p_import_arena.add_argument("channel", help="Are.na channel slug, ID, or JSON file path")
    p_import_arena.add_argument("--limit", type=int, default=100, help="Max blocks to fetch (default: 100)")
    p_import_arena.add_argument("--tag", help="Additional tag to apply to imported atoms")
    p_import_arena.add_argument("--collection", help="Collection name (defaults to channel title)")
    p_import_arena.add_argument("--visibility", choices=["public", "shared", "private"], help="Explicitly set visibility tier (public, shared, private)")
    p_import_arena.set_defaults(func=cmd_import_arena)

    # 11. Attach Transcript command
    p_attach = subparsers.add_parser("attach-transcript", help="Attach a user-supplied transcript (.txt, .vtt, .srt, .json) or text to a video atom")
    p_attach.add_argument("atom_id_or_url", help="Atom ID or URL of the video")
    p_attach.add_argument("transcript", help="Path to transcript file (.txt, .vtt, .srt, .json) or raw text")
    p_attach.set_defaults(func=cmd_attach_transcript)

    # 12. Backfill Transcripts command
    p_backfill = subparsers.add_parser("backfill-transcripts", help="Bulk attach transcripts to video atoms from a folder or configured API")
    p_backfill.add_argument("--dir", help="Directory of transcript files named by video ID or atom ID (.txt, .vtt, .srt, .json)")
    p_backfill.add_argument("--limit", type=int, default=30, help="Max videos to process in this run (default: 30, pass 0 for all)")
    p_backfill.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between API requests (default: 0.5)")
    p_backfill.add_argument("--api-key", help="Supadata API key for optional transcript extraction")
    p_backfill.set_defaults(func=cmd_backfill_transcripts)

    # 12. Sync command (Google Cloud Storage)
    p_sync = subparsers.add_parser("sync", help="Sync public atoms and image assets to Google Cloud Storage (GCS)")
    p_sync.add_argument("--bucket", default=None, help="GCS bucket name (overrides WEBTACK_GCS_BUCKET in .env; prompted if unset)")
    p_sync.add_argument("--manifest-only", action="store_true", help="Only upload curation_public.json manifest without rsyncing images")
    p_sync.set_defaults(func=cmd_sync)

    # 13. Pull command (Instapaper & Are.na inbound sync)
    p_pull = subparsers.add_parser("pull", help="Pull new captures from Instapaper (unread) and Are.na (user feed)")
    p_pull.add_argument("--service", choices=["all", "instapaper", "arena"], default="all", help="Service to pull from (default: all)")
    p_pull.add_argument("--limit", type=int, default=100, help="Max items to fetch per service (default: 100)")
    p_pull.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Default visibility tier (default: public)")
    p_pull.set_defaults(func=cmd_pull)

    # 14. Enrich command (Vision Alt Text & Article Summaries)
    p_enrich = subparsers.add_parser("enrich", help="Generate accessibility alt text for images and/or AI summaries for articles")
    p_enrich.add_argument("--target", choices=["all", "images", "articles"], default="all", help="What to enrich: images, articles, or all (default)")
    p_enrich.add_argument("--limit", type=int, default=None, help="Max atoms to enrich per category")
    p_enrich.add_argument("--force", action="store_true", help="Re-generate descriptions even if already present")
    p_enrich.add_argument("--no-arena", action="store_true", help="(Deprecated) Legacy flag, Are.na sync has moved to integrations/arena/")
    p_enrich.set_defaults(func=cmd_enrich)

    # 15. Validate command (Schema and Sidecar Integrity Linter)
    p_val = subparsers.add_parser("validate", help="Validate atom.json sidecars against formal schema and check sidecar integrity")
    p_val.add_argument("--atom", help="Validate a specific atom ID instead of the entire vault")
    p_val.set_defaults(func=cmd_validate)

    # 16. Delete command
    p_del = subparsers.add_parser("delete", help="Delete an atom and its sidecar directory from the vault")
    p_del.add_argument("atom_id", help="ID of the atom to delete (e.g. atm_...)")
    p_del.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
