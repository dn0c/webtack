#!/usr/bin/env python3
"""
Webtack — Are.na Channel Importer Integration
Imports blocks from an Are.na channel (remote slug, ID, or JSON dump) into Webtack atoms.
"""

import os
import sys
import json
import re
import html
import types
from urllib.parse import unquote
import requests
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import curate
import viewer


def import_channel(channel_input: str, vault_dir: Path, limit: int = 100, tag: str = None, collection: str = None, visibility: str = None):
    """Import blocks from an Are.na channel (remote slug/ID or JSON dump) into Webtack atoms."""
    vault_dir = Path(vault_dir).resolve()
    channel_input = channel_input.strip()

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
        headers = {"User-Agent": "Webtack/1.0"}
        token = os.environ.get("ARENA_TOKEN") or os.environ.get("ARENA_API_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_url = f"https://api.are.na/v2/channels/{channel_input}?per={limit}"
        print(f"📡 Fetching Are.na channel '{channel_input}' from API...")
        try:
            session = curate.get_http_session()
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
                    print("❌ Please provide ARENA_API_TOKEN or a JSON dump file.")
                    return 0
            else:
                print(f"❌ Error fetching Are.na channel: HTTP {resp.status_code}")
                return 0
        except Exception as e:
            print(f"❌ Network error: {e}")
            return 0

    if not blocks:
        print(f"ℹ️ No blocks found for channel '{channel_input}'.")
        return 0

    print(f"\n🧱 Ingesting {len(blocks)} blocks from Are.na channel '{channel_title}'...")
    conn = curate.get_db(vault_dir)
    imported = 0
    skipped = 0

    clean_tag = re.sub(r'[^a-zA-Z0-9]+', '-', channel_title.lower()).strip('-') or "arena"
    base_tags = [clean_tag]
    if tag:
        base_tags.extend(curate.normalize_tags(tag))

    # Determine default visibility for channel
    channel_vis = visibility
    if not channel_vis:
        ch_low = (collection or channel_title).lower()
        if "work (private)" in ch_low or "private" in ch_low:
            channel_vis = "private"
        elif any(k in ch_low for k in ("wishlist", "sarah", "mom & dad", "mom-dad")):
            channel_vis = "shared"
        else:
            channel_vis = "public"

    for b in blocks:
        b_class = b.get("class") or b.get("type") or "Block"
        b_title = b.get("title") or b.get("name")
        b_desc = curate.sanitize_text(b.get("description") or b.get("description_html"))
        b_id = str(b["id"]) if b.get("id") else None
        b_url = f"https://www.are.na/block/{b_id}" if b_id else None

        block_vis = channel_vis
        if b.get("visibility") == "private" and channel_vis == "public":
            block_vis = "shared"

        source_url = None
        if b.get("source") and isinstance(b["source"], dict):
            source_url = b["source"].get("url")
            if source_url and "rdl.ink" in source_url and "/render/" in source_url:
                source_url = unquote(source_url.split("/render/", 1)[1])

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
        if b_class in ("Media", "Embed") or (source_url and curate.extract_video_info(source_url)):
            v_url = source_url or b.get("embed", {}).get("url")
            if v_url:
                v_args = types.SimpleNamespace(
                    url=v_url,
                    title=b_title,
                    notes=b_desc,
                    tags=",".join(base_tags),
                    collection=collection or channel_title,
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
                    curate.cmd_video(v_args)
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
                    collection=collection or channel_title,
                    visibility=block_vis,
                    favorite=False,
                    vault=str(vault_dir),
                    arena_block_id=b.get("id"),
                    capture_method="arena",
                    capture_id=b_id,
                    capture_url=b_url
                )
                try:
                    curate.cmd_image(img_args)
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
                    collection=collection or channel_title,
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
                    curate.cmd_save_link(l_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Link import failed for {source_url}: {e}")

        # 4. Text (Quote or Note)
        elif b_class == "Text":
            if content:
                extracted_author, clean_title = curate.extract_author_and_source_title(b_title)
                is_quote = (
                    source_url is not None
                    or any(k in (collection or channel_title).lower() for k in ("quote", "highlight", "reading"))
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
                        collection=collection or channel_title,
                        visibility=block_vis,
                        favorite=False,
                        vault=str(vault_dir),
                        capture_method="arena",
                        capture_id=b_id,
                        capture_url=b_url
                    )
                    curate.cmd_quote(q_args)
                else:
                    n_args = types.SimpleNamespace(
                        text=content,
                        title=final_title,
                        tags=",".join(base_tags),
                        collection=collection or channel_title,
                        visibility=block_vis,
                        favorite=False,
                        vault=str(vault_dir),
                        capture_method="arena",
                        capture_id=b_id,
                        capture_url=b_url
                    )
                    curate.cmd_note(n_args)
                imported += 1

        # 5. Connected Channel
        elif b_class == "Channel":
            ch_url = f"https://www.are.na/channel/{b.get('slug') or b.get('id')}"
            l_args = types.SimpleNamespace(
                url=ch_url,
                title=f"Channel: {b_title}",
                notes=b_desc or f"Connected Are.na channel ({b.get('length', 0)} blocks)",
                tags=",".join(base_tags + ["arena-channel"]),
                collection=collection or channel_title,
                visibility=block_vis,
                image_url=None,
                quote=None,
                favorite=False,
                vault=str(vault_dir),
                target_kind="bookmark"
            )
            try:
                curate.cmd_save_link(l_args)
                imported += 1
            except Exception as e:
                print(f"   ⚠️ Channel block import failed: {e}")

        # 6. Attachment
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
                    collection=collection or channel_title,
                    visibility=block_vis,
                    image_url=img_thumb,
                    quote=None,
                    favorite=False,
                    vault=str(vault_dir),
                    target_kind="bookmark"
                )
                try:
                    curate.cmd_save_link(l_args)
                    imported += 1
                except Exception as e:
                    print(f"   ⚠️ Attachment block import failed: {e}")

    viewer.generate_viewer(vault_dir)
    print(f"\n✨ Completed Are.na import for '{channel_title}'!")
    print(f"   📥 Imported: {imported} new atoms")
    print(f"   ℹ️ Skipped:  {skipped} duplicates\n")
    return imported


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Are.na Channel Importer for Webtack")
    parser.add_argument("channel", help="Are.na channel slug, ID, or JSON file path")
    parser.add_argument("--vault", default="vault", help="Path to Webtack vault directory (default: vault)")
    parser.add_argument("--limit", type=int, default=100, help="Max blocks to fetch (default: 100)")
    parser.add_argument("--tag", help="Additional tag to apply to imported atoms")
    parser.add_argument("--collection", help="Collection name (defaults to channel title)")
    parser.add_argument("--visibility", choices=["public", "shared", "private"], help="Explicitly set visibility tier")
    args = parser.parse_args()

    import_channel(
        channel_input=args.channel,
        vault_dir=Path(args.vault),
        limit=args.limit,
        tag=args.tag,
        collection=args.collection,
        visibility=args.visibility
    )
