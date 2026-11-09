#!/usr/bin/env python3
"""
Webtack — Are.na Alt Text Synchronizer
Pushes rich accessibility alt text generated in Webtack back up to corresponding Are.na blocks.
"""

import os
import sys
import json
import re
import sqlite3
import requests
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.arena.sync import get_arena_token


def push_arena_alt_text(block_id: str, alt_text: str, token: str) -> tuple[bool, str]:
    """Update block description / alt text on Are.na API."""
    if not block_id or not alt_text or not token:
        return False, "Missing block_id, alt_text, or token"

    url = f"https://api.are.na/v3/blocks/{block_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 Webtack/1.0"
    }
    payload = {"description": alt_text}

    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return True, "Updated successfully"
        elif r.status_code == 403:
            return False, "You do not own this Are.na block"
        else:
            return False, f"HTTP {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, str(e)


def extract_arena_block_id(source_url: str = None, doc: dict = None) -> str | None:
    if source_url:
        m = re.search(r"are\.na/block/(\d+)", source_url)
        if m:
            return m.group(1)
        m_api = re.search(r"api\.are\.na/v3/blocks/(\d+)", source_url)
        if m_api:
            return m_api.group(1)

    if doc:
        meta = doc.get("metadata_json") or {}
        if isinstance(meta, dict) and meta.get("arena_block_id"):
            return str(meta["arena_block_id"])
        prov_src = (doc.get("source") or doc.get("provenance") or {}).get("source_url")
        if prov_src:
            m = re.search(r"are\.na/block/(\d+)", prov_src)
            if m:
                return m.group(1)
        cap_id = (doc.get("source") or {}).get("capture_id")
        if cap_id and (doc.get("source") or {}).get("capture_method") == "arena":
            return str(cap_id)

    return None


def push_all_alt_texts(vault_dir: Path, limit: int = None) -> int:
    vault_dir = Path(vault_dir).resolve()
    token = get_arena_token(vault_dir)
    if not token:
        print("❌ Are.na API token not found. Set ARENA_API_TOKEN in .env.")
        return 0

    conn = sqlite3.connect(vault_dir / "vault.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, raw_json FROM atoms WHERE kind = 'image'")
    rows = c.fetchall()

    synced = 0
    for r in rows:
        doc = json.loads(r["raw_json"])
        bid = extract_arena_block_id(doc=doc)
        if not bid:
            continue

        cover_img = (doc.get("content") or doc.get("payload") or {}).get("cover_image", {})
        alt = cover_img.get("alt_text")
        if not alt or len(alt) < 15:
            continue

        ok, msg = push_arena_alt_text(bid, alt, token)
        if ok:
            print(f"✅ Synced alt text to Are.na block {bid} (atom {r['id']})")
            synced += 1
        elif "do not own" not in msg:
            print(f"⚠️ Could not sync block {bid}: {msg}")

        if limit and synced >= limit:
            break

    conn.close()
    print(f"\n✨ Synced {synced} alt text descriptions to Are.na blocks.")
    return synced


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Push Webtack image alt text to Are.na blocks")
    parser.add_argument("--vault", default="vault", help="Path to Webtack vault (default: vault)")
    parser.add_argument("--limit", type=int, default=None, help="Max blocks to sync")
    args = parser.parse_args()

    push_all_alt_texts(Path(args.vault), limit=args.limit)
