#!/usr/bin/env python3
"""
WebTack — Clean Quote Titles & Notes
1. Updates curated quote titles to their clean source article titles, stripping 'Quote - ' prefixes,
   resolving generic 'Quote' titles, and recovering real source titles from quote provenance/text.
   Preserves custom, thoughtful, and book titles.
2. Empties 'notes' if it simply contains the Source URL.
3. Clears author if it was previously set to the exact article title.
4. Regenerates the public manifest and syncs to GCS.
"""

import sys
import re
import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, generate_curation_export, upload_manifest_to_gcs, get_public_atoms, DEFAULT_GCS_BUCKET

VAULT_DIR = REPO_ROOT / "vault"


def clean_extracted_title(t: str) -> str:
    if not t:
        return ""
    t = html.unescape(t).strip()
    t = re.sub(r"^\s*[-—–]\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_valid_source_title(t: str) -> bool:
    if not t or len(t) < 3:
        return False
    t_clean = t.strip().lower()
    if t_clean in ("quote", "untitled", "none", "notes", "instapaper", "reading"):
        return False
    if t.startswith("Source:") or t.startswith("http://") or t.startswith("https://"):
        return False
    if t.startswith("[") and ("http" in t or t.endswith(")")):
        return False
    return True


def extract_source_title_from_text(text: str) -> str:
    if not text:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    # 1. 'Highlight from: <Title>'
    for l in lines:
        if l.startswith("Highlight from:"):
            cand = clean_extracted_title(l.replace("Highlight from:", ""))
            if is_valid_source_title(cand):
                return cand

    # 2. Line immediately preceding 'Source:'
    for idx, l in enumerate(lines):
        if l.startswith("Source:") and idx > 0:
            cand = clean_extracted_title(lines[idx - 1])
            if is_valid_source_title(cand) and not cand.startswith('"') and not cand.startswith('“') and len(cand) < 150:
                return cand

    # 3. ' - <Title> http...'
    for l in lines:
        m = re.search(r"\s+[-—–]\s+([^http\n]{4,120})\s+(https?://\S+)", l)
        if m:
            cand = clean_extracted_title(m.group(1))
            if is_valid_source_title(cand) and not cand.lower().startswith("via"):
                return cand
        m2 = re.search(r"\s+[-—–]\s+([^via\n]{4,120})\s+via Instapaper", l)
        if m2:
            cand = clean_extracted_title(m2.group(1))
            if is_valid_source_title(cand):
                return cand

    # 4. Trailing line with article title
    for l in lines[1:]:
        if l.startswith("via Instapaper") or re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}", l):
            continue
        cand = clean_extracted_title(l)
        if is_valid_source_title(cand) and len(cand) < 120 and not cand.startswith('"') and not cand.startswith('“'):
            return cand

    return None


def main():
    conn = get_db(VAULT_DIR)
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, author, source_url, destination_url, notes, text_content, raw_json
        FROM atoms
        WHERE kind = 'quote'
    """).fetchall()

    print(f"🔍 Inspecting {len(rows)} quotes in vault...")

    now_iso = datetime.now(timezone.utc).isoformat()
    titles_updated = 0
    notes_cleared = 0

    for r in rows:
        aid = r["id"]
        created_at = r["created_at"]
        cur_t = r["atom_title"] or ""
        author = r["author"] or ""
        notes = (r["notes"] or "").strip()
        text = r["text_content"] or ""
        u = (r["source_url"] or r["destination_url"] or "").strip()

        # 1. Notes check: if notes is simply the Source URL, empty it
        new_notes = r["notes"]
        is_source_url_only = False
        if notes:
            if notes.startswith("Source URL:") and len(notes.splitlines()) == 1:
                is_source_url_only = True
            elif notes == u or notes == u.rstrip("/"):
                is_source_url_only = True
            elif (notes.startswith("http://") or notes.startswith("https://")) and len(notes.split()) == 1:
                is_source_url_only = True
            elif notes.startswith("Source:") and len(notes.splitlines()) == 1:
                is_source_url_only = True

        if is_source_url_only:
            new_notes = None
            notes_cleared += 1

        # 2. Title check
        new_t = cur_t
        if cur_t.startswith("Quote - "):
            new_t = clean_extracted_title(cur_t[8:])
        elif cur_t.strip() == "Quote":
            if is_valid_source_title(author):
                new_t = author.strip()
            else:
                cand = extract_source_title_from_text(text)
                if cand:
                    new_t = cand
        elif (cur_t.startswith('"') or cur_t.startswith('“') or cur_t.endswith("...")):
            cand = extract_source_title_from_text(text)
            if cand:
                new_t = cand

        # 3. Author check: if author is identical to the article title, clear author
        new_author = author if author else None
        if new_author and new_t and new_author.strip().lower() == new_t.strip().lower():
            new_author = None

        title_changed = (new_t != cur_t)
        notes_changed = (new_notes != r["notes"])
        author_changed = (new_author != (r["author"] if r["author"] else None))

        if not (title_changed or notes_changed or author_changed):
            continue

        if title_changed:
            titles_updated += 1
            print(f"✨ [{aid}] Title: \"{cur_t}\" ➔ \"{new_t}\"")

        # Update raw_json
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        if "curation" in raw and isinstance(raw["curation"], dict):
            raw["curation"]["atom_title"] = new_t
            raw["curation"]["notes"] = new_notes
        if "provenance" in raw and isinstance(raw["provenance"], dict):
            raw["provenance"]["source_title"] = new_t
            raw["provenance"]["author"] = new_author
        if "metadata_json" in raw and isinstance(raw["metadata_json"], dict):
            raw["metadata_json"]["author"] = new_author
        raw["updated_at"] = now_iso
        new_raw_json = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET atom_title = ?,
                    notes = ?,
                    author = ?,
                    raw_json = ?
                WHERE id = ?
            """, (new_t, new_notes, new_author, new_raw_json, aid))

        # Update atom.json on disk
        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_json_path = VAULT_DIR / "atoms" / year / month / aid / "atom.json"
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Failed to update atom.json for {aid}: {e}")

    print(f"\n🎉 Successfully updated {titles_updated} quote titles!")
    print(f"🧹 Emptied Source URL from notes on {notes_cleared} quotes!")

    # Regenerate public export & upload to GCS
    print("\n📦 Regenerating curation_public.json...")
    public_rows = get_public_atoms(VAULT_DIR)
    generate_curation_export(VAULT_DIR, public_rows, bucket=DEFAULT_GCS_BUCKET)
    print("🚀 Publishing updated manifest to GCS...")
    upload_manifest_to_gcs(VAULT_DIR, bucket=DEFAULT_GCS_BUCKET)
    print("✅ All done!")


if __name__ == "__main__":
    main()
