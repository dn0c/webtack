#!/usr/bin/env python3
"""
WebTack — Batch Alt Text Applier
Applies generated alt text to atoms (atom.json & SQLite) and pushes to Are.na for owned blocks.
"""

import sys
import json
import sqlite3
import requests
from datetime import datetime, timezone
from pathlib import Path

vault_dir = Path(__file__).resolve().parent.parent / "vault"
token = "5rWBdFgiZ8e_UlNUGFRBs_0xFwMaD1AwM8PWO_reTeY"
headers = {"Authorization": f"Bearer {token}"}

def apply_batch(updates: dict[str, str]):
    """
    updates: dict mapping aid -> alt_text string
    """
    if not updates:
        return

    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    placeholders = ",".join("?" for _ in updates)
    c.execute(f"SELECT id, cover_file_path, raw_json FROM atoms WHERE id IN ({placeholders})", list(updates.keys()))
    rows = c.fetchall()

    now_iso = datetime.now(timezone.utc).isoformat()
    db_updates = []
    disk_updates = 0
    arena_updates = 0
    arena_skipped = 0

    cache_file = vault_dir / ".arena_scan_cache.json"
    bid_map = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                bid_map = {x["aid"]: x.get("bid") for x in cdata if x.get("bid")}
        except Exception:
            pass

    for r in rows:
        aid = r["id"]
        alt_text = updates[aid].strip()
        cpath = r["cover_file_path"]
        raw = r["raw_json"]
        doc = json.loads(raw)

        # Update atom JSON
        cover_img = doc.get("payload", {}).get("cover_image", {})
        cover_img["alt_text"] = alt_text
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

        # Check Are.na update
        bid = bid_map.get(aid)
        if bid:
            try:
                chk = requests.get(f"https://api.are.na/v3/blocks/{bid}", headers=headers, timeout=5)
                if chk.status_code == 200 and chk.json().get("can", {}).get("manage"):
                    # Update block
                    up = requests.put(f"https://api.are.na/v3/blocks/{bid}", headers=headers, json={"alt_text": alt_text}, timeout=5)
                    if up.status_code == 200:
                        arena_updates += 1
                    else:
                        print(f"⚠️ Are.na update returned {up.status_code} for block {bid}")
                else:
                    arena_skipped += 1
            except Exception as e:
                print(f"⚠️ Are.na error for block {bid}: {e}")

    if db_updates:
        with conn:
            conn.executemany("""
                UPDATE atoms
                SET updated_at = ?,
                    raw_json = ?
                WHERE id = ?
            """, db_updates)

    print(f"✅ Applied {len(db_updates)} updates (Disk: {disk_updates}, Are.na pushed: {arena_updates}, Are.na external skipped: {arena_skipped})")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Load from json file
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        apply_batch(data)
