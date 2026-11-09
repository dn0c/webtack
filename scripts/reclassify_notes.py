#!/usr/bin/env python3
"""
Webtack — Reclassify and Clean Up "Notes" Atoms
Converts misclassified text/link blocks imported into Webtack:
- 18 Atoms -> 'quote'
- 3 Atoms  -> 'bookmark'
- 2 Atoms  -> 'image'
- 4 Redundant duplicate atoms -> Merged and removed
- 10 Atoms -> Kept as genuine 'note'
"""

import os
import sys
import json
import shutil
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from curate import download_image
from viewer import generate_viewer
from scripts.sync_public_gcs import get_public_atoms, generate_curation_export

VAULT_DIR = BASE_DIR / "vault"
DB_PATH = VAULT_DIR / "vault.db"
SCHEMA_URL = "https://raw.githubusercontent.com/dn0c/webtack/main/schema/atom.schema.json"

# 1. Duplicates to merge into primary atoms and delete
DUPLICATES_TO_MERGE = {
    # duplicate_id: (primary_id, collections_to_add, tags_to_add)
    "atm_20261104195655_b120ab": ("atm_20261104194822_deb557", ["Work Inspo"], ["work-inspo"]),
    "atm_20261104195649_ff7255": ("atm_20261104194819_c5a604", ["Work Inspo"], ["work-inspo"]),
    "atm_20261104195655_a0e3a2": ("atm_20261104194822_6ce7e6", ["Work Inspo"], ["work-inspo"]),
    "atm_20261104195911_1b1807": ("atm_20261104200646_55113c", ["Decorate"], ["decorate-dkeha4pxrv0"]),
}

# 2. Quote atoms configuration
QUOTES_CONFIG = {
    "atm_20261104194822_deb557": {
        "title": "LLM Knowledge Bases",
        "author": "Andrej Karpathy",
        "source_url": "https://x.com/karpathy/status/2039805659525644595?s=20",
        "source_title": "Andrej Karpathy on LLM Knowledge Bases",
        "site_name": "x.com"
    },
    "atm_20261104194823_2b16c4": {
        "title": "The Dark Forest and Generative AI",
        "author": "Maggie Appleton",
        "source_url": "https://maggieappleton.com/ai-dark-forest",
        "source_title": "The Dark Forest and Generative AI",
        "site_name": "maggieappleton.com"
    },
    "atm_20261104194823_275de7": {
        "title": "The Dark Forest and Generative AI (Part 2)",
        "author": "Maggie Appleton",
        "source_url": "https://maggieappleton.com/ai-dark-forest",
        "source_title": "The Dark Forest and Generative AI",
        "site_name": "maggieappleton.com"
    },
    "atm_20261104194824_ff467a": {
        "title": "The Rise of \"No Code\"",
        "author": "Ryan Hoover",
        "source_url": "https://medium.com/@rrhoover/the-rise-of-no-code-e733d7c0944d",
        "source_title": "The Rise of \"No Code\" – Ryan Hoover – Medium",
        "site_name": "medium.com"
    },
    "atm_20261104195648_2b7198": {
        "title": "A blog post is a complex search query",
        "author": "Henrik Karlsson",
        "source_url": "https://www.henrikkarlsson.xyz/p/search-query",
        "source_title": "A blog post is a very long and complex search query to find fascinating people",
        "site_name": "henrikkarlsson.xyz"
    },
    "atm_20261104195648_5eb867": {
        "title": "A blog post is a complex search query (Part 2)",
        "author": "Henrik Karlsson",
        "source_url": "https://www.henrikkarlsson.xyz/p/search-query",
        "source_title": "A blog post is a very long and complex search query to find fascinating people",
        "site_name": "henrikkarlsson.xyz"
    },
    "atm_20261104194819_c5a604": {
        "title": "SOUL.MD — Build a Composable AI Agent Identity",
        "author": "SOUL.MD",
        "source_url": "https://www.soul-md.xyz/#quickstart",
        "source_title": "SOUL.MD — Build a Composable AI Agent Identity",
        "site_name": "soul-md.xyz"
    },
    "atm_20261104194823_5890d1": {
        "title": "AI Style Guides: How to Help AI Write Like You",
        "author": "Every",
        "source_url": "https://every.to/guides/ai-style-guide",
        "source_title": "AI Style Guides: How to Help AI Write Like You",
        "site_name": "every.to"
    },
    "atm_20261104194823_a25a79": {
        "title": "How to Enter Side Doors",
        "author": "Velvet Noise",
        "source_url": "https://velvetnoise.substack.com/p/how-to-enter-side-doors",
        "source_title": "how to enter side doors (via velvetnoise.substack.com)",
        "site_name": "velvetnoise.substack.com"
    },
    "atm_20261104194824_eada04": {
        "title": "Mat Dryhurst on Redesigning the System",
        "author": "Mat Dryhurst",
        "source_url": "https://thecreativeindependent.com/people/philosopher-and-digital-artist-mat-dryhurst-on-redesigning-the-system/",
        "source_title": "Philosopher and digital artist Mat Dryhurst on redesigning the system",
        "site_name": "thecreativeindependent.com"
    },
    "atm_20261104195607_454277": {
        "title": "[SIC] 390: Alter Roger",
        "author": "Ben Dietz",
        "source_url": "https://sic.substack.com/p/sic-390-alter-roger",
        "source_title": "[SIC] 390: Alter Roger - by Ben Dietz",
        "site_name": "sic.substack.com"
    },
    "atm_20261104195635_5e6f76": {
        "title": "Sports, Sound, and Greek Coffee: The World of Yorgo Tloupas",
        "author": "Yorgo Tloupas",
        "source_url": "https://www.freundevonfreunden.com/design/sports-sound-and-greek-coffee-the-world-of-yorgo-tloupas/",
        "source_title": "Sports, Sound, and Greek Coffee: The World of Yorgo Tloupas",
        "site_name": "freundevonfreunden.com"
    },
    "atm_20261104195637_6736ad": {
        "title": "Person → System",
        "author": "Laurel Schwulst",
        "source_url": "https://laurelschwulst.com",
        "source_title": "Laurel Schwulst",
        "site_name": "laurelschwulst.com"
    },
    "atm_20261104195637_7389a8": {
        "title": "A Gathering of Particulars: On Building a Word-Hoard",
        "author": "Lara Palmqvist",
        "source_url": "https://blog.pshares.org/a-gathering-of-particulars-on-building-a-word-hoard/",
        "source_title": "Lara Palmqvist",
        "site_name": "blog.pshares.org"
    },
    "atm_20261104195637_b26a66": {
        "title": "Charles Broskoski - Everything is Personal (Dialectic)",
        "author": "Charles Broskoski",
        "source_url": "https://jacksondahl.com/dialectic/charles-broskoski",
        "source_title": "40. Charles Broskoski - Everything is Personal — Dialectic",
        "site_name": "jacksondahl.com"
    },
    "atm_20261104195637_e701bd": {
        "title": "Charles Broskoski - Everything is Personal (Dialectic Part 2)",
        "author": "Charles Broskoski",
        "source_url": "https://jacksondahl.com/dialectic/charles-broskoski",
        "source_title": "40. Charles Broskoski - Everything is Personal — Dialectic",
        "site_name": "jacksondahl.com"
    },
    "atm_20261104195655_b7d880": {
        "title": "On the Creative Life",
        "author": "Ava Huang",
        "source_url": None,
        "source_title": None,
        "site_name": None
    },
    "atm_20261104203552_7c9ac3": {
        "title": "14 Identical Dark Suits",
        "author": "Tokyo Deep Value",
        "source_url": "https://x.com/TokyoDeepValue",
        "source_title": "Tokyo Deep Value on X",
        "site_name": "x.com"
    }
}

# 3. Bookmark atoms configuration
BOOKMARKS_CONFIG = {
    "atm_20261104200646_55113c": {
        "title": "The House of Schoolhouse | Schoolhouse Electric",
        "url": "https://www.schoolhouseelectric.com/blogs/journal/the-house-of-schoolhouse",
        "site_name": "schoolhouseelectric.com"
    },
    "atm_20261104203422_c90c3c": {
        "title": "Patch Pocket Overshirt - Heavy Linen",
        "url": "https://us.adaysmarch.com/new-arrivals/patch-pocket-overshirt-heavy-linen-navy#aw_source=pb-5c5022d7a159c80b21005784",
        "site_name": "us.adaysmarch.com"
    },
    "atm_20261104210856_0e92ef": {
        "title": "Flamebo World Industries 2000s Skateboard Vintage Classic Hoodie Print | eBay",
        "url": "https://www.ebay.com/itm/306112714003",
        "site_name": "ebay.com"
    }
}

# 4. Image atoms configuration
IMAGES_CONFIG = {
    "atm_20261104195849_ac5d28": {
        "title": "Fashion: Photographer Greg Williams On Hollywood Knitwear",
        "url": "https://www.mrporter.com/content/images/cms/ycm/resource/blob/25457346/4c3c6ae2bef1fac956ceddf72e277b21/16x9-jpg-data.jpg/w800_q80.jpg",
        "site_name": "mrporter.com",
        "author": "MR PORTER"
    },
    "atm_20261104203402_4fed36": {
        "title": "GHIAIA CASHMERE Cotton-Twill Blazer for Men | MR PORTER",
        "url": "https://www.mrporter.com/variants/images/1647597304421610/in/w2000_q60.jpg",
        "site_name": "mrporter.com",
        "author": "MR PORTER"
    }
}


def get_atom_folder(atom_id: str, created_at: str) -> Path:
    year = created_at[:4] if created_at else "2026"
    month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
    return VAULT_DIR / "atoms" / year / month / atom_id


def main():
    print("🚀 Starting Webtack 'notes' atoms reclassification & cleanup...")
    print(f"📦 Database: {DB_PATH}")

    # 1. Backup DB
    backup_path = VAULT_DIR / "vault.db.pre_notes_cleanup.bak"
    shutil.copy2(DB_PATH, backup_path)
    print(f"💾 Created database backup at {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()

    # 2. Merge Duplicates
    print("\n🔗 Step 1: Merging duplicate atoms across collections...")
    for dup_id, (prim_id, colls_add, tags_add) in DUPLICATES_TO_MERGE.items():
        # Fetch primary atom
        prim_row = c.execute("SELECT * FROM atoms WHERE id = ?", (prim_id,)).fetchone()
        dup_row = c.execute("SELECT * FROM atoms WHERE id = ?", (dup_id,)).fetchone()

        if not prim_row or not dup_row:
            print(f"   ⚠️ Could not find primary {prim_id} or dup {dup_id}, skipping merge.")
            continue

        prim_colls = json.loads(prim_row["collections"]) if prim_row["collections"] else []
        prim_tags = json.loads(prim_row["tags"]) if prim_row["tags"] else []

        for c_item in colls_add:
            if c_item not in prim_colls:
                prim_colls.append(c_item)
        for t_item in tags_add:
            if t_item not in prim_tags:
                prim_tags.append(t_item)

        # Update primary atom on disk
        prim_folder = get_atom_folder(prim_id, prim_row["created_at"])
        prim_json_file = prim_folder / "atom.json"
        if prim_json_file.exists():
            with open(prim_json_file, "r", encoding="utf-8") as f:
                pdoc = json.load(f)
            pdoc["curation"]["collections"] = prim_colls
            pdoc["curation"]["tags"] = prim_tags
            pdoc["updated_at"] = now_iso
            with open(prim_json_file, "w", encoding="utf-8") as f:
                json.dump(pdoc, f, indent=2, ensure_ascii=False)

        # Update primary atom in DB
        c.execute("""
            UPDATE atoms
            SET collections = ?, tags = ?, updated_at = ?
            WHERE id = ?
        """, (json.dumps(prim_colls), json.dumps(prim_tags), now_iso, prim_id))

        # Delete duplicate atom from DB
        c.execute("DELETE FROM atoms WHERE id = ?", (dup_id,))

        # Remove duplicate folder on disk
        dup_folder = get_atom_folder(dup_id, dup_row["created_at"])
        if dup_folder.exists():
            trash_folder = VAULT_DIR / ".trash" / dup_id
            trash_folder.parent.mkdir(parents=True, exist_ok=True)
            if trash_folder.exists():
                shutil.rmtree(trash_folder)
            shutil.move(str(dup_folder), str(trash_folder))

        print(f"   ✅ Merged {dup_id} into {prim_id} (collections: {prim_colls})")

    conn.commit()

    # 3. Convert Quotes
    print(f"\n✍️ Step 2: Converting {len(QUOTES_CONFIG)} atoms to 'quote'...")
    for atom_id, q_cfg in QUOTES_CONFIG.items():
        row = c.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            print(f"   ⚠️ Atom {atom_id} not found!")
            continue

        atom_folder = get_atom_folder(atom_id, row["created_at"])
        atom_json_path = atom_folder / "atom.json"
        note_md_path = atom_folder / "note.md"
        quote_txt_path = atom_folder / "quote.txt"

        if not atom_folder.exists() or not atom_json_path.exists():
            print(f"   ⚠️ Atom folder/JSON missing for {atom_id}!")
            continue

        with open(atom_json_path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        text_content = row["text_content"] or ""
        word_count = len(text_content.split())

        # Write quote.txt
        with open(quote_txt_path, "w", encoding="utf-8") as f:
            f.write(text_content.strip() + "\n")

        # Delete old note.md if present
        if note_md_path.exists():
            os.remove(note_md_path)

        # Build content & source
        rel_quote_path = f"atoms/{row['created_at'][:4]}/{row['created_at'][5:7]}/{atom_id}/quote.txt"
        doc["kind"] = "quote"
        doc["updated_at"] = now_iso
        doc["curation"]["atom_title"] = q_cfg["title"]
        src = doc.setdefault("source", doc.pop("provenance", {}))
        src["source_url"] = q_cfg["source_url"]
        src["source_title"] = q_cfg["source_title"]
        src["site_name"] = q_cfg["site_name"]
        src["author"] = q_cfg["author"]

        doc["payload"]["cover_image"] = None
        doc["payload"]["text"] = {
            "file": "quote.txt",
            "relative_path": rel_quote_path,
            "excerpt": text_content.strip(),
            "word_count": word_count
        }

        meta_bag = doc.get("metadata_json", {})
        meta_bag["author"] = q_cfg["author"]
        meta_bag["word_count"] = word_count
        doc["metadata_json"] = meta_bag

        # Save atom.json
        with open(atom_json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)

        # Update DB
        c.execute("""
            UPDATE atoms
            SET kind = 'quote', atom_title = ?, author = ?, source_url = ?,
                destination_url = ?, text_content = ?, metadata = ?, raw_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            q_cfg["title"], q_cfg["author"], q_cfg["source_url"], q_cfg["source_url"],
            text_content.strip(), json.dumps(meta_bag), json.dumps(doc), now_iso, atom_id
        ))

        print(f"   ✍️ Converted quote [{atom_id}]: {q_cfg['title']} ({q_cfg['author']})")

    conn.commit()

    # 4. Convert Bookmarks
    print(f"\n🔖 Step 3: Converting {len(BOOKMARKS_CONFIG)} atoms to 'bookmark'...")
    for atom_id, b_cfg in BOOKMARKS_CONFIG.items():
        row = c.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            print(f"   ⚠️ Atom {atom_id} not found!")
            continue

        atom_folder = get_atom_folder(atom_id, row["created_at"])
        atom_json_path = atom_folder / "atom.json"
        note_md_path = atom_folder / "note.md"

        with open(atom_json_path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        if note_md_path.exists():
            os.remove(note_md_path)

        url = b_cfg["url"]
        doc["kind"] = "bookmark"
        doc["updated_at"] = now_iso
        doc["curation"]["atom_title"] = b_cfg["title"]
        src = doc.setdefault("source", doc.pop("provenance", {}))
        src["source_url"] = url
        src["source_title"] = b_cfg["title"]
        src["site_name"] = b_cfg["site_name"]

        doc["payload"]["destination_url"] = url
        doc["payload"]["text"] = None
        doc["payload"]["article"] = None

        meta_bag = doc.get("metadata_json", {})
        meta_bag["word_count"] = 0
        doc["metadata_json"] = meta_bag

        with open(atom_json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)

        c.execute("""
            UPDATE atoms
            SET kind = 'bookmark', atom_title = ?, source_url = ?, destination_url = ?,
                text_content = NULL, metadata = ?, raw_json = ?, updated_at = ?
            WHERE id = ?
        """, (
            b_cfg["title"], url, url, json.dumps(meta_bag), json.dumps(doc), now_iso, atom_id
        ))

        print(f"   🔖 Converted bookmark [{atom_id}]: {b_cfg['title']}")

    conn.commit()

    # 5. Convert Images
    print(f"\n🖼️ Step 4: Converting {len(IMAGES_CONFIG)} atoms to 'image'...")
    for atom_id, img_cfg in IMAGES_CONFIG.items():
        row = c.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            print(f"   ⚠️ Atom {atom_id} not found!")
            continue

        atom_folder = get_atom_folder(atom_id, row["created_at"])
        atom_json_path = atom_folder / "atom.json"
        note_md_path = atom_folder / "note.md"
        cover_path = atom_folder / "cover.jpg"

        with open(atom_json_path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        if note_md_path.exists():
            os.remove(note_md_path)

        img_url = img_cfg["url"]
        print(f"   📥 Downloading image asset for {atom_id}...")
        downloaded = download_image(img_url, cover_path)

        rel_cover_path = f"atoms/{row['created_at'][:4]}/{row['created_at'][5:7]}/{atom_id}/cover.jpg"
        doc["kind"] = "image"
        doc["updated_at"] = now_iso
        doc["curation"]["atom_title"] = img_cfg["title"]
        src = doc.setdefault("source", doc.pop("provenance", {}))
        src["source_url"] = img_url
        src["site_name"] = img_cfg["site_name"]
        src["author"] = img_cfg["author"]

        doc["payload"]["destination_url"] = img_url
        doc["payload"]["cover_image"] = {
            "file": "cover.jpg",
            "relative_path": rel_cover_path,
            "mime_type": downloaded["mime_type"],
            "hash": downloaded["hash"],
            "dimensions": downloaded["dimensions"],
            "aspect_ratio": downloaded["aspect_ratio"],
            "blurhash": downloaded["blurhash"],
            "color_palette": downloaded["color_palette"],
            "alt_text": None,
            "original_src_url": img_url
        }
        doc["payload"]["text"] = None

        meta_bag = {
            "aspect_ratio": downloaded["aspect_ratio"],
            "blurhash": downloaded["blurhash"],
            "color_palette": downloaded["color_palette"],
            "word_count": None
        }
        doc["metadata_json"] = meta_bag

        with open(atom_json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)

        c.execute("""
            UPDATE atoms
            SET kind = 'image', atom_title = ?, author = ?, cover_file_path = ?,
                source_url = ?, destination_url = ?, text_content = NULL,
                metadata = ?, raw_json = ?, updated_at = ?
            WHERE id = ?
        """, (
            img_cfg["title"], img_cfg["author"], rel_cover_path, img_url, img_url,
            json.dumps(meta_bag), json.dumps(doc), now_iso, atom_id
        ))

        print(f"   🖼️ Converted image [{atom_id}]: {img_cfg['title']} ({downloaded['dimensions']['width']}x{downloaded['dimensions']['height']})")

    conn.commit()

    # 6. Check summary of kinds in database
    print("\n📊 New Vault Kind Breakdown:")
    for k, cnt in c.execute("SELECT kind, COUNT(*) FROM atoms GROUP BY kind ORDER BY COUNT(*) DESC").fetchall():
        print(f"   {k:12s}: {cnt:,}")

    # 7. Regenerate Viewer & Manifest
    print("\n🖥️ Step 5: Regenerating local HTML masonry viewer & exports...")
    viewer_file = generate_viewer(VAULT_DIR)
    print(f"   ✅ Regenerated viewer: {viewer_file}")

    pub_rows = get_public_atoms(VAULT_DIR)
    export_file = generate_curation_export(VAULT_DIR, pub_rows)
    print(f"   ✅ Exported curation manifest: {export_file} ({len(pub_rows)} public atoms)")

    print("\n🎉 All notes cleaned up successfully!")


if __name__ == "__main__":
    main()
