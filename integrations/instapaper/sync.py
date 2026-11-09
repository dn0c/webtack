#!/usr/bin/env python3
"""
Webtack — Instapaper Inbound Sync Integration
Pulls newly bookmarked items from Instapaper (unread) into Webtack atoms with full readability text.
"""

import os
import sys
import json
import sqlite3
import types
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import curate


def get_instapaper_token(vault_dir: Path = None) -> str | None:
    token = os.environ.get("INSTAPAPER_ACCESS_TOKEN")
    if token:
        return token
    if vault_dir:
        cred_file = vault_dir / ".sync_credentials.json"
        if cred_file.exists():
            try:
                with open(cred_file, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    return c.get("instapaper_access_token")
            except Exception:
                pass
    mcp_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    if mcp_path.exists():
        try:
            with open(mcp_path, "r", encoding="utf-8") as f:
                mcp = json.load(f).get("mcpServers", {})
                return mcp.get("instapaper", {}).get("env", {}).get("INSTAPAPER_ACCESS_TOKEN")
        except Exception:
            pass
    return None


def get_sync_state(vault_dir: Path) -> dict:
    state_file = vault_dir / ".sync_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"instapaper": {}}


def save_sync_state(vault_dir: Path, state: dict):
    state_file = vault_dir / ".sync_state.json"
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving sync state: {e}")


def sync_instapaper(vault_dir: Path, limit: int = 25, visibility: str = "public") -> int:
    vault_dir = Path(vault_dir).resolve()
    token = get_instapaper_token(vault_dir)
    if not token:
        print("❌ Instapaper access token not found. Please set INSTAPAPER_ACCESS_TOKEN in .env.")
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
    conn.row_factory = sqlite3.Row
    state = get_sync_state(vault_dir)
    instapaper_synced = set(state.setdefault("instapaper", {}).setdefault("synced_ids", []))
    imported = 0

    for b in bookmarks:
        bm_url = b.get("url")
        bm_id = str(b.get("id")) if b.get("id") else None
        if not bm_url:
            continue

        if bm_id and bm_id in instapaper_synced:
            continue

        title = b.get("title") or "Untitled Bookmark"
        desc = b.get("description") or None

        # Fetch parsed full text directly from Instapaper API if available
        article_md = None
        article_wc = 0
        if bm_id:
            try:
                parse_url = f"https://www.instapaper.com/api/2/bookmarks/{bm_id}/parse"
                p_resp = requests.get(parse_url, headers=headers, timeout=20)
                if p_resp.status_code == 200:
                    p_data = p_resp.json()
                    c_body = p_data.get("content", {}).get("body") if isinstance(p_data.get("content"), dict) else p_data.get("content")
                    if c_body:
                        from scripts.backfill_instapaper_fulltext import html_to_clean_markdown
                        article_md, article_wc = html_to_clean_markdown(c_body, url=bm_url)
            except Exception:
                pass

        print(f"   ✨ Ingesting: {title[:50]}... ({bm_url[:40]}...)")
        target_kind = "article" if article_md and article_wc >= 80 else None
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
            target_kind=target_kind,
            capture_method="instapaper",
            capture_id=str(bm_id) if bm_id else None,
            capture_url=f"https://www.instapaper.com/read/{bm_id}" if bm_id else None
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync unread Instapaper bookmarks into Webtack")
    parser.add_argument("--vault", default="vault", help="Path to vault directory (default: vault)")
    parser.add_argument("--limit", type=int, default=25, help="Max items to fetch (default: 25)")
    parser.add_argument("--visibility", choices=["public", "shared", "private"], default="public", help="Visibility tier")
    args = parser.parse_args()

    sync_instapaper(Path(args.vault), limit=args.limit, visibility=args.visibility)
