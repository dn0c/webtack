#!/usr/bin/env python3
"""
Webtack — Sync Original Article Titles from Instapaper
Extracts the canonical, original article titles from Instapaper bookmarks and updates
both provenance.source_title and curation.atom_title across the vault and database.
"""

import sys
import os
import json
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, cmd_sync
from viewer import generate_viewer

VAULT_DIR = REPO_ROOT / "vault"
CACHE_FILE = VAULT_DIR / ".instapaper_bookmarks_cache.json"


def clean_url(u: str) -> str:
    if not u:
        return ""
    return u.strip().rstrip("/")


def clean_title(title: str) -> str:
    if not title:
        return ""
    t = html.unescape(title).strip()
    # Replace non-breaking spaces and excessive whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_poor_title(title: str, author: str = None) -> bool:
    if not title:
        return True
    t_clean = title.strip().lower()
    if t_clean in ("untitled", "untitled bookmark", "are.na block", "reading bookmark", "home", "file"):
        return True
    if "." in t_clean and " " not in t_clean and any(t_clean.endswith(ext) for ext in (".com", ".org", ".net", ".io", ".html", ".pdf", ".co")):
        return True
    if author and t_clean == author.strip().lower():
        return True
    return False


def main():
    if not CACHE_FILE.exists():
        print(f"❌ Cache file {CACHE_FILE} not found. Please run backfill script first.")
        sys.exit(1)

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    print(f"📦 Loaded {len(bookmarks)} Instapaper bookmarks from cache.")

    # Index bookmarks by URL
    bm_by_url = {}
    for b in bookmarks:
        u = b.get("url")
        if u:
            clean = clean_url(u)
            bm_by_url[clean] = b
            p = urlparse(u)
            # Only index host_path if there are no query parameters (avoid colliding on /watch, etc.)
            if not p.query:
                host_path = f"{p.netloc}{p.path}".rstrip("/")
                bm_by_url[host_path] = b

    conn = get_db(VAULT_DIR)
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, author, source_url, destination_url, raw_json
        FROM atoms
    """).fetchall()

    print(f"🔍 Inspecting {len(rows)} atoms in vault for Instapaper title updates...")

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_articles = 0
    updated_bookmarks = 0

    for r in rows:
        aid = r["id"]
        kind = r["kind"]
        created_at = r["created_at"]
        old_atom_title = r["atom_title"] or ""
        author = r["author"]

        src_clean = clean_url(r["source_url"] or "")
        dest_clean = clean_url(r["destination_url"] or "")

        bm = None
        for u in (src_clean, dest_clean):
            if not u:
                continue
            if u in bm_by_url:
                bm = bm_by_url[u]
                break
            p = urlparse(u)
            if not p.query:
                host_path = f"{p.netloc}{p.path}".rstrip("/")
                if host_path in bm_by_url:
                    bm = bm_by_url[host_path]
                    break

        if not bm:
            continue

        inst_title_raw = bm.get("title")
        if not inst_title_raw:
            continue

        new_title = clean_title(inst_title_raw)
        if not new_title:
            continue

        # Load atom.json
        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_folder = VAULT_DIR / "atoms" / year / month / aid
        atom_json_path = atom_folder / "atom.json"

        doc = {}
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception:
                pass

        if not doc:
            try:
                doc = json.loads(r["raw_json"])
            except Exception:
                continue

        prov = doc.setdefault("provenance", {})
        curation = doc.setdefault("curation", {})

        old_source_title = prov.get("source_title") or ""
        current_cur_title = curation.get("atom_title") or old_atom_title

        # Determine if we should update source_title and atom_title
        needs_source_update = (old_source_title != new_title)
        needs_atom_update = False

        if current_cur_title != new_title:
            # Update atom_title if:
            # 1. Current title is poor/simplified
            # 2. Current title was identical to old_source_title (meaning it wasn't a manual custom title)
            # 3. New title has more complete punctuation/diacritics/casing
            if is_poor_title(current_cur_title, author):
                needs_atom_update = True
            elif current_cur_title == old_source_title:
                needs_atom_update = True
            elif len(new_title) > len(current_cur_title) and new_title.startswith(current_cur_title):
                needs_atom_update = True

        if not (needs_source_update or needs_atom_update):
            continue

        prov["source_title"] = new_title
        if needs_atom_update:
            curation["atom_title"] = new_title
            final_atom_title = new_title
        else:
            final_atom_title = current_cur_title

        doc["updated_at"] = now_iso

        # Write atom.json
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "w", encoding="utf-8") as f:
                    json.dump(doc, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Error writing {atom_json_path}: {e}")

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET atom_title = ?,
                    raw_json = ?,
                    updated_at = ?
                WHERE id = ?
            """, (final_atom_title, json.dumps(doc), now_iso, aid))

        if kind == "article":
            updated_articles += 1
        else:
            updated_bookmarks += 1

    print(f"\n✅ Title Sync Complete!")
    print(f"   • Updated Articles:  {updated_articles}")
    print(f"   • Updated Bookmarks: {updated_bookmarks}")

    if updated_articles > 0 or updated_bookmarks > 0:
        print("\n🔄 Regenerating Webtack viewer index...")
        generate_viewer(VAULT_DIR)
        print("✅ Viewer index regenerated!")


if __name__ == "__main__":
    main()
