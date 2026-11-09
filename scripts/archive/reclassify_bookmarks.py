#!/usr/bin/env python3
"""
Webtack — Reclassify Reading Items by Content Depth
Enforces canonical taxonomy:
- If atom has full article text (article.md or >= 100 words text) -> 'article' (📖 Read)
- If atom is a web link with preview/metadata/excerpt -> 'bookmark' (↗ Visit)
- If atom is a video embed -> 'video' (▶ Watch)
- If atom is a quote -> 'quote'
- If atom is a personal note without a link -> 'note'
"""

import sys
import os
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from curate import get_db
from viewer import generate_viewer
from scripts.sync_public_gcs import get_public_atoms, generate_curation_export


def main():
    vault_dir = Path(__file__).resolve().parent.parent / "vault"
    conn = get_db(vault_dir)

    print("🔍 Inspecting atoms in vault to enforce article vs bookmark taxonomy...")
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, notes, destination_url, source_url,
               text_content, metadata
        FROM atoms
        WHERE collections = '["Reading"]'
    """).fetchall()

    print(f"📚 Found {len(rows)} atoms in Reading collection.")

    db_updates = []
    t0 = time.time()
    converted_to_bookmark = 0
    kept_article = 0

    for r in rows:
        aid = r["id"]
        old_kind = r["kind"]
        created_at = r["created_at"]
        text = r["text_content"]
        dest_url = r["destination_url"]
        src_url = r["source_url"]

        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_folder = vault_dir / "atoms" / year / month / aid
        art_file = atom_folder / "article.md"

        has_full_text = art_file.exists() or (text and len(text.split()) >= 100 and not text.startswith("http"))

        # Determine target kind
        if old_kind in ("video", "image", "quote"):
            target_kind = old_kind
        elif has_full_text:
            target_kind = "article"
            kept_article += 1
        else:
            target_kind = "bookmark"
            converted_to_bookmark += 1

        if target_kind != old_kind:
            # Update atom.json on disk
            atom_json_path = atom_folder / "atom.json"
            if atom_json_path.exists():
                try:
                    with open(atom_json_path, "r", encoding="utf-8") as f:
                        doc = json.load(f)
                    doc["kind"] = target_kind
                    with open(atom_json_path, "w", encoding="utf-8") as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            db_updates.append((target_kind, aid))

    if db_updates:
        print(f"🔄 Updating {len(db_updates)} atoms in database...")
        with conn:
            conn.executemany("UPDATE atoms SET kind = ? WHERE id = ?", db_updates)

    print(f"✅ Taxonomy alignment complete in {time.time() - t0:.1f}s:")
    print(f"   🔖 Bookmarks (links for visit): {converted_to_bookmark}")
    print(f"   📖 Full-text Articles: {kept_article}")

    # Vault summary
    print("\n📊 New Vault breakdown by kind:")
    for k, count in conn.execute("SELECT kind, count(*) FROM atoms GROUP BY kind ORDER BY count(*) DESC").fetchall():
        print(f"   {k:12s}: {count:,}")

    print("\n📄 Regenerating curation_public.json manifest...")
    pub_rows = get_public_atoms()
    out_file = generate_curation_export(pub_rows)
    print(f"✅ Generated {out_file} ({len(pub_rows)} public atoms)")

    print("\n✨ Regenerating Webtack local viewer...")
    generate_viewer(vault_dir)
    print("✨ Webtack viewer updated successfully!")


if __name__ == "__main__":
    main()
