#!/usr/bin/env python3
"""
WebTack — Update Image Source URLs from Description / Notes

Extracts web URLs present in image atom notes (e.g., 'Via https://...')
and updates:
1. SQLite database atoms table: source_url, destination_url, raw_json, updated_at
2. On-disk atom.json: provenance.source_url, payload.destination_url, updated_at
3. Regenerates public export (curation_public.json) and viewer (index.html / export.html)
"""

import sys
import re
import json
import html
import sqlite3
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curate import get_db
from viewer import generate_viewer
from scripts.sync_public_gcs import get_public_atoms, generate_curation_export

URL_REGEX = re.compile(r"https?://[^\s<>\"'()\[\]]+")


def extract_primary_url(text: str) -> str | None:
    if not text:
        return None
    matches = URL_REGEX.findall(text)
    for m in matches:
        cleaned = re.sub(r"[\.,;:!?]+$", "", m)
        cleaned = html.unescape(cleaned)
        try:
            parsed = urlparse(cleaned)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return cleaned
        except Exception:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Update image source URLs from description/notes.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect candidates without applying changes.")
    parser.add_argument("--id", type=str, help="Only update a single atom ID (e.g., atm_20261104203623_152d6d)")
    args = parser.parse_args()

    vault_dir = Path(__file__).resolve().parent.parent / "vault"
    conn = get_db(vault_dir)

    query = """
        SELECT id, kind, created_at, updated_at, atom_title, notes,
               source_url, destination_url, raw_json
        FROM atoms
        WHERE kind = 'image'
    """
    params = []
    if args.id:
        query += " AND id = ?"
        params.append(args.id)
    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    print(f"🔍 Scanned {len(rows)} image atoms...")

    updates = []
    for r in rows:
        aid = r["id"]
        notes = r["notes"] or ""
        ext_url = extract_primary_url(notes)
        if not ext_url:
            continue

        curr_src = r["source_url"]
        curr_dest = r["destination_url"]

        # Check if update is needed
        if curr_src == ext_url and curr_dest == ext_url:
            continue

        updates.append({
            "id": aid,
            "title": r["atom_title"],
            "created_at": r["created_at"],
            "notes": notes,
            "new_url": ext_url,
            "old_source": curr_src,
            "old_dest": curr_dest,
            "raw_json": r["raw_json"]
        })

    print(f"🎯 Found {len(updates)} image atoms to update with description URLs.")
    if not updates:
        print("Nothing to update.")
        return

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW (First 15 items) ---")
        for u in updates[:15]:
            print(f"[{u['id']}] {u['title']}")
            print(f"   Notes:      {u['notes'][:80]}...")
            print(f"   Old Source: {u['old_source']}")
            print(f"   New URL:    {u['new_url']}")
        print(f"\nDry run complete. Run without --dry-run to apply {len(updates)} changes.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    db_updates = []
    disk_success = 0

    for u in updates:
        aid = u["id"]
        new_url = u["new_url"]
        created_at = u["created_at"] or now_iso

        # Locate atom.json on disk
        year = created_at[:4] if len(created_at) >= 4 else "2026"
        month = created_at[5:7] if len(created_at) >= 7 else "11"
        atom_folder = vault_dir / "atoms" / year / month / aid
        atom_json_path = atom_folder / "atom.json"

        # Load existing JSON or fall back to DB raw_json
        doc = None
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception as e:
                print(f"⚠️ Could not read {atom_json_path}: {e}")

        if not doc and u["raw_json"]:
            try:
                doc = json.loads(u["raw_json"])
            except Exception:
                pass

        if doc:
            if "provenance" not in doc:
                doc["provenance"] = {}
            doc["provenance"]["source_url"] = new_url
            if "payload" not in doc:
                doc["payload"] = {}
            doc["payload"]["destination_url"] = new_url
            doc["updated_at"] = now_iso

            if atom_json_path.exists():
                try:
                    with open(atom_json_path, "w", encoding="utf-8") as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
                    disk_success += 1
                except Exception as e:
                    print(f"⚠️ Failed to write {atom_json_path}: {e}")

            new_raw_json = json.dumps(doc, ensure_ascii=False)
        else:
            new_raw_json = u["raw_json"]

        db_updates.append((new_url, new_url, now_iso, new_raw_json, aid))

    # Commit database changes in a transaction
    with conn:
        conn.executemany("""
            UPDATE atoms
            SET source_url = ?,
                destination_url = ?,
                updated_at = ?,
                raw_json = ?
            WHERE id = ?
        """, db_updates)

    print(f"✅ Successfully updated {len(db_updates)} database records and {disk_success} atom.json files.")

    # Refresh curation_public.json and viewer HTML
    print("\n📄 Regenerating curation_public.json export...")
    pub_rows = get_public_atoms()
    out_file = generate_curation_export(pub_rows)
    print(f"✅ Generated {out_file}")

    print("\n✨ Regenerating WebTack viewer (index.html / export.html)...")
    generate_viewer(vault_dir)
    print("✨ WebTack viewer updated successfully!")


if __name__ == "__main__":
    main()
