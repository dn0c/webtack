#!/usr/bin/env python3
"""
WideWeb — Inbound Sync for Instapaper & Are.na
Pulls newly bookmarked/saved items from Instapaper (unread) and Are.na (all channels)
into local WideWeb atoms with deduplication, payload enrichment, and automatic schema validation.
"""

import os
import json
import sqlite3
import types
from pathlib import Path
from urllib.parse import urlparse

import requests

CONFIG_MCP_PATH = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
ARENA_USER_ID = "1211866"


def get_credentials(vault_dir: Path):
    """Retrieve Instapaper and Are.na tokens from environment, local config, or MCP config."""
    instapaper_token = os.environ.get("INSTAPAPER_ACCESS_TOKEN")
    arena_token = os.environ.get("ARENA_API_TOKEN")

    # Local credentials override
    cred_file = vault_dir / ".sync_credentials.json"
    if cred_file.exists():
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                c = json.load(f)
                instapaper_token = instapaper_token or c.get("instapaper_access_token")
                arena_token = arena_token or c.get("arena_api_token")
        except Exception:
            pass

    # MCP config fallback
    if (not instapaper_token or not arena_token) and CONFIG_MCP_PATH.exists():
        try:
            with open(CONFIG_MCP_PATH, "r", encoding="utf-8") as f:
                mcp = json.load(f).get("mcpServers", {})
                if not instapaper_token:
                    instapaper_token = mcp.get("instapaper", {}).get("env", {}).get("INSTAPAPER_ACCESS_TOKEN")
                if not arena_token:
                    auth_header = mcp.get("arena", {}).get("headers", {}).get("Authorization", "")
                    if auth_header.startswith("Bearer "):
                        arena_token = auth_header[7:].strip()
        except Exception:
            pass

    return {
        "instapaper_access_token": instapaper_token,
        "arena_api_token": arena_token
    }


def get_sync_state(vault_dir: Path) -> dict:
    """Load sync state checkpoint."""
    state_file = vault_dir / ".sync_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"instapaper": {}, "arena": {}}


def save_sync_state(vault_dir: Path, state: dict):
    """Save sync state checkpoint."""
    state_file = vault_dir / ".sync_state.json"
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving sync state: {e}")


def url_exists_in_vault(conn: sqlite3.Connection, url: str) -> bool:
    """Check if a URL already exists as destination_url or source_url in SQLite."""
    if not url:
        return False
    clean = url.strip()
    alt_clean = clean.rstrip("/") if clean.endswith("/") else clean + "/"
    row = conn.execute(
        "SELECT id FROM atoms WHERE destination_url = ? OR destination_url = ? OR source_url = ? OR source_url = ? LIMIT 1",
        (clean, alt_clean, clean, alt_clean)
    ).fetchone()
    return row is not None


def pull_instapaper(vault_dir: Path, limit: int = 25, visibility: str = "public"):
    """Pull unread bookmarks from Instapaper into WideWeb."""
    import curate

    creds = get_credentials(vault_dir)
    token = creds.get("instapaper_access_token")
    if not token:
        print("⚠️ Instapaper access token not found. Skipping Instapaper sync.")
        return 0

    print(f"\n📥 [Instapaper] Checking unread bookmarks (limit={limit})...")
    url = f"https://www.instapaper.com/api/2/bookmarks?section=home&limit={limit}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"❌ Instapaper API returned HTTP {resp.status_code}: {resp.text[:200]}")
            return 0
        data = resp.json()
        bookmarks = data.get("bookmarks", [])
    except Exception as e:
        print(f"❌ Error fetching Instapaper bookmarks: {e}")
        return 0

    if not bookmarks:
        print("   ℹ️ No unread bookmarks found.")
        return 0

    conn = sqlite3.connect(vault_dir / "vault.db")
    state = get_sync_state(vault_dir)
    imported = 0

    for b in bookmarks:
        bm_url = b.get("url")
        bm_id = str(b.get("id")) if b.get("id") else None
        if not bm_url:
            continue

        instapaper_synced = set(state.setdefault("instapaper", {}).setdefault("synced_ids", []))
        if bm_id and bm_id in instapaper_synced:
            continue
        if url_exists_in_vault(conn, bm_url):
            if bm_id:
                state["instapaper"]["synced_ids"].append(bm_id)
            continue

        title = b.get("title") or "Untitled Bookmark"
        desc = b.get("description") or None

        print(f"   ✨ Ingesting: {title[:50]}... ({bm_url[:40]}...)")
        args = types.SimpleNamespace(
            url=bm_url,
            title=title,
            notes=desc,
            tags="instapaper",
            collection="Reading",
            image_url=b.get("image"),
            quote=None,
            favorite=False,
            vault=str(vault_dir),
            visibility=visibility,
            target_kind="article"
        )
        try:
            curate.cmd_save_link(args)
            imported += 1
            if bm_id:
                state["instapaper"]["synced_ids"].append(bm_id)
                state["instapaper"]["last_synced_id"] = bm_id
        except Exception as err:
            print(f"      ⚠️ Failed to ingest '{title}': {err}")

    conn.close()
    save_sync_state(vault_dir, state)
    print(f"✅ [Instapaper] Ingested {imported} new atoms.")
    return imported


def pull_arena(vault_dir: Path, limit: int = 25, visibility: str = "public"):
    """Pull recent blocks across all user channels from Are.na into WideWeb."""
    import curate

    creds = get_credentials(vault_dir)
    token = creds.get("arena_api_token")
    if not token:
        print("⚠️ Are.na API token not found. Skipping Are.na sync.")
        return 0

    print(f"\n📥 [Are.na] Checking user contents (limit={limit})...")
    url = f"https://api.are.na/v3/users/{ARENA_USER_ID}/contents?per={limit}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 WideWeb/1.0"
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

    conn = sqlite3.connect(vault_dir / "vault.db")
    state = get_sync_state(vault_dir)
    imported = 0

    arena_synced = set(state.setdefault("arena", {}).setdefault("synced_ids", []))

    for it in items:
        block_id = str(it.get("id")) if it.get("id") else None
        block_type = it.get("type")
        title = it.get("title") or "Are.na Block"
        desc_obj = it.get("description")
        notes = (desc_obj.get("plain") or desc_obj.get("markdown")) if isinstance(desc_obj, dict) else (desc_obj or None)

        source_url = it.get("source", {}).get("url") if isinstance(it.get("source"), dict) else None
        check_url = source_url or (f"https://www.are.na/block/{block_id}" if block_id else None)

        # Deduplication check
        if block_id and block_id in arena_synced:
            continue
        if check_url and url_exists_in_vault(conn, check_url):
            if block_id:
                state["arena"]["synced_ids"].append(block_id)
            continue

        try:
            if block_type in ("Link", "Embed") and source_url:
                print(f"   ✨ Ingesting Link: {title[:50]}... ({source_url[:40]}...)")
                args = types.SimpleNamespace(
                    url=source_url,
                    title=title,
                    notes=notes,
                    tags="are.na",
                    collection="Are.na",
                    image_url=it.get("image", {}).get("src") if isinstance(it.get("image"), dict) else None,
                    quote=None,
                    favorite=False,
                    vault=str(vault_dir),
                    visibility=visibility,
                    target_kind=None
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
                        tags="are.na",
                        collection="Are.na",
                        author=it.get("user", {}).get("name") if isinstance(it.get("user"), dict) else None,
                        source=source_url or f"https://www.are.na/block/{block_id}",
                        favorite=False,
                        vault=str(vault_dir),
                        visibility=visibility
                    )
                    curate.cmd_image(args)
                    imported += 1

            elif block_type == "Text":
                content_obj = it.get("content")
                text_content = (content_obj.get("plain") or content_obj.get("markdown")) if isinstance(content_obj, dict) else (content_obj or notes)
                if text_content:
                    print(f"   ✨ Ingesting Text: {title[:50]}...")
                    args = types.SimpleNamespace(
                        text=text_content,
                        title=title,
                        tags="are.na",
                        collection="Are.na",
                        favorite=False,
                        vault=str(vault_dir),
                        visibility=visibility
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


def pull_all(vault_dir: Path, service: str = "all", limit: int = 25, visibility: str = "public"):
    """Run inbound pull for Instapaper, Are.na, or both."""
    total = 0
    if service in ("all", "instapaper"):
        total += pull_instapaper(vault_dir, limit=limit, visibility=visibility)
    if service in ("all", "arena"):
        total += pull_arena(vault_dir, limit=limit, visibility=visibility)

    if total > 0:
        print(f"\n🎉 Total new atoms imported: {total}")
    else:
        print(f"\n⚡ Library is up to date (0 new items to import).")
    return total


if __name__ == "__main__":
    import sys
    project_root = Path(__file__).resolve().parent
    vault = project_root / "vault"
    service = sys.argv[1] if len(sys.argv) > 1 else "all"
    pull_all(vault, service=service)
