#!/usr/bin/env python3
"""
WebTack — Reliable Sequential Dump for Are.na Reading Channel (10,243 blocks)
Fetches all pages sequentially using the Are.na v2 API with incremental
per-page checkpointing and retry backoff.
"""

import sys
import os
import json
import time
import requests
from pathlib import Path

CHANNEL_ID = "4965281"
PER_PAGE = 100
DELAY_BETWEEN_PAGES = 0.25
VAULT_DIR = Path(__file__).resolve().parent.parent / "vault"
IMPORT_DIR = VAULT_DIR / "import"
CHECKPOINT_FILE = IMPORT_DIR / "arena_reading_checkpoint.json"
FINAL_DUMP_FILE = IMPORT_DIR / "arena_reading.json"


def get_arena_token() -> str:
    token = os.environ.get("ARENA_TOKEN") or os.environ.get("ARENA_API_TOKEN")
    if token:
        return token
    mcp_path = Path.home() / ".gemini/antigravity/mcp_config.json"
    if mcp_path.exists():
        try:
            with open(mcp_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            auth_header = cfg.get("mcpServers", {}).get("arena", {}).get("headers", {}).get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header.split("Bearer ")[-1].strip()
        except Exception:
            pass
    raise RuntimeError("Could not find Are.na token in environment or mcp_config.json")


def fetch_page_with_retry(page: int, token: str, retries: int = 5) -> list:
    url = f"https://api.are.na/v2/channels/{CHANNEL_ID}/contents?per={PER_PAGE}&page={page}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "WebTack/1.0"
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=(5.0, 25.0))
            if resp.status_code == 200:
                data = resp.json()
                return data.get("contents", [])
            elif resp.status_code == 429:
                wait = attempt * 4.0
                print(f"⚠️ Page {page} rate-limited (429), waiting {wait:.1f}s...")
                time.sleep(wait)
            elif resp.status_code in (500, 502, 503, 504, 408):
                wait = attempt * 2.5
                print(f"⚠️ Page {page} server error ({resp.status_code}), attempt {attempt}/{retries}, waiting {wait:.1f}s...")
                time.sleep(wait)
            else:
                print(f"❌ Page {page} returned unexpected status {resp.status_code}")
                return []
        except Exception as e:
            wait = attempt * 2.5
            print(f"⚠️ Page {page} connection error: {e}, attempt {attempt}/{retries}, waiting {wait:.1f}s...")
            time.sleep(wait)

    print(f"❌ Failed to fetch page {page} after {retries} retries.")
    return []


def main():
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = get_arena_token()

    # Step 1: Check total blocks from channel metadata
    ch_url = f"https://api.are.na/v2/channels/{CHANNEL_ID}?per=1"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "WebTack/1.0"}
    resp = requests.get(ch_url, headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch channel details: HTTP {resp.status_code}")
        sys.exit(1)

    ch_info = resp.json()
    channel_title = ch_info.get("title", "Reading")
    total_items = ch_info.get("length") or ch_info.get("counts", {}).get("contents", 10243)
    total_pages = (total_items + PER_PAGE - 1) // PER_PAGE

    print(f"📚 Channel: '{channel_title}' ({total_items} items across {total_pages} pages)")

    # Step 2: Load checkpoint
    pages_data = {}
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                pages_data = json.load(f)
            print(f"📂 Resuming from checkpoint: {len(pages_data)} / {total_pages} pages already fetched.")
        except Exception as e:
            print(f"⚠️ Could not load checkpoint ({e}), starting fresh.")
            pages_data = {}

    missing_pages = [p for p in range(1, total_pages + 1) if str(p) not in pages_data]
    print(f"⚡ Pages remaining to fetch: {len(missing_pages)} / {total_pages}")

    if missing_pages:
        t0 = time.time()
        for i, page in enumerate(missing_pages, 1):
            p_start = time.time()
            blocks = fetch_page_with_retry(page, token)
            pages_data[str(page)] = blocks

            # Write checkpoint after each page
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(pages_data, f)

            elapsed = time.time() - t0
            pages_fetched = i
            speed = pages_fetched / elapsed if elapsed > 0 else 0
            rem_pages = len(missing_pages) - pages_fetched
            eta = rem_pages / speed if speed > 0 else 0
            p_dur = time.time() - p_start

            print(f"[{len(pages_data)}/{total_pages}] Page {page:3d} fetched ({len(blocks):3d} blocks in {p_dur:.2f}s) | Speed: {speed:.2f} p/s | ETA: {eta:.0f}s")
            time.sleep(DELAY_BETWEEN_PAGES)

        print(f"\n🎉 All {total_pages} pages downloaded successfully!")

    # Step 3: Combine all pages in order
    all_blocks = []
    seen_ids = set()
    for p in range(1, total_pages + 1):
        p_blocks = pages_data.get(str(p), [])
        for b in p_blocks:
            bid = b.get("id")
            if bid and bid in seen_ids:
                continue
            if bid:
                seen_ids.add(bid)
            all_blocks.append(b)

    print(f"📦 Assembled {len(all_blocks)} unique blocks from {len(pages_data)} pages.")

    # Step 4: Write final dump file
    dump_payload = {
        "channel_id": CHANNEL_ID,
        "title": channel_title,
        "total_blocks": len(all_blocks),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": all_blocks
    }

    with open(FINAL_DUMP_FILE, "w", encoding="utf-8") as f:
        json.dump(dump_payload, f, indent=2, ensure_ascii=False)

    print(f"💾 Saved full dump to: {FINAL_DUMP_FILE}")

    # Step 5: Clean up checkpoint
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("🧹 Cleaned up temporary checkpoint file.")


if __name__ == "__main__":
    main()
