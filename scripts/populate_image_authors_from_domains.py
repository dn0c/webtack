#!/usr/bin/env python3
"""
WideWeb — Populate Missing Image Authors from Source URL Domains

Finds image atoms that are missing an Author / Creator attribution, extracts
the domain from the Source URL (or destination URL), maps it to a clean brand/site name
(e.g., 'hypebeast.com' -> 'Hypebeast'), and updates:
1. SQLite database atoms table: author, raw_json, updated_at
2. On-disk atom.json: provenance.author, provenance.site_name (if null), updated_at
3. Regenerates public export (curation_public.json) and viewer (index.html / export.html)
"""

import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from curate import (
    get_db,
    get_public_atoms,
    generate_curation_export,
    extract_author_from_url
)
from viewer import generate_viewer


def main():
    parser = argparse.ArgumentParser(description="Populate missing image authors from source URL domains.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect candidates without applying changes.")
    parser.add_argument("--id", type=str, help="Only update a single atom ID (e.g., atm_20261104203608_8906d0)")
    args = parser.parse_args()

    vault_dir = PROJECT_ROOT / "vault"
    conn = get_db(vault_dir)

    query = """
        SELECT id, kind, created_at, updated_at, atom_title, author,
               source_url, destination_url, raw_json
        FROM atoms
        WHERE kind = 'image' AND (author IS NULL OR trim(author) = '')
    """
    params = []
    if args.id:
        query += " AND id = ?"
        params.append(args.id)
    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    print(f"🔍 Scanned {len(rows)} image atoms missing an author...")

    updates = []
    for r in rows:
        aid = r["id"]
        source_url = r["source_url"] or r["destination_url"]
        if not source_url or not source_url.strip():
            continue

        extracted_author = extract_author_from_url(source_url)
        if not extracted_author:
            continue

        updates.append({
            "id": aid,
            "title": r["atom_title"],
            "created_at": r["created_at"],
            "source_url": source_url,
            "new_author": extracted_author,
            "raw_json": r["raw_json"]
        })

    print(f"🎯 Found {len(updates)} image atoms to populate with author / creator.")
    if not updates:
        print("Nothing to update.")
        return

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW (First 25 items) ---")
        for u in updates[:25]:
            print(f"[{u['id']}] {u['title'][:40]}")
            print(f"   Source URL: {u['source_url'][:60]}")
            print(f"   New Author: {u['new_author']}")
        print(f"\nDry run complete. Run without --dry-run to apply {len(updates)} changes.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    db_updates = []
    disk_success = 0

    for u in updates:
        aid = u["id"]
        new_author = u["new_author"]
        created_at = u["created_at"] or now_iso

        # Locate atom.json on disk
        year = created_at[:4] if len(created_at) >= 4 else "2026"
        month = created_at[5:7] if len(created_at) >= 7 else "11"
        atom_folder = vault_dir / "atoms" / year / month / aid
        atom_json_path = atom_folder / "atom.json"

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
            doc["provenance"]["author"] = new_author
            if not doc["provenance"].get("site_name"):
                doc["provenance"]["site_name"] = new_author
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

        db_updates.append((new_author, now_iso, new_raw_json, aid))

    with conn:
        conn.executemany("""
            UPDATE atoms
            SET author = ?,
                updated_at = ?,
                raw_json = ?
            WHERE id = ?
        """, db_updates)

    print(f"✅ Successfully updated {len(db_updates)} database records and {disk_success} atom.json files.")

    # Refresh curation_public.json and viewer HTML
    print("\n📄 Regenerating curation_public.json export...")
    pub_rows = get_public_atoms(vault_dir)
    out_file = generate_curation_export(vault_dir, pub_rows)
    print(f"✅ Generated {out_file}")

    print("\n✨ Regenerating WideWeb viewer (index.html / export.html)...")
    generate_viewer(vault_dir)
    print("✨ WideWeb viewer updated successfully!")


if __name__ == "__main__":
    main()
