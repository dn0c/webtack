#!/usr/bin/env python3
"""
WideWeb — Are.na Alt Text Synchronizer & Generator

1. Pulls existing rich alt text from Are.na into local WideWeb atoms (atom.json & SQLite).
2. Identifies blocks that need newly generated alt text.
3. Generates alt text using vision model (Gemini Flash / OpenAI).
4. Pushes newly generated alt text up to the corresponding Are.na blocks.
"""

import sys
import json
import sqlite3
import argparse
from datetime import datetime, timezone
from pathlib import Path

vault_dir = Path(__file__).resolve().parent.parent / "vault"
cache_file = vault_dir / ".arena_scan_cache.json"

def apply_arena_alt_to_atoms():
    if not cache_file.exists():
        print("❌ Cache file vault/.arena_scan_cache.json not found! Run scan first.")
        sys.exit(1)

    with open(cache_file, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    rich_map = {x["aid"]: (x["alt"], x["cpath"]) for x in cache_data if x.get("is_rich")}
    print(f"📦 Loaded {len(rich_map)} rich alt text entries from Are.na scan.")

    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, raw_json FROM atoms WHERE kind = 'image'")
    rows = c.fetchall()

    now_iso = datetime.now(timezone.utc).isoformat()
    disk_updates = 0
    db_updates = []

    for r in rows:
        aid = r["id"]
        if aid not in rich_map:
            continue

        rich_alt, cpath = rich_map[aid]
        raw = r["raw_json"]
        doc = json.loads(raw)
        cover_img = doc.get("payload", {}).get("cover_image", {})
        curr_alt = cover_img.get("alt_text")

        if curr_alt == rich_alt:
            continue

        # Update document
        cover_img["alt_text"] = rich_alt
        doc["payload"]["cover_image"] = cover_img
        doc["updated_at"] = now_iso

        # Write to disk
        atom_json_path = (vault_dir / cpath).parent / "atom.json"
        try:
            with open(atom_json_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            disk_updates += 1
        except Exception as e:
            print(f"⚠️ Failed to write {atom_json_path}: {e}")

        new_raw_json = json.dumps(doc, ensure_ascii=False)
        db_updates.append((now_iso, new_raw_json, aid))

    if db_updates:
        with conn:
            conn.executemany("""
                UPDATE atoms
                SET updated_at = ?,
                    raw_json = ?
                WHERE id = ?
            """, db_updates)

    print(f"✅ Successfully updated {len(db_updates)} WideWeb atoms in SQLite and {disk_updates} atom.json files on disk with Are.na rich alt text!")

if __name__ == "__main__":
    apply_arena_alt_to_atoms()
