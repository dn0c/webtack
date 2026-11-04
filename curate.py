#!/usr/bin/env python3
"""
OpenCurate CLI
A local-first, durable web curation and bookmarking framework using the Payload Sidecar pattern.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    from PIL import Image
    import trafilatura
    import blurhash
except ImportError as e:
    sys.exit(f"Missing dependency: {e}. Please run: python3 -m pip install requests beautifulsoup4 pillow trafilatura blurhash-python")

# Default vault path: ./vault or from environment variable
DEFAULT_VAULT = Path(os.environ.get("OPENCURATE_VAULT", Path(__file__).resolve().parent / "vault"))


def get_db(vault_dir: Path) -> sqlite3.Connection:
    """Initialize or connect to the SQLite index database using the Clean Hybrid pattern."""
    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_kind ON atoms(kind);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_created ON atoms(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_atoms_dest_url ON atoms(destination_url) WHERE destination_url IS NOT NULL;")
    return conn


def generate_atom_id() -> str:
    """Generate a chronological, unique atom ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_suffix = os.urandom(3).hex()
    return f"atm_{ts}_{rand_suffix}"


def extract_dominant_colors(image_path: Path, num_colors: int = 3) -> list[str]:
    """Extract top dominant hex colors from an image using Pillow."""
    try:
        with Image.open(image_path) as img:
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
    """Extract an ultra-compact blurhash string from an image."""
    try:
        with Image.open(image_path) as img:
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


def scrape_url_metadata(url: str) -> dict:
    """Scrape Open Graph, favicon, article text, and semantic metadata from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    resp = requests.get(url, headers=headers, timeout=12)
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
    article_data = extract_article_content(html_text, url)
    if not author and article_data["author"]:
        author = article_data["author"]
    if not published_at and article_data["published_at"]:
        published_at = article_data["published_at"]

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
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(image_url, headers=headers, timeout=15)
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


def cmd_save_link(args):
    """Save a URL/link into the vault, scraping metadata, cover image, and full article text."""
    vault_dir = Path(args.vault).resolve()
    print(f"🌐 Scraping {args.url}...")
    try:
        scraped = scrape_url_metadata(args.url)
    except Exception as e:
        print(f"⚠️ Scraping failed ({e}), continuing with URL fallback.")
        scraped = {
            "source_title": urlparse(args.url).netloc,
            "description": None,
            "author": None,
            "site_name": urlparse(args.url).netloc,
            "canonical_url": args.url,
            "image_url": args.image_url,
            "favicon": None,
            "published_at": None,
            "article_markdown": None,
            "article_word_count": 0
        }

    if args.image_url:
        scraped["image_url"] = args.image_url

    atom_id = generate_atom_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    atom_title = args.title or scraped["source_title"]
    notes = args.notes or scraped["description"]
    tags = [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()] if args.tags else []
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []

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
                "alt_text": scraped["source_title"],
                "original_src_url": scraped["image_url"]
            }
            print(f"🎨 Palette: {' '.join(downloaded['color_palette'])} | Ratio: {downloaded['aspect_ratio']}")
        except Exception as e:
            print(f"⚠️ Failed to download cover image: {e}")

    # 2. Save Offline Article Body (Instapaper pattern)
    article_meta = None
    if scraped.get("article_markdown") and scraped["article_word_count"] > 40:
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
    if args.quote:
        quote_filename = "quote.txt"
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

    atom_doc = {
        "$schema": "https://opencurate.org/v1/atom.schema.json",
        "id": atom_id,
        "version": 2,
        "created_at": now_iso,
        "updated_at": now_iso,
        "provenance": {
            "source_url": args.url,
            "source_title": scraped["source_title"],
            "canonical_url": scraped["canonical_url"],
            "site_name": scraped["site_name"],
            "author": scraped["author"],
            "author_url": None,
            "published_at": scraped.get("published_at"),
            "favicon": scraped.get("favicon")
        },
        "curation": {
            "kind": "link",
            "atom_title": atom_title,
            "notes": notes,
            "tags": tags,
            "collections": collections,
            "favorite": args.favorite
        },
        "payload": {
            "destination_url": args.url,
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
                favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "link", now_iso, now_iso, atom_title, notes, json.dumps(tags),
            json.dumps(collections), 1 if args.favorite else 0, args.url, cover_rel_path,
            args.quote.strip() if args.quote else None, args.url, scraped["author"],
            json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    print(f"\n✨ Link atom saved successfully!")
    print(f"   ID:     {atom_id}")
    print(f"   Kind:   link")
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

    tags = [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()] if args.tags else []
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Write quote.txt
    quote_filename = "quote.txt"
    abs_quote_path = abs_folder / quote_filename
    with open(abs_quote_path, "w", encoding="utf-8") as f:
        f.write(args.quote.strip())
    quote_rel_path = str(rel_folder / quote_filename)

    meta_bag = {
        "word_count": word_count,
        "author": args.author
    }

    atom_doc = {
        "$schema": "https://opencurate.org/v1/atom.schema.json",
        "id": atom_id,
        "version": 2,
        "created_at": now_iso,
        "updated_at": now_iso,
        "provenance": {
            "source_url": args.source,
            "source_title": args.source_title,
            "canonical_url": args.source,
            "site_name": urlparse(args.source).netloc if args.source else None,
            "author": args.author,
            "author_url": None,
            "published_at": None,
            "favicon": None
        },
        "curation": {
            "kind": "quote",
            "atom_title": atom_title,
            "notes": args.notes,
            "tags": tags,
            "collections": collections,
            "favorite": args.favorite
        },
        "payload": {
            "destination_url": args.source,
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
                favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "quote", now_iso, now_iso, atom_title, args.notes, json.dumps(tags),
            json.dumps(collections), 1 if args.favorite else 0, args.source, None,
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

    tags = [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()] if args.tags else []
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Write note.txt
    note_filename = "note.txt"
    abs_note_path = abs_folder / note_filename
    with open(abs_note_path, "w", encoding="utf-8") as f:
        f.write(args.text.strip())
    note_rel_path = str(rel_folder / note_filename)

    meta_bag = {"word_count": word_count}

    atom_doc = {
        "$schema": "https://opencurate.org/v1/atom.schema.json",
        "id": atom_id,
        "version": 2,
        "created_at": now_iso,
        "updated_at": now_iso,
        "provenance": {
            "source_url": None,
            "source_title": None,
            "canonical_url": None,
            "site_name": None,
            "author": None,
            "author_url": None,
            "published_at": None,
            "favicon": None
        },
        "curation": {
            "kind": "note",
            "atom_title": atom_title,
            "notes": None,
            "tags": tags,
            "collections": collections,
            "favorite": args.favorite
        },
        "payload": {
            "destination_url": None,
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
                favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "note", now_iso, now_iso, atom_title, None, json.dumps(tags),
            json.dumps(collections), 1 if args.favorite else 0, None, None,
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
    tags = [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()] if args.tags else []
    collections = [c.strip() for c in args.collection.split(",") if c.strip()] if args.collection else []

    meta_bag = {
        "aspect_ratio": downloaded["aspect_ratio"],
        "blurhash": downloaded["blurhash"],
        "color_palette": downloaded["color_palette"]
    }

    atom_doc = {
        "$schema": "https://opencurate.org/v1/atom.schema.json",
        "id": atom_id,
        "version": 2,
        "created_at": now_iso,
        "updated_at": now_iso,
        "provenance": {
            "source_url": args.source or (src if is_url else None),
            "source_title": None,
            "canonical_url": None,
            "site_name": None,
            "author": args.author,
            "author_url": None,
            "published_at": None,
            "favicon": None
        },
        "curation": {
            "kind": "image",
            "atom_title": atom_title,
            "notes": args.notes,
            "tags": tags,
            "collections": collections,
            "favorite": args.favorite
        },
        "payload": {
            "destination_url": args.source,
            "cover_image": {
                "file": cover_filename,
                "relative_path": cover_rel_path,
                "mime_type": downloaded["mime_type"],
                "hash": downloaded["hash"],
                "dimensions": downloaded["dimensions"],
                "aspect_ratio": downloaded["aspect_ratio"],
                "blurhash": downloaded["blurhash"],
                "color_palette": downloaded["color_palette"],
                "alt_text": args.alt or atom_title,
                "original_src_url": src if is_url else None
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
                favorite, destination_url, cover_file_path, text_content, source_url,
                author, metadata, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, "image", now_iso, now_iso, atom_title, args.notes, json.dumps(tags),
            json.dumps(collections), 1 if args.favorite else 0, args.source, cover_rel_path,
            None, args.source, args.author, json.dumps(meta_bag), json.dumps(atom_doc)
        ))

    print(f"\n🖼️ Image atom saved successfully!")
    print(f"   ID:      {atom_id}")
    print(f"   Kind:    image")
    print(f"   Ratio:   {downloaded['aspect_ratio']} | Blurhash: {downloaded['blurhash']}")
    print(f"   Folder:  {abs_folder}")


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
    if args.collection:
        query += " AND collections LIKE ?"
        params.append(f"%{args.collection}%")
        
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

    print(f"\n📚 OpenCurate Vault ({len(rows)} items shown):")
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


def cmd_export(args):
    """Export atoms to third-party formats (e.g. are.na/import/csv)."""
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
    query += " ORDER BY created_at ASC"

    rows = conn.execute(query, params).fetchall()

    if args.target == "arena-csv":
        out_stream = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
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

        if args.out:
            out_stream.close()
            print(f"✅ Exported {len(rows)} items for are.na/import/csv to: {args.out}")

    elif args.target == "json":
        atoms_list = [json.loads(r["raw_json"]) for r in rows]
        content = json.dumps(atoms_list, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Exported {len(rows)} atoms to JSON: {args.out}")
        else:
            print(content)


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
                prov = doc.get("provenance", {})
                cur = doc.get("curation", {})
                payload = doc.get("payload", {})
                
                # Backwards compatibility: Map display_hint to kind if kind is missing
                kind = cur.get("kind")
                if not kind:
                    display_hint = cur.get("display_hint", "auto")
                    if display_hint == "text":
                        kind = "quote"
                    elif display_hint == "image":
                        kind = "image"
                    else:
                        kind = "link"

                # Cover image mapping (handles both v1 asset and v2 cover_image)
                cover = payload.get("cover_image") or payload.get("asset") or {}
                cover_rel_path = cover.get("relative_path")
                text = payload.get("text") or {}
                article = payload.get("article") or {}

                meta_bag = doc.get("metadata_json") or {}
                if "word_count" not in meta_bag:
                    meta_bag["word_count"] = text.get("word_count") or article.get("word_count")
                if "aspect_ratio" not in meta_bag and cover.get("aspect_ratio"):
                    meta_bag["aspect_ratio"] = cover.get("aspect_ratio")
                if "blurhash" not in meta_bag and cover.get("blurhash"):
                    meta_bag["blurhash"] = cover.get("blurhash")

                with conn:
                    conn.execute("""
                        INSERT INTO atoms (
                            id, kind, created_at, updated_at, atom_title, notes, tags,
                            collections, favorite, destination_url, cover_file_path,
                            text_content, source_url, author, metadata, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        atom_id, kind, now_iso, doc.get("updated_at", now_iso),
                        cur.get("atom_title", "Untitled"), cur.get("notes"),
                        json.dumps(cur.get("tags", [])), json.dumps(cur.get("collections", [])),
                        1 if cur.get("favorite") else 0, payload.get("destination_url"),
                        cover_rel_path, text.get("excerpt"), prov.get("source_url"),
                        prov.get("author"), json.dumps(meta_bag), json.dumps(doc)
                    ))
                count += 1
            except Exception as e:
                print(f"⚠️ Error parsing {atom_file}: {e}")

    print(f"🎉 Disaster Recovery complete! Successfully indexed {count} atoms into vault.db.")


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


def main():
    parser = argparse.ArgumentParser(description="OpenCurate CLI - Local-first web curation framework")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Path to OpenCurate vault directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Link command (and alias 'save')
    p_link = subparsers.add_parser("link", help="Save a link/webpage into the vault")
    p_link.add_argument("url", help="The webpage URL to capture")
    p_link.add_argument("--title", help="Custom atom title (defaults to page title)")
    p_link.add_argument("--notes", help="Personal curation notes")
    p_link.add_argument("--tags", help="Comma-separated tags (e.g. design,systems)")
    p_link.add_argument("--collection", help="Collection name")
    p_link.add_argument("--image-url", help="Override primary image URL")
    p_link.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_link.add_argument("--favorite", action="store_true", help="Mark as favorite")
    p_link.set_defaults(func=cmd_save_link)

    p_save = subparsers.add_parser("save", help="Alias for 'link'")
    p_save.add_argument("url", help="The webpage URL to capture")
    p_save.add_argument("--title", help="Custom atom title (defaults to page title)")
    p_save.add_argument("--notes", help="Personal curation notes")
    p_save.add_argument("--tags", help="Comma-separated tags")
    p_save.add_argument("--collection", help="Collection name")
    p_save.add_argument("--image-url", help="Override primary image URL")
    p_save.add_argument("--quote", help="Accompanying text quote or excerpt")
    p_save.add_argument("--favorite", action="store_true", help="Mark as favorite")
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
    p_quote.add_argument("--favorite", action="store_true", help="Mark as favorite")
    p_quote.set_defaults(func=cmd_quote)

    # 3. Note command
    p_note = subparsers.add_parser("note", help="Save a personal thought or memo")
    p_note.add_argument("text", help="The body of the note/thought")
    p_note.add_argument("--title", help="Custom title for the note")
    p_note.add_argument("--tags", help="Comma-separated tags")
    p_note.add_argument("--collection", help="Collection name")
    p_note.add_argument("--favorite", action="store_true", help="Mark as favorite")
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
    p_image.add_argument("--favorite", action="store_true", help="Mark as favorite")
    p_image.set_defaults(func=cmd_image)

    # 5. List command
    p_list = subparsers.add_parser("list", help="List atoms in the vault")
    p_list.add_argument("--kind", choices=["quote", "note", "link", "image", "video", "file"], help="Filter by kind")
    p_list.add_argument("--tag", help="Filter by tag")
    p_list.add_argument("--collection", help="Filter by collection")
    p_list.add_argument("--limit", type=int, default=20, help="Number of items to show")
    p_list.set_defaults(func=cmd_list)

    # 6. Export command
    p_export = subparsers.add_parser("export", help="Export atoms to platform formats")
    p_export.add_argument("--target", choices=["arena-csv", "json"], default="arena-csv", help="Export target")
    p_export.add_argument("--kind", choices=["quote", "note", "link", "image", "video", "file"], help="Filter by kind")
    p_export.add_argument("--tag", help="Filter by tag")
    p_export.add_argument("--out", help="Output file path (default: stdout)")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
