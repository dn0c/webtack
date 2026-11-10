#!/usr/bin/env python3
"""
WebTack — Flag & Enrich Reading Collection as Articles
Converts all bookmark and note atoms from the Reading collection into first-class
Article atoms with excerpts, word counts, reading time estimates, and updated atom.json documents.
"""

import sys
import os
import json
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curate import get_db
from viewer import generate_viewer
from scripts.sync_public_gcs import get_public_atoms, generate_curation_export


def main():
    vault_dir = Path(__file__).resolve().parent.parent / "vault"
    conn = get_db(vault_dir)

    print("🔍 Fetching Reading collection atoms flagged as bookmark or note...")
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, notes, destination_url, source_url,
               text_content, author, metadata, raw_json
        FROM atoms
        WHERE collections = '["Reading"]' AND kind IN ('bookmark', 'note')
    """).fetchall()

    print(f"📚 Found {len(rows)} atoms to convert to 'article'...")

    if not rows:
        print("✅ No atoms to update!")
        return

    BATCH_SIZE = 200
    updated_count = 0
    t0 = time.time()

    # Process in batches
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        db_updates = []

        for r in chunk:
            aid = r["id"]
            title = r["atom_title"]
            notes = r["notes"]
            dest_url = r["destination_url"]
            src_url = r["source_url"]
            text = r["text_content"]
            author = r["author"]
            created_at = r["created_at"]

            # Resolve canonical URL
            canon_url = dest_url or src_url
            if not canon_url and text and text.startswith("http"):
                canon_url = text.strip()

            # Resolve excerpt / text content
            excerpt = None
            if notes and notes.strip():
                excerpt = notes.strip()
            elif text and not text.startswith("http"):
                excerpt = text.strip()

            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            site_name = meta.get("site_name")
            if not site_name and canon_url:
                try:
                    site_name = urlparse(canon_url).netloc
                except Exception:
                    pass

            words = len(excerpt.split()) if excerpt else 0
            read_time = max(1, round(words / 200)) if words > 0 else None

            meta["site_name"] = site_name
            meta["word_count"] = words
            meta["reading_time_minutes"] = read_time
            meta["is_article"] = True

            # Update atom.json on disk
            try:
                # Resolve atom folder using created_at timestamp
                year = created_at[:4] if created_at else "2026"
                month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
                atom_json_path = vault_dir / "atoms" / year / month / aid / "atom.json"
                if atom_json_path.exists():
                    with open(atom_json_path, "r", encoding="utf-8") as f:
                        doc = json.load(f)
                    doc["kind"] = "article"
                    if not doc.get("provenance"):
                        doc["provenance"] = {}
                    if canon_url:
                        doc["provenance"]["canonical_url"] = canon_url
                        doc["provenance"]["source_url"] = canon_url
                    if site_name:
                        doc["provenance"]["site_name"] = site_name

                    if not doc.get("payload"):
                        doc["payload"] = {}
                    doc["payload"]["destination_url"] = canon_url
                    doc["payload"]["text"] = excerpt
                    doc["payload"]["article"] = {
                        "byline": author,
                        "excerpt": excerpt,
                        "word_count": words,
                        "estimated_reading_time_min": read_time
                    }

                    with open(atom_json_path, "w", encoding="utf-8") as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
            except Exception as e:
                pass

            meta_json = json.dumps(meta)
            db_updates.append((
                "article",
                canon_url,
                canon_url,
                excerpt,
                meta_json,
                aid
            ))

        with conn:
            conn.executemany("""
                UPDATE atoms
                SET kind = ?,
                    destination_url = ?,
                    source_url = ?,
                    text_content = ?,
                    metadata = ?
                WHERE id = ?
            """, db_updates)

        updated_count += len(chunk)
        elapsed = time.time() - t0
        speed = updated_count / elapsed if elapsed > 0 else 0
        print(f"[{updated_count}/{len(rows)}] Converted {len(chunk)} atoms | Speed: {speed:.1f} atoms/s")

    print(f"\n🎉 Successfully flagged & enriched {updated_count} atoms as articles in {time.time() - t0:.1f}s!")

    print("\n📄 Regenerating curation_public.json manifest...")
    pub_rows = get_public_atoms()
    out_file = generate_curation_export(pub_rows)
    print(f"✅ Generated {out_file} ({len(pub_rows)} public atoms)")

    print("\n✨ Regenerating WebTack local viewer...")
    generate_viewer(vault_dir)
    print("✨ WebTack viewer updated successfully!")


if __name__ == "__main__":
    main()
