#!/usr/bin/env python3
"""
WideWeb — Restore Original YouTube Titles
Recovers and restores the original titles and channel authors for YouTube atoms
that were inadvertently overwritten by the URL-path collision in sync_instapaper_titles.py.
"""

import sys
import glob
import json
import sqlite3
import html
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, generate_curation_export, upload_manifest_to_gcs, get_public_atoms, DEFAULT_GCS_BUCKET

VAULT_DIR = REPO_ROOT / "vault"
IMPORT_DIR = VAULT_DIR / "import"


def extract_video_id(url: str):
    if not url:
        return None
    p = urlparse(url)
    if "youtu.be" in p.netloc:
        return p.path.lstrip("/").split("/")[0].split("?")[0]
    if "youtube.com" in p.netloc:
        qs = parse_qs(p.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0]
        if "/shorts/" in p.path:
            return p.path.split("/shorts/")[1].split("/")[0].split("?")[0]
        if "/embed/" in p.path:
            return p.path.split("/embed/")[1].split("/")[0].split("?")[0]
    return None


def clean_title(title: str) -> str:
    if not title:
        return ""
    t = html.unescape(title).strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_title_index():
    index = {}
    for f in glob.glob(str(IMPORT_DIR / "arena_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
                items = d.get("data") if isinstance(d, dict) else d
                if isinstance(items, list):
                    for b in items:
                        src = b.get("source") or {}
                        u = src.get("url") or ""
                        vid = extract_video_id(u)
                        if vid:
                            t = b.get("title") or src.get("title")
                            auth = (b.get("user") or {}).get("name")
                            if t and "Vice Meets Rob Corddry" not in t:
                                index[vid] = (clean_title(t), auth)
        except Exception as e:
            print(f"Warning reading {f}: {e}")

    # Fallback / manual entries for single channel blocks
    extras = {
        "5ErxKvL_zzU": ('"Somewhere in Detroit": Underground Resistance, Submerge, Techno and the Detroit Way', 'RolandChannel'),
        "GDpfZgjQf3s": ('No Talk Polyend Tracker-CE Firmware Chip Dirt Synth Demo And FX // Polyend Tracker Demo', 'Ron Cavagnaro'),
        "nj963-FoACI": ('Theranos whistleblower says he nearly jumped out of his seat watching Elizabeth Holmes documentary', 'CBS Mornings'),
        "wcrzJBsHis8": ('Vice Meets Rob Corddry', 'VICE')
    }
    for vid, (t, auth) in extras.items():
        if vid not in index or not index[vid][0]:
            index[vid] = (clean_title(t), auth)

    return index


def main():
    print("🔍 Building YouTube title index from Are.na imports...")
    title_index = build_title_index()
    print(f"✅ Indexed {len(title_index)} unique YouTube video titles.")

    conn = get_db(VAULT_DIR)
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, author, source_url, destination_url, raw_json
        FROM atoms
        WHERE atom_title LIKE '%Vice Meets Rob Corddry%'
    """).fetchall()

    print(f"🔍 Found {len(rows)} video atoms affected by the title collision.")

    now_iso = datetime.now(timezone.utc).isoformat()
    restored = 0
    skipped_real = 0
    missing = []

    for r in rows:
        aid = r["id"]
        created_at = r["created_at"]
        u = r["source_url"] or r["destination_url"]
        vid = extract_video_id(u)

        if vid == "wcrzJBsHis8":
            # This is the actual legitimate Rob Corddry video
            skipped_real += 1
            continue

        if not vid or vid not in title_index:
            missing.append((aid, u))
            continue

        new_title, fallback_author = title_index[vid]
        old_author = r["author"]
        new_author = old_author or fallback_author

        # Update raw_json
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        if "curation" in raw and isinstance(raw["curation"], dict):
            raw["curation"]["atom_title"] = new_title
        if "provenance" in raw and isinstance(raw["provenance"], dict):
            raw["provenance"]["source_title"] = new_title
            if new_author and not raw["provenance"].get("author"):
                raw["provenance"]["author"] = new_author
        raw["updated_at"] = now_iso
        new_raw_json = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET atom_title = ?,
                    author = COALESCE(?, author),
                    raw_json = ?
                WHERE id = ?
            """, (new_title, new_author, new_raw_json, aid))

        # Update atom.json on disk
        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_json_path = VAULT_DIR / "atoms" / year / month / aid / "atom.json"
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Failed writing atom.json for {aid}: {e}")

        restored += 1

    print(f"🎉 Successfully restored {restored} YouTube video titles!")
    print(f"ℹ️ Kept {skipped_real} true Rob Corddry video intact.")
    if missing:
        print(f"⚠️ Could not match {len(missing)} videos:")
        for aid, u in missing[:5]:
            print(f"   {aid}: {u}")

    # Regenerate public export & upload to GCS
    print("\n📦 Regenerating curation_public.json...")
    public_rows = get_public_atoms(VAULT_DIR)
    generate_curation_export(VAULT_DIR, public_rows, bucket=DEFAULT_GCS_BUCKET)
    print("🚀 Publishing updated manifest to GCS...")
    upload_manifest_to_gcs(VAULT_DIR, bucket=DEFAULT_GCS_BUCKET)
    print("✅ All done!")


if __name__ == "__main__":
    main()
