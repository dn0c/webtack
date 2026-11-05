#!/usr/bin/env python3
"""
WideWeb — Fast Multi-Threaded Ingest for Are.na Reading Channel (10,243 blocks)
Processes downloaded dump from vault/import/arena_reading.json into WideWeb atoms
with concurrent thumbnail/cover downloads, blurhash generation, and atomic SQLite batch inserts.
"""

import sys
import os
import json
import time
import hashlib
import re
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curate import (
    get_db, generate_atom_id, extract_dominant_colors,
    compute_blurhash, extract_author_and_source_title,
    normalize_tags, SCHEMA_URL, sanitize_text, get_http_session
)
from viewer import generate_viewer


def fast_download_image(image_url: str, dest_path: Path) -> dict | None:
    session = get_http_session()
    try:
        resp = session.get(image_url, timeout=(2.0, 4.0))
    except Exception:
        try:
            resp = session.get(image_url, timeout=(2.0, 4.0), verify=False)
        except Exception:
            return None

    if resp.status_code != 200:
        return None

    content = resp.content
    if not content or len(content) < 100:
        return None

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


def parse_block_timestamp(b: dict) -> datetime:
    ts_str = b.get("connected_at") or b.get("created_at") or b.get("updated_at")
    if ts_str:
        try:
            # Handle ISO formats like 2026-03-23T21:25:33.880Z
            clean_ts = ts_str.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_ts)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def extract_block_image_url(b: dict) -> str | None:
    img = b.get("image")
    if not img or not isinstance(img, dict):
        return None
    # Prefer display (1200px max) or original or large
    display = img.get("display")
    if isinstance(display, dict) and display.get("url"):
        return display["url"]
    large = img.get("large")
    if isinstance(large, dict) and large.get("url"):
        return large["url"]
    orig = img.get("original")
    if isinstance(orig, dict) and orig.get("url"):
        return orig["url"]
    thumb = img.get("thumb")
    if isinstance(thumb, dict) and thumb.get("url"):
        return thumb["url"]
    if img.get("src"):
        return img["src"]
    return None


def process_reading_block(b: dict, vault_dir: Path, existing_urls: set, existing_texts: set) -> tuple | None:
    b_class = b.get("class") or b.get("base_class") or "Block"
    b_title = (b.get("title") or b.get("generated_title") or "").strip()
    b_desc = sanitize_text(b.get("description") or b.get("description_html") or "")

    source_dict = b.get("source") or {}
    source_url = source_dict.get("url") if isinstance(source_dict, dict) else None
    if not source_url and b.get("embed"):
        source_url = b["embed"].get("source_url") or b["embed"].get("url")

    # Text content for Text blocks
    text_content = None
    if b_class == "Text":
        content_raw = b.get("content") or b.get("content_html") or ""
        if isinstance(content_raw, dict):
            text_content = content_raw.get("plain") or content_raw.get("markdown") or content_raw.get("html") or ""
        else:
            text_content = str(content_raw)
        text_content = text_content.strip()

    # Deduplication
    if b_class == "Text" and text_content:
        text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        if text_hash in existing_texts:
            return None
    elif source_url:
        if source_url in existing_urls:
            return None
    else:
        # Blocks without URL or content cannot be stored
        if not b_title:
            return None

    # Determine kind
    kind = "bookmark"
    if b_class == "Image":
        kind = "image"
    elif b_class in ("Media", "Embed"):
        kind = "video"
    elif b_class == "Text":
        if ('"' in text_content or '“' in text_content) or source_url or "quote" in b_title.lower():
            kind = "quote"
        else:
            kind = "note"
    elif b_class == "Link":
        kind = "bookmark"

    # Provider / Site Name
    site_name = None
    if isinstance(source_dict, dict) and source_dict.get("provider"):
        site_name = source_dict["provider"].get("name")
    if not site_name and source_url:
        try:
            site_name = urlparse(source_url).netloc
        except Exception:
            pass

    atom_id = generate_atom_id()
    dt = parse_block_timestamp(b)
    iso_date = dt.isoformat()

    rel_folder = Path("atoms") / f"{dt.year}" / f"{dt.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    # Download cover/preview image if available
    img_url = extract_block_image_url(b)
    cover_meta = None
    cover_rel_path = None
    if img_url:
        cover_filename = "cover.jpg"
        abs_cover = abs_folder / cover_filename
        downloaded = None
        try:
            downloaded = fast_download_image(img_url, abs_cover)
        except Exception:
            pass

        if downloaded:
            cover_rel_path = str(rel_folder / cover_filename)
            cover_meta = {
                "file": cover_filename,
                "relative_path": cover_rel_path,
                "mime_type": downloaded.get("mime_type", "image/jpeg"),
                "hash": downloaded.get("hash", ""),
                "dimensions": downloaded.get("dimensions", {"width": 0, "height": 0}),
                "aspect_ratio": downloaded.get("aspect_ratio") or 1.5,
                "blurhash": downloaded.get("blurhash"),
                "color_palette": downloaded.get("color_palette", []),
                "alt_text": b_title or "Cover",
                "original_src_url": img_url
            }

    author = None
    if isinstance(source_dict, dict) and source_dict.get("author"):
        author = source_dict["author"]
    elif b.get("user") and b_class == "Image":
        author = b["user"].get("name")

    final_title = b_title or (source_dict.get("title") if isinstance(source_dict, dict) else None) or site_name or "Reading Bookmark"
    tags = ["reading"]
    collections = ["Reading"]
    visibility = "public"

    meta_bag = {
        "site_name": site_name,
        "aspect_ratio": cover_meta["aspect_ratio"] if cover_meta else None,
        "blurhash": cover_meta["blurhash"] if cover_meta else None,
        "color_palette": cover_meta["color_palette"] if cover_meta else None,
        "arena_block_id": b.get("id"),
        "arena_class": b_class
    }

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": kind,
        "version": 2,
        "created_at": iso_date,
        "updated_at": iso_date,
        "provenance": {
            "source_url": source_url,
            "source_title": final_title,
            "canonical_url": source_url,
            "site_name": site_name,
            "author": author,
            "author_url": None,
            "published_at": None,
            "favicon": None
        },
        "curation": {
            "atom_title": final_title,
            "notes": b_desc if b_desc else None,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": False
        },
        "payload": {
            "destination_url": source_url,
            "cover_image": cover_meta,
            "text": text_content,
            "article": None,
            "video": None,
            "file": None
        }
    }

    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2, ensure_ascii=False)

    db_row = (
        atom_id,
        kind,
        iso_date,
        iso_date,
        final_title,
        b_desc if b_desc else None,
        json.dumps(tags),
        json.dumps(collections),
        0,
        source_url,
        cover_rel_path,
        text_content,
        source_url,
        author,
        json.dumps(meta_bag),
        json.dumps(atom_doc),
        visibility
    )

    dedup_key = source_url if source_url else (hashlib.sha256(text_content.encode("utf-8")).hexdigest() if text_content else None)
    return db_row, dedup_key, (b_class == "Text")


def main():
    vault_dir = Path(__file__).resolve().parent.parent / "vault"
    dump_file = vault_dir / "import" / "arena_reading.json"

    if not dump_file.exists():
        print(f"❌ Error: {dump_file} not found. Run download_reading_channel.py first.")
        sys.exit(1)

    print(f"📂 Loading {dump_file}...")
    with open(dump_file, "r", encoding="utf-8") as f:
        dump = json.load(f)

    blocks = dump.get("data", [])
    print(f"🧱 Found {len(blocks)} blocks in dump.")

    conn = get_db(vault_dir)
    rows = conn.execute("SELECT destination_url, source_url, text_content FROM atoms").fetchall()
    existing_urls = set()
    existing_texts = set()
    for r in rows:
        if r["destination_url"]:
            existing_urls.add(r["destination_url"])
        if r["source_url"]:
            existing_urls.add(r["source_url"])
        if r["text_content"]:
            existing_texts.add(hashlib.sha256(r["text_content"].encode("utf-8")).hexdigest())

    print(f"🔍 Found {len(existing_urls)} URLs and {len(existing_texts)} text blocks for deduplication.")

    # Pre-filter blocks
    pending_blocks = []
    skipped = 0
    for b in blocks:
        s_url = None
        if b.get("source") and isinstance(b["source"], dict):
            s_url = b["source"].get("url")
        if not s_url and b.get("embed"):
            s_url = b["embed"].get("source_url") or b["embed"].get("url")

        if s_url and s_url in existing_urls:
            skipped += 1
            continue

        if b.get("class") == "Text":
            raw = b.get("content") or b.get("content_html") or ""
            if isinstance(raw, dict):
                raw = raw.get("plain") or raw.get("markdown") or ""
            raw = str(raw).strip()
            if raw and hashlib.sha256(raw.encode("utf-8")).hexdigest() in existing_texts:
                skipped += 1
                continue

        pending_blocks.append(b)

    print(f"⚡ To process: {len(pending_blocks)} blocks ({skipped} already exist in vault).")

    if not pending_blocks:
        print("✅ Nothing new to ingest!")
        return

    BATCH_SIZE = 100
    NUM_WORKERS = 16
    total_imported = 0
    t0 = time.time()

    print(f"🚀 Starting ingestion with {NUM_WORKERS} worker threads in batches of {BATCH_SIZE}...")

    for i in range(0, len(pending_blocks), BATCH_SIZE):
        chunk = pending_blocks[i:i + BATCH_SIZE]
        chunk_t0 = time.time()
        db_rows = []

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = [executor.submit(process_reading_block, b, vault_dir, existing_urls, existing_texts) for b in chunk]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        db_row, dedup_key, is_text = res
                        db_rows.append(db_row)
                        if dedup_key:
                            if is_text:
                                existing_texts.add(dedup_key)
                            else:
                                existing_urls.add(dedup_key)
                except Exception as e:
                    print(f"⚠️ Worker error: {e}")

        if db_rows:
            with conn:
                conn.executemany("""
                    INSERT INTO atoms (
                        id, kind, created_at, updated_at, atom_title, notes, tags,
                        collections, favorite, destination_url, cover_file_path,
                        text_content, source_url, author, metadata, raw_json, visibility
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, db_rows)
            total_imported += len(db_rows)

        chunk_time = time.time() - chunk_t0
        elapsed = time.time() - t0
        rate = total_imported / elapsed if elapsed > 0 else 0
        rem_items = len(pending_blocks) - (i + len(chunk))
        est_rem = rem_items / rate if rate > 0 else 0
        print(f"[{total_imported}/{len(pending_blocks)}] Batch of {len(db_rows)} committed in {chunk_time:.1f}s | Speed: {rate:.1f} items/s | ETA: {est_rem:.0f}s")

    elapsed_total = time.time() - t0
    print(f"\n🎉 Ingestion complete in {elapsed_total:.1f}s!")
    print(f"✅ Imported: {total_imported} new reading atoms")
    print(f"⏭️ Skipped (Duplicates): {skipped}")

    print("\n✨ Regenerating WideWeb viewer...")
    generate_viewer(vault_dir)
    print("✨ Viewer updated successfully!")


if __name__ == "__main__":
    main()
