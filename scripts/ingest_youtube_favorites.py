#!/usr/bin/env python3
"""
WideWeb — Fast Batch Ingest for Are.na YouTube Favorites Channel
Processes 1,498 blocks with concurrent thumbnail downloads, transcript fetching,
and atomic SQLite inserts.
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from curate import (
    get_db, generate_atom_id, download_image,
    fetch_youtube_transcript, SCHEMA_URL
)
from viewer import generate_viewer


def extract_yt_video_id(url: str) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if "youtube.com" in netloc:
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                return qs.get("v", [None])[0]
            elif parsed.path.startswith("/shorts/"):
                return parsed.path.split("/shorts/")[1].split("/")[0].split("?")[0]
            elif parsed.path.startswith("/embed/"):
                return parsed.path.split("/embed/")[1].split("/")[0].split("?")[0]
        elif "youtu.be" in netloc:
            return parsed.path.strip("/").split("/")[0].split("?")[0]
    except Exception:
        pass
    return None


def process_video_block(b: dict, vault_dir: Path, existing_urls: set) -> tuple | None:
    b_title = b.get("title") or "YouTube Video"
    b_desc = b.get("description")
    if isinstance(b_desc, dict):
        b_desc = b_desc.get("plain") or b_desc.get("markdown") or ""
    b_desc = (b_desc or "").strip()

    source_url = (b.get("source") or {}).get("url") or (b.get("embed") or {}).get("source_url") or ""
    if not source_url:
        return None

    video_id = extract_yt_video_id(source_url)
    if not video_id:
        return None

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    if canonical_url in existing_urls or source_url in existing_urls:
        return None

    embed_url = f"https://www.youtube.com/embed/{video_id}"

    atom_id = generate_atom_id()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    rel_folder = Path("atoms") / f"{now.year}" / f"{now.month:02d}" / atom_id
    abs_folder = vault_dir / rel_folder
    abs_folder.mkdir(parents=True, exist_ok=True)

    author = (b.get("embed") or {}).get("author_name") or None
    author_url = (b.get("embed") or {}).get("author_url") or None

    # Cover image download
    thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    arena_img = b.get("image") or {}
    arena_src = arena_img.get("src")

    cover_meta = None
    cover_rel_path = None
    cover_filename = "cover.jpg"
    abs_cover = abs_folder / cover_filename

    downloaded = None
    try:
        downloaded = download_image(thumb_url, abs_cover)
    except Exception:
        pass

    if not downloaded and arena_src:
        try:
            downloaded = download_image(arena_src, abs_cover)
        except Exception:
            pass

    if downloaded:
        cover_rel_path = str(rel_folder / cover_filename)
        bhash = downloaded.get("blurhash") or arena_img.get("blurhash")
        ratio = downloaded.get("aspect_ratio") or arena_img.get("aspect_ratio") or 1.333
        cover_meta = {
            "file": cover_filename,
            "relative_path": cover_rel_path,
            "mime_type": downloaded.get("mime_type", "image/jpeg"),
            "hash": downloaded.get("hash", ""),
            "dimensions": downloaded.get("dimensions", {"width": 480, "height": 360}),
            "aspect_ratio": ratio,
            "blurhash": bhash,
            "color_palette": downloaded.get("color_palette", []),
            "alt_text": b_title,
            "original_src_url": thumb_url
        }

    # Transcripts
    transcript_data = None
    try:
        transcript_data = fetch_youtube_transcript(video_id)
    except Exception:
        pass

    transcript_txt_rel = None
    transcript_json_rel = None
    if transcript_data:
        try:
            txt_path = abs_folder / "transcript.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript_data["plain_text"])
            transcript_txt_rel = str(rel_folder / "transcript.txt")

            json_path = abs_folder / "transcript.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(transcript_data["snippets"], f, indent=2)
            transcript_json_rel = str(rel_folder / "transcript.json")
        except Exception:
            pass

    meta_bag = {
        "provider": "YouTube",
        "video_id": video_id,
        "embed_url": embed_url,
        "aspect_ratio": cover_meta["aspect_ratio"] if cover_meta else None,
        "blurhash": cover_meta["blurhash"] if cover_meta else None,
        "color_palette": cover_meta["color_palette"] if cover_meta else None,
        "favicon": "https://www.youtube.com/s/desktop/12d6b690/img/favicon_144x144.png",
        "has_transcript": bool(transcript_data),
        "transcript_snippets": len(transcript_data["snippets"]) if transcript_data else 0,
        "transcript_language": transcript_data["language"] if transcript_data else None
    }

    tags = ["youtube-favorites"]
    collections = ["YouTube Favorites"]
    visibility = "public"

    atom_doc = {
        "$schema": SCHEMA_URL,
        "id": atom_id,
        "kind": "video",
        "version": 2,
        "created_at": now_iso,
        "updated_at": now_iso,
        "provenance": {
            "source_url": canonical_url,
            "source_title": b_title,
            "canonical_url": canonical_url,
            "site_name": "YouTube",
            "author": author,
            "author_url": author_url,
            "published_at": None,
            "favicon": "https://www.youtube.com/s/desktop/12d6b690/img/favicon_144x144.png"
        },
        "curation": {
            "atom_title": b_title,
            "notes": b_desc if b_desc else None,
            "tags": tags,
            "collections": collections,
            "visibility": visibility,
            "favorite": False
        },
        "payload": {
            "destination_url": canonical_url,
            "cover_image": cover_meta,
            "text": None,
            "article": None,
            "video": {
                "provider": "YouTube",
                "embed_url": embed_url,
                "duration_seconds": None,
                "transcript_file": transcript_txt_rel,
                "transcript_json": transcript_json_rel,
                "transcript_language": transcript_data["language"] if transcript_data else None,
                "transcript_is_generated": transcript_data["is_generated"] if transcript_data else None,
                "has_transcript": bool(transcript_data)
            },
            "file": None
        }
    }

    atom_json_path = abs_folder / "atom.json"
    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(atom_doc, f, indent=2, ensure_ascii=False)

    db_row = (
        atom_id,
        "video",
        now_iso,
        now_iso,
        b_title,
        b_desc if b_desc else None,
        json.dumps(tags),
        json.dumps(collections),
        0,
        canonical_url,
        cover_rel_path,
        transcript_data["speech_text"] if transcript_data else None,
        canonical_url,
        author,
        json.dumps(meta_bag),
        json.dumps(atom_doc),
        visibility
    )
    return db_row, canonical_url, bool(transcript_data)


def main():
    vault_dir = Path(__file__).parent / "vault"
    dump_file = vault_dir / "import" / "arena_youtube-favorites.json"

    if not dump_file.exists():
        print(f"❌ Error: {dump_file} not found.")
        sys.exit(1)

    print(f"📂 Loading {dump_file}...")
    with open(dump_file, "r", encoding="utf-8") as f:
        dump = json.load(f)

    blocks = dump.get("data", [])
    print(f"🧱 Found {len(blocks)} blocks in dump.")

    conn = get_db(vault_dir)
    rows = conn.execute("SELECT destination_url, source_url FROM atoms").fetchall()
    existing_urls = set()
    for r in rows:
        if r["destination_url"]:
            existing_urls.add(r["destination_url"])
        if r["source_url"]:
            existing_urls.add(r["source_url"])

    print(f"🔍 Found {len(existing_urls)} existing URLs in vault for deduplication.")

    # Filter out blocks already known to exist
    pending_blocks = []
    skipped = 0
    for b in blocks:
        s_url = (b.get("source") or {}).get("url") or (b.get("embed") or {}).get("source_url") or ""
        vid = extract_yt_video_id(s_url)
        canon = f"https://www.youtube.com/watch?v={vid}" if vid else s_url
        if canon in existing_urls or s_url in existing_urls:
            skipped += 1
        else:
            pending_blocks.append(b)

    print(f"⚡ To process: {len(pending_blocks)} blocks ({skipped} already exist in vault).")

    if not pending_blocks:
        print("✅ Nothing new to ingest!")
        return

    BATCH_SIZE = 50
    NUM_WORKERS = 8
    total_imported = 0
    total_transcripts = 0
    t0 = time.time()

    print(f"🚀 Starting ingestion with {NUM_WORKERS} worker threads...")

    # Process in chunks of BATCH_SIZE to commit regularly
    for i in range(0, len(pending_blocks), BATCH_SIZE):
        chunk = pending_blocks[i:i + BATCH_SIZE]
        chunk_t0 = time.time()
        db_rows = []

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = [executor.submit(process_video_block, b, vault_dir, existing_urls) for b in chunk]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        db_row, canon_url, has_tx = res
                        db_rows.append(db_row)
                        existing_urls.add(canon_url)
                        if has_tx:
                            total_transcripts += 1
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
        print(f"[{total_imported}/{len(pending_blocks)}] Batch of {len(db_rows)} committed in {chunk_time:.1f}s | Speed: {rate:.1f} items/s | Transcripts: {total_transcripts} | ETA: {est_rem:.0f}s")

    elapsed_total = time.time() - t0
    print(f"\n🎉 Ingestion complete in {elapsed_total:.1f}s!")
    print(f"✅ Imported: {total_imported} new video atoms")
    print(f"📜 Spoken Captions Fetched: {total_transcripts} videos")
    print(f"⏭️ Skipped (Duplicates): {skipped}")

    print("\n✨ Regenerating WideWeb viewer...")
    generate_viewer(vault_dir)
    print("✨ Viewer updated successfully!")


if __name__ == "__main__":
    main()
