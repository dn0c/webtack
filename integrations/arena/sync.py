#!/usr/bin/env python3
"""
WideWeb — Are.na Feed Inbound Sync Integration
Pulls recently curated blocks across all Are.na channels for a user into WideWeb atoms.
"""

import os
import sys
import json
import re
import types
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import curate


def get_arena_token(vault_dir: Path = None) -> str | None:
    token = os.environ.get("ARENA_API_TOKEN") or os.environ.get("ARENA_TOKEN")
    if token:
        return token
    if vault_dir:
        cred_file = vault_dir / ".sync_credentials.json"
        if cred_file.exists():
            try:
                with open(cred_file, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    return c.get("arena_api_token")
            except Exception:
                pass
    mcp_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    if mcp_path.exists():
        try:
            with open(mcp_path, "r", encoding="utf-8") as f:
                mcp = json.load(f).get("mcpServers", {})
                auth_header = mcp.get("arena", {}).get("headers", {}).get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    return auth_header[7:].strip()
        except Exception:
            pass
    return None


def get_arena_user_id(token: str) -> str | None:
    env_id = os.environ.get("ARENA_USER_ID")
    if env_id:
        return env_id
    try:
        resp = requests.get(
            "https://api.are.na/v3/me",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "WideWeb/1.0"},
            timeout=10
        )
        if resp.status_code == 200:
            uid = resp.json().get("id")
            if uid:
                return str(uid)
    except Exception:
        pass
    return None


def get_block_channel_info(block_id: str, headers: dict):
    if not block_id:
        return None, None
    try:
        url = f"https://api.are.na/v3/blocks/{block_id}/connections"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            channels = r.json().get("data", [])
            if channels:
                first = channels[0]
                return first.get("title"), first.get("slug")
    except Exception:
        pass
    return None, None


def get_sync_state(vault_dir: Path) -> dict:
    state_file = vault_dir / ".sync_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"arena": {}}


def save_sync_state(vault_dir: Path, state: dict):
    state_file = vault_dir / ".sync_state.json"
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving sync state: {e}")


def sync_arena(vault_dir: Path, limit: int = 100, visibility: str = "public") -> int:
    vault_dir = Path(vault_dir).resolve()
    token = get_arena_token(vault_dir)
    if not token:
        print("❌ Are.na API token not found. Please set ARENA_API_TOKEN in .env.")
        return 0

    user_id = get_arena_user_id(token)
    if not user_id:
        print("❌ Could not determine Are.na user ID. Please set ARENA_USER_ID in .env.")
        return 0

    print(f"\n📥 [Are.na] Checking user contents (user={user_id}, limit={limit})...")
    url = f"https://api.are.na/v3/users/{user_id}/contents?per={limit}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 WideWeb/1.0"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"❌ Are.na API returned HTTP {resp.status_code}: {resp.text[:200]}")
            return 0
        data = resp.json()
        items = data.get("data", [])
    except Exception as e:
        print(f"❌ Error fetching Are.na contents: {e}")
        return 0

    if not items:
        print("   ℹ️ No recent Are.na blocks found.")
        return 0

    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    state = get_sync_state(vault_dir)
    arena_synced = set(state.setdefault("arena", {}).setdefault("synced_ids", []))
    imported = 0

    for it in items:
        block_id = str(it.get("id")) if it.get("id") else None
        block_type = it.get("type")
        title = it.get("title") or "Are.na Block"
        desc_obj = it.get("description")
        notes = (desc_obj.get("plain") or desc_obj.get("markdown")) if isinstance(desc_obj, dict) else (desc_obj or None)
        source_url = it.get("source", {}).get("url") if isinstance(it.get("source"), dict) else None

        if block_id and block_id in arena_synced:
            continue

        try:
            ch_title, ch_slug = get_block_channel_info(block_id, headers)
            is_reading_highlights = (
                ch_slug == "reading-highlights-quotes" or
                (ch_title and "highlight" in ch_title.lower()) or
                (notes and "highlight from:" in notes.lower())
            )
            collection_name = "Reading Highlights" if is_reading_highlights else (ch_title or "Are.na")
            tag_slug = ch_slug or "are.na"
            tags_list = f"are.na,{tag_slug}" if tag_slug != "are.na" else "are.na"

            content_obj = it.get("content")
            text_content = (content_obj.get("plain") or content_obj.get("markdown")) if isinstance(content_obj, dict) else (content_obj or notes)

            arena_bid = str(block_id) if block_id else None
            arena_burl = f"https://www.are.na/block/{arena_bid}" if arena_bid else None

            if is_reading_highlights and text_content:
                print(f"   ✨ Ingesting Quote: {title[:50]}...")
                args = types.SimpleNamespace(
                    quote=text_content,
                    title=title,
                    source=source_url,
                    source_title=title,
                    author=it.get("user", {}).get("name"),
                    notes=None,
                    tags=f"{tags_list},reading-highlights",
                    collection="Reading Highlights",
                    favorite=False,
                    vault=str(vault_dir),
                    visibility=visibility,
                    capture_method="arena",
                    capture_id=arena_bid,
                    capture_url=arena_burl
                )
                curate.cmd_quote(args)
                imported += 1

            elif block_type in ("Link", "Embed") and source_url:
                print(f"   ✨ Ingesting Link: {title[:50]}...")
                args = types.SimpleNamespace(
                    url=source_url,
                    title=title,
                    notes=notes,
                    tags=tags_list,
                    collection=collection_name,
                    image_url=it.get("image", {}).get("src") if isinstance(it.get("image"), dict) else None,
                    quote=None,
                    favorite=False,
                    vault=str(vault_dir),
                    visibility=visibility,
                    target_kind=None,
                    capture_method="arena",
                    capture_id=arena_bid,
                    capture_url=arena_burl
                )
                curate.cmd_save_link(args)
                imported += 1

            elif block_type == "Image":
                img_data = it.get("image") or {}
                img_src = img_data.get("src") or img_data.get("large", {}).get("src")
                if img_src:
                    print(f"   ✨ Ingesting Image: {title[:50]}...")
                    args = types.SimpleNamespace(
                        src=img_src,
                        title=title,
                        notes=notes,
                        alt=img_data.get("alt_text"),
                        tags=tags_list,
                        collection=collection_name,
                        author=it.get("user", {}).get("name") if isinstance(it.get("user"), dict) else None,
                        source=source_url,
                        favorite=False,
                        vault=str(vault_dir),
                        visibility=visibility,
                        arena_block_id=block_id,
                        capture_method="arena",
                        capture_id=arena_bid,
                        capture_url=arena_burl
                    )
                    curate.cmd_image(args)
                    imported += 1

            elif block_type == "Text":
                if text_content:
                    print(f"   ✨ Ingesting Text: {title[:50]}...")
                    args = types.SimpleNamespace(
                        text=text_content,
                        title=title,
                        tags=tags_list,
                        collection=collection_name,
                        favorite=False,
                        vault=str(vault_dir),
                        visibility=visibility,
                        capture_method="arena",
                        capture_id=arena_bid,
                        capture_url=arena_burl
                    )
                    curate.cmd_note(args)
                    imported += 1

            if block_id:
                state["arena"]["synced_ids"].append(block_id)
                state["arena"]["last_synced_id"] = block_id

        except Exception as err:
            print(f"      ⚠️ Failed to ingest Are.na block {block_id}: {err}")

    conn.close()
    save_sync_state(vault_dir, state)
    print(f"✅ [Are.na] Ingested {imported} new atoms.")
    return imported


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync recent Are.na blocks into WideWeb")
    parser.add_argument("--vault", default="vault", help="Path to WideWeb vault directory (default: vault)")
    parser.add_argument("--limit", type=int, default=100, help="Max blocks to fetch (default: 100)")
    parser.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier")
    args = parser.parse_args()

    sync_arena(Path(args.vault), limit=args.limit, visibility=args.visibility)
