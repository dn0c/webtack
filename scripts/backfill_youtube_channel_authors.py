#!/usr/bin/env python3
"""
WebTack — Backfill YouTube Channel Authors

Populates missing channel author attribution for YouTube video atoms using
the raw Are.na JSON dumps (embed.author_name) in vault/import/arena_*.json.
Also cleans up atoms where the author was erroneously set to "drew. shannon".

Updates:
1. SQLite database atoms table (author, updated_at, raw_json)
2. On-disk atom.json (source.author, updated_at)
3. Regenerates curation exports and WebTack viewer (index.html / export.html)
"""

import sys
import json
import glob
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, get_public_atoms, generate_curation_export
from viewer import generate_viewer

VAULT_DIR = REPO_ROOT / "vault"
IMPORT_DIR = VAULT_DIR / "import"


def extract_video_id(url: str) -> str | None:
    if not url:
        return None
    try:
        p = urlparse(url)
        netloc = p.netloc.lower()
        if "youtu.be" in netloc:
            return p.path.strip("/").split("/")[0].split("?")[0]
        if "youtube.com" in netloc:
            qs = parse_qs(p.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0]
            if "/shorts/" in p.path:
                return p.path.split("/shorts/")[1].split("/")[0].split("?")[0]
            if "/embed/" in p.path:
                return p.path.split("/embed/")[1].split("/")[0].split("?")[0]
    except Exception:
        pass
    return None


def build_channel_map():
    channel_map = {}
    for f in glob.glob(str(IMPORT_DIR / "arena_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
                items = d.get("data") if isinstance(d, dict) else d
                if isinstance(items, list):
                    for b in items:
                        u = (b.get("source") or {}).get("url") or (b.get("embed") or {}).get("source_url") or ""
                        vid = extract_video_id(u)
                        embed = b.get("embed") or {}
                        author_name = embed.get("author_name")
                        if vid and author_name and author_name.strip():
                            channel_map[vid] = author_name.strip()
        except Exception as e:
            print(f"⚠️ Warning reading {f}: {e}")
    return channel_map


def main():
    parser = argparse.ArgumentParser(description="Backfill YouTube channel names into source.author")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    print("🔍 Building YouTube channel index from raw Are.na imports...")
    channel_map = build_channel_map()
    print(f"✅ Indexed {len(channel_map)} YouTube video channels from raw imports.")

    conn = get_db(VAULT_DIR)
    rows = conn.execute("""
        SELECT id, atom_title, author, source_url, destination_url, created_at, raw_json
        FROM atoms
        WHERE source_url LIKE '%youtube.com%' OR source_url LIKE '%youtu.be%'
           OR destination_url LIKE '%youtube.com%' OR destination_url LIKE '%youtu.be%'
    """).fetchall()

    print(f"🔍 Found {len(rows)} YouTube video atoms in vault.db.")

    backfill_items = []
    clear_drew_items = []

    for r in rows:
        aid = r["id"]
        u = r["source_url"] or r["destination_url"]
        vid = extract_video_id(u)
        current_author = r["author"]
        raw_channel = channel_map.get(vid)

        if current_author and current_author.strip() == "drew. shannon":
            if raw_channel:
                backfill_items.append((r, raw_channel, "replaced drew. shannon"))
            else:
                clear_drew_items.append((r, None, "cleared drew. shannon"))
        elif not current_author or not current_author.strip():
            if raw_channel:
                backfill_items.append((r, raw_channel, "filled missing author"))

    print(f"🎯 Candidates to backfill with channel author: {len(backfill_items)}")
    print(f"🎯 Candidates to clear erroneous 'drew. shannon': {len(clear_drew_items)}")

    total_changes = len(backfill_items) + len(clear_drew_items)
    if total_changes == 0:
        print("Nothing to update.")
        return

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW: BACKFILL ---")
        for r, new_auth, reason in backfill_items[:10]:
            print(f"  [{r['id']}] {r['atom_title'][:40]} -> '{new_auth}' ({reason})")
        if len(backfill_items) > 10:
            print(f"  ... and {len(backfill_items) - 10} more.")

        print("\n--- DRY RUN PREVIEW: CLEAR DREW. SHANNON ---")
        for r, _, reason in clear_drew_items[:10]:
            print(f"  [{r['id']}] {r['atom_title'][:40]} -> None ({reason})")
        if len(clear_drew_items) > 10:
            print(f"  ... and {len(clear_drew_items) - 10} more.")

        print(f"\nDry run complete. Run without --dry-run to apply {total_changes} updates.")
        return

    # Backup vault.db
    db_path = VAULT_DIR / "vault.db"
    backup_path = VAULT_DIR / "vault.db.pre_yt_author_backfill.bak"
    shutil.copyfile(db_path, backup_path)
    print(f"💾 Backed up database to {backup_path.name}")

    now_iso = datetime.now(timezone.utc).isoformat()
    db_updates = []
    disk_updates = 0

    all_updates = backfill_items + clear_drew_items
    for r, new_author, _ in all_updates:
        aid = r["id"]
        created_at = r["created_at"] or now_iso

        # Locate atom.json on disk
        year = created_at[:4] if len(created_at) >= 4 else "2026"
        month = created_at[5:7] if len(created_at) >= 7 else "11"
        atom_folder = VAULT_DIR / "atoms" / year / month / aid
        atom_json_path = atom_folder / "atom.json"

        if not atom_json_path.exists():
            matches = list(VAULT_DIR.glob(f"atoms/*/*/{aid}/atom.json"))
            if matches:
                atom_json_path = matches[0]

        doc = None
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception as e:
                print(f"⚠️ Could not read {atom_json_path}: {e}")

        if not doc and r["raw_json"]:
            try:
                doc = json.loads(r["raw_json"])
            except Exception:
                pass

        if doc:
            if "source" in doc and isinstance(doc["source"], dict):
                doc["source"]["author"] = new_author
                if not doc["source"].get("site_name"):
                    doc["source"]["site_name"] = "YouTube"
            if "provenance" in doc and isinstance(doc["provenance"], dict):
                doc["provenance"]["author"] = new_author
            doc["updated_at"] = now_iso

            if atom_json_path.exists():
                try:
                    with open(atom_json_path, "w", encoding="utf-8") as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
                    disk_updates += 1
                except Exception as e:
                    print(f"⚠️ Failed to write {atom_json_path}: {e}")

            new_raw_json = json.dumps(doc, ensure_ascii=False)
        else:
            new_raw_json = r["raw_json"]

        db_updates.append((new_author, now_iso, new_raw_json, aid))

    with conn:
        conn.executemany("""
            UPDATE atoms
            SET author = ?,
                updated_at = ?,
                raw_json = ?
            WHERE id = ?
        """, db_updates)

    print(f"✅ Successfully updated {len(db_updates)} database records and {disk_updates} atom.json files.")

    # Refresh curation_public.json and viewer HTML
    print("\n📄 Regenerating curation_public.json export...")
    pub_rows = get_public_atoms(VAULT_DIR)
    out_file = generate_curation_export(VAULT_DIR, pub_rows)
    print(f"✅ Generated {out_file}")

    print("\n✨ Regenerating WebTack viewer (index.html / export.html)...")
    generate_viewer(VAULT_DIR)
    print("✨ WebTack viewer updated successfully!")


if __name__ == "__main__":
    main()
