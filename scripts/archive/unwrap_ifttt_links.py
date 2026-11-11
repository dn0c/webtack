#!/usr/bin/env python3
"""
WebTack — Unwrap IFTTT Links
Resolves short ift.tt redirect links for quotes and bookmarks to their canonical destination URLs,
updating provenance.source_url, provenance.site_name, notes, text_content, SQLite, and atom.json.
"""

import sys
import re
import json
import sqlite3
import requests
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, generate_curation_export, upload_manifest_to_gcs, get_public_atoms, DEFAULT_GCS_BUCKET

VAULT_DIR = REPO_ROOT / "vault"

DOMAIN_MAPPING = {
    "nytimes.com": "The New York Times",
    "newyorker.com": "The New Yorker",
    "theatlantic.com": "The Atlantic",
    "medium.com": "Medium",
    "nymag.com": "New York Magazine",
    "thecut.com": "The Cut",
    "inc.com": "Inc.",
    "gawker.com": "Gawker",
    "deadspin.com": "Deadspin",
    "recode.net": "Recode",
    "mailchimp.com": "Mailchimp",
    "jotform.com": "Jotform",
    "thegreatdiscontent.com": "The Great Discontent",
    "apple.com": "Apple",
    "basecamp.com": "Basecamp",
    "signalvnoise.com": "Signal v. Noise",
    "wearemel.com": "MEL Magazine",
    "features.wearemel.com": "MEL Magazine",
    "fastcompany.com": "Fast Company",
    "wired.com": "Wired",
    "theverge.com": "The Verge",
    "vox.com": "Vox",
    "bloomberg.com": "Bloomberg",
    "wsj.com": "The Wall Street Journal",
    "espn.com": "ESPN",
    "latimes.com": "Los Angeles Times",
    "washingtonpost.com": "The Washington Post"
}


def get_site_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "").lower()
    for k, v in DOMAIN_MAPPING.items():
        if domain == k or domain.endswith("." + k):
            return v
    return domain


def resolve_ifttt(u: str, session: requests.Session) -> str:
    """Trace IFTTT redirect headers to recover target destination URL."""
    if not u or "ift.tt" not in u:
        return u

    cur = u
    target = None
    for _ in range(4):
        try:
            r = session.get(cur, allow_redirects=False, timeout=8)
            loc = r.headers.get("Location")
            if not loc:
                break
            if "ift.tt" in loc:
                cur = loc
                continue
            target = loc
            break
        except Exception:
            break

    if not target:
        return u

    # Attempt to resolve further redirects to the final canonical URL
    try:
        r2 = session.head(target, allow_redirects=True, timeout=6)
        if r2.status_code < 400 and r2.url:
            return r2.url
    except Exception:
        pass

    return target


def main():
    conn = get_db(VAULT_DIR)
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, author, source_url, destination_url, notes, text_content, raw_json
        FROM atoms
        WHERE source_url LIKE '%ift.tt%' OR destination_url LIKE '%ift.tt%'
    """).fetchall()

    print(f"🔍 Found {len(rows)} atoms with ift.tt links.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    now_iso = datetime.now(timezone.utc).isoformat()
    unwrapped_count = 0
    failed_count = 0

    for idx, r in enumerate(rows, 1):
        aid = r["id"]
        created_at = r["created_at"]
        old_url = r["source_url"] or r["destination_url"]

        new_url = resolve_ifttt(old_url, session)
        if not new_url or new_url == old_url or "ift.tt" in new_url:
            print(f"[{idx}/{len(rows)}] ⚠️ Could not resolve {old_url} for {aid}")
            failed_count += 1
            continue

        site_name = get_site_name(new_url)
        print(f"[{idx}/{len(rows)}] ✨ {aid}: {old_url} ➔ {new_url} ({site_name})")

        # Update notes
        old_notes = r["notes"] or ""
        new_notes = old_notes.replace(old_url, new_url)

        # Update text_content
        old_text = r["text_content"] or ""
        new_text = old_text.replace(old_url, new_url)

        # Update raw_json
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        if "provenance" in raw and isinstance(raw["provenance"], dict):
            raw["provenance"]["source_url"] = new_url
            raw["provenance"]["canonical_url"] = new_url
            raw["provenance"]["site_name"] = site_name
        if "curation" in raw and isinstance(raw["curation"], dict):
            raw["curation"]["notes"] = new_notes
        if "payload" in raw and isinstance(raw["payload"], dict):
            raw["payload"]["destination_url"] = new_url
            if "text" in raw["payload"] and isinstance(raw["payload"]["text"], dict):
                ex = raw["payload"]["text"].get("excerpt") or ""
                raw["payload"]["text"]["excerpt"] = ex.replace(old_url, new_url)
        raw["updated_at"] = now_iso
        new_raw_json = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET source_url = ?,
                    destination_url = ?,
                    notes = ?,
                    text_content = ?,
                    raw_json = ?
                WHERE id = ?
            """, (new_url, new_url, new_notes, new_text, new_raw_json, aid))

        # Update atom.json & quote.md on disk
        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_folder = VAULT_DIR / "atoms" / year / month / aid

        atom_json_path = atom_folder / "atom.json"
        if atom_json_path.exists():
            try:
                with open(atom_json_path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Failed to update atom.json for {aid}: {e}")

        quote_md_path = atom_folder / "quote.md"
        if quote_md_path.exists():
            try:
                with open(quote_md_path, "r", encoding="utf-8") as f:
                    q_content = f.read()
                new_q = q_content.replace(old_url, new_url)
                if new_q != q_content:
                    with open(quote_md_path, "w", encoding="utf-8") as f:
                        f.write(new_q)
            except Exception as e:
                print(f"⚠️ Failed to update quote.md for {aid}: {e}")

        unwrapped_count += 1

    print(f"\n🎉 Successfully unwrapped {unwrapped_count} / {len(rows)} ift.tt links!")
    if failed_count:
        print(f"⚠️ Failed to unwrap {failed_count} links.")

    # Regenerate public export & upload to GCS
    print("\n📦 Regenerating curation_public.json...")
    public_rows = get_public_atoms(VAULT_DIR)
    generate_curation_export(VAULT_DIR, public_rows, bucket=DEFAULT_GCS_BUCKET)
    print("🚀 Publishing updated manifest to GCS...")
    upload_manifest_to_gcs(VAULT_DIR, bucket=DEFAULT_GCS_BUCKET)
    print("✅ All done!")


if __name__ == "__main__":
    main()
