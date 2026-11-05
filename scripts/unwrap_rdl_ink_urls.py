#!/usr/bin/env python3
"""
WideWeb — Unwrap rdl.ink URLs

Unwraps Raindrop.io render proxy URLs (https://rdl.ink/render/<encoded_url>)
across:
1. SQLite database: destination_url, source_url, raw_json, updated_at
2. On-disk atom.json: payload.destination_url, provenance.source_url,
   provenance.canonical_url, provenance.site_name, updated_at
3. On-disk note.md if text content contains rdl.ink
4. Regenerates curation_public.json and viewer (index.html / export.html)
"""

import sys
import re
import json
import sqlite3
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curate import get_db
from viewer import generate_viewer
from scripts.sync_public_gcs import get_public_atoms, generate_curation_export


def clean_rdl_url(url: str | None) -> str | None:
    if not url or "rdl.ink" not in url or "/render/" not in url:
        return url
    encoded = url.split("/render/", 1)[1]
    return unquote(encoded)


def main():
    parser = argparse.ArgumentParser(description="Unwrap rdl.ink proxy URLs to original destinations.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect candidates without applying changes.")
    args = parser.parse_args()

    vault_dir = Path(__file__).resolve().parent.parent / "vault"
    conn = get_db(vault_dir)

    rows = conn.execute("""
        SELECT id, kind, created_at, updated_at, atom_title, notes,
               destination_url, source_url, raw_json, text_content
        FROM atoms
        WHERE destination_url LIKE '%rdl.ink%'
           OR source_url LIKE '%rdl.ink%'
           OR raw_json LIKE '%rdl.ink%'
        ORDER BY created_at DESC
    """).fetchall()

    print(f"🔍 Found {len(rows)} candidate atoms with rdl.ink references...")

    updates = []
    for r in rows:
        aid = r["id"]
        created_at = r["created_at"]
        dest = r["destination_url"]
        src = r["source_url"]
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}

        new_dest = clean_rdl_url(dest)
        new_src = clean_rdl_url(src)

        # In case raw_json had it while DB didn't (e.g. note atom)
        if not new_dest and raw.get("payload", {}).get("destination_url"):
            new_dest = clean_rdl_url(raw["payload"]["destination_url"])
        if not new_src and raw.get("provenance", {}).get("source_url"):
            new_src = clean_rdl_url(raw["provenance"]["source_url"])

        # Determine target primary URL
        target_url = new_dest or new_src

        # If it's a note with rdl.ink in text_content
        text_content = r["text_content"]
        new_text_content = text_content
        if text_content and "rdl.ink" in text_content and "/render/" in text_content:
            new_text_content = re.sub(
                r"https?://rdl\.ink/render/([^\s<>\"'()\[\]]+)",
                lambda m: unquote(m.group(1)),
                text_content
            )
            if not target_url:
                target_url = new_text_content.strip()
                new_dest = target_url
                new_src = target_url

        domain = None
        if target_url:
            try:
                parsed = urlparse(target_url)
                if parsed.netloc:
                    domain = parsed.netloc.lower().replace("www.", "")
            except Exception:
                pass

        updates.append({
            "id": aid,
            "kind": r["kind"],
            "title": r["atom_title"],
            "created_at": created_at,
            "old_dest": dest,
            "new_dest": new_dest,
            "old_src": src,
            "new_src": new_src,
            "domain": domain,
            "raw": raw,
            "text_content": new_text_content
        })

    if not updates:
        print("No atoms to update.")
        return

    print(f"🎯 Total atoms to unwrap: {len(updates)}")

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW (First 15 items) ---")
        for u in updates[:15]:
            print(f"[{u['kind']}] {u['id']} - {u['title']}")
            print(f"   Old: {u['old_dest'] or u['old_src']}")
            print(f"   New: {u['new_dest'] or u['new_src']}")
            print(f"   Domain: {u['domain']}")
        print(f"\nDry run complete. Run without --dry-run to apply {len(updates)} changes.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    db_updates = []
    disk_success = 0

    for u in updates:
        aid = u["id"]
        created_at = u["created_at"] or now_iso
        doc = u["raw"]

        year = created_at[:4] if len(created_at) >= 4 else "2026"
        month = created_at[5:7] if len(created_at) >= 7 else "11"
        atom_folder = vault_dir / "atoms" / year / month / aid
        atom_json_path = atom_folder / "atom.json"

        # Check for note.md update
        note_path = atom_folder / "note.md"
        if note_path.exists() and u["text_content"]:
            try:
                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(u["text_content"])
            except Exception as e:
                print(f"⚠️ Could not write {note_path}: {e}")

        # Update atom_doc dictionary
        if doc:
            if "provenance" not in doc:
                doc["provenance"] = {}
            if u["new_src"]:
                doc["provenance"]["source_url"] = u["new_src"]
            if doc["provenance"].get("canonical_url") and "rdl.ink" in doc["provenance"]["canonical_url"]:
                doc["provenance"]["canonical_url"] = clean_rdl_url(doc["provenance"]["canonical_url"])
            if doc["provenance"].get("site_name") in ("rdl.ink", None) and u["domain"]:
                doc["provenance"]["site_name"] = u["domain"]
            if doc["provenance"].get("source_title") == "rdl.ink" and u["domain"]:
                doc["provenance"]["source_title"] = u["domain"]

            if "payload" not in doc:
                doc["payload"] = {}
            if u["new_dest"]:
                doc["payload"]["destination_url"] = u["new_dest"]

            # Check cover alt text
            cover_img = doc["payload"].get("cover_image")
            if cover_img and cover_img.get("alt_text") == "rdl.ink":
                cover_img["alt_text"] = u["title"]

            # Check text excerpt
            if doc["payload"].get("text") and doc["payload"]["text"].get("excerpt"):
                excerpt = doc["payload"]["text"]["excerpt"]
                if "rdl.ink" in excerpt and "/render/" in excerpt:
                    doc["payload"]["text"]["excerpt"] = clean_rdl_url(excerpt)

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
            new_raw_json = json.dumps({})

        db_updates.append((u["new_dest"], u["new_src"], u["text_content"], now_iso, new_raw_json, aid))

    # Commit DB updates
    with conn:
        conn.executemany("""
            UPDATE atoms
            SET destination_url = ?,
                source_url = ?,
                text_content = ?,
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

    print("\n✨ Regenerating WideWeb viewer (index.html / export.html)...")
    generate_viewer(vault_dir)
    print("✨ WideWeb viewer updated successfully!")


if __name__ == "__main__":
    main()
