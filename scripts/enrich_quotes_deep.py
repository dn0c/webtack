#!/usr/bin/env python3
"""
Webtack — Deep Quote Enrichment
Performs multi-pass metadata recovery for quotes across the vault:
Pass 1: Parses 103 book quotes ("via <Book> by <Author>") to populate author and metadata.
Pass 2: Enriches 40 highlight quotes with trapped URLs & titles from notes.
Pass 3: Unwraps and promotes 139 trapped body URLs (including bit.ly & ift.tt) into proper provenance.
Pass 4: Re-exports and publishes curation_public.json to GCS.
"""

import sys
import re
import html
import json
import sqlite3
import requests
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import (
    get_db,
    generate_curation_export,
    upload_manifest_to_gcs,
    get_public_atoms,
    DEFAULT_GCS_BUCKET
)

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
    "washingtonpost.com": "The Washington Post",
    "californiasunday.com": "The California Sunday Magazine",
    "story.californiasunday.com": "The California Sunday Magazine",
    "asteriskmag.com": "Asterisk",
    "maggieappleton.com": "Maggie Appleton",
    "noemamag.com": "NOEMA"
}

KNOWN_AUTHORS = {
    "maggieappleton.com": "Maggie Appleton",
    "asteriskmag.com": "Celine Nguyen",
    "minutes.substack.com": "Will Manidis",
    "ribbonfarm.com": "Venkatesh Rao",
    "marco.org": "Marco Arment",
    "randsinrepose.com": "Michael Lopp",
    "austinkleon.com": "Austin Kleon",
    "sethgodin.typepad.com": "Seth Godin"
}


def get_site_name(url: str) -> str:
    if not url:
        return None
    domain = urlparse(url).netloc.replace("www.", "").lower()
    for k, v in DOMAIN_MAPPING.items():
        if domain == k or domain.endswith("." + k):
            return v
    return domain


def resolve_shortlink(u: str, session: requests.Session) -> str:
    """Unwrap bit.ly, ift.tt, and generic redirect shortlinks."""
    if not u:
        return u
    if not any(k in u for k in ("bit.ly", "ift.tt", "t.co", "goo.gl", "buff.ly", "ow.ly", "tinyurl.com")):
        return u

    cur = u
    target = None
    for _ in range(4):
        try:
            r = session.get(cur, allow_redirects=False, timeout=6)
            loc = r.headers.get("Location")
            if not loc:
                break
            if any(k in loc for k in ("bit.ly", "ift.tt", "t.co")):
                cur = loc
                continue
            target = loc
            break
        except Exception:
            break

    if not target:
        return u

    try:
        r2 = session.head(target, allow_redirects=True, timeout=5)
        if r2.status_code < 400 and r2.url:
            return r2.url
    except Exception:
        pass

    return target


def fetch_article_meta(url: str, session: requests.Session):
    """Fetch OpenGraph title, author, site_name, and favicon."""
    meta = {"title": None, "author": None, "site_name": None, "favicon": None}
    domain = urlparse(url).netloc.replace("www.", "").lower()
    if domain in KNOWN_AUTHORS:
        meta["author"] = KNOWN_AUTHORS[domain]

    meta["site_name"] = get_site_name(url)

    try:
        resp = session.get(url, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Title
            og_t = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
            if og_t and og_t.get("content"):
                meta["title"] = og_t["content"].strip()
            elif soup.title and soup.title.string:
                meta["title"] = soup.title.string.strip()

            # Author
            if not meta["author"]:
                for m in soup.find_all("meta"):
                    if m.get("name") in ("author", "twitter:creator") or m.get("property") in ("author", "article:author"):
                        c = m.get("content")
                        if c and not c.startswith("http"):
                            meta["author"] = c.strip()
                            break

            # Site name
            og_s = soup.find("meta", property="og:site_name")
            if og_s and og_s.get("content"):
                meta["site_name"] = og_s["content"].strip()

            # Favicon
            for link in soup.find_all("link"):
                rel = " ".join(link.get("rel", []))
                if "icon" in rel:
                    href = link.get("href")
                    if href:
                        if href.startswith("//"):
                            meta["favicon"] = "https:" + href
                        elif href.startswith("/"):
                            meta["favicon"] = f"https://{domain}{href}"
                        elif href.startswith("http"):
                            meta["favicon"] = href
                        break
    except Exception:
        pass

    return meta


def main():
    conn = get_db(VAULT_DIR)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    now_iso = datetime.now(timezone.utc).isoformat()

    print("=" * 60)
    print("🚀 STARTING MULTI-PASS QUOTE ENRICHMENT")
    print("=" * 60)

    # ----------------------------------------------------
    # PASS 1: Book Quotes Attribution (103 quotes)
    # ----------------------------------------------------
    print("\n📚 PASS 1: Parsing book quotes attribution from notes...")
    book_rows = conn.execute("""
        SELECT id, atom_title, author, notes, raw_json, created_at
        FROM atoms
        WHERE kind = 'quote' AND (author IS NULL OR author = '') AND notes LIKE 'via % by %'
    """).fetchall()

    pass1_count = 0
    for r in book_rows:
        aid = r["id"]
        notes = r["notes"] or ""
        m = re.search(r"via\s+(.+?)\s+by\s+([^(\n]+)", notes)
        if not m:
            continue
        book_title = html.unescape(m.group(1)).strip()
        author_name = html.unescape(m.group(2)).strip()
        if not author_name:
            continue

        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        if "provenance" in raw and isinstance(raw["provenance"], dict):
            raw["provenance"]["author"] = author_name
            if not raw["provenance"].get("source_title"):
                raw["provenance"]["source_title"] = book_title
        if "metadata_json" not in raw or not isinstance(raw["metadata_json"], dict):
            raw["metadata_json"] = {}
        raw["metadata_json"]["author"] = author_name
        raw["metadata_json"]["book_title"] = book_title
        raw["updated_at"] = now_iso
        new_raw = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET author = ?,
                    raw_json = ?
                WHERE id = ?
            """, (author_name, new_raw, aid))

        # Update atom.json on disk
        year = r["created_at"][:4] if r["created_at"] else "2026"
        month = r["created_at"][5:7] if r["created_at"] and len(r["created_at"]) >= 7 else "11"
        atom_file = VAULT_DIR / "atoms" / year / month / aid / "atom.json"
        if atom_file.exists():
            try:
                with open(atom_file, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        pass1_count += 1
        if pass1_count <= 5 or pass1_count % 25 == 0:
            print(f"   [{pass1_count}/{len(book_rows)}] ✨ {aid}: {book_title} ➔ Author: {author_name}")

    print(f"✅ Pass 1 Complete: Enriched {pass1_count} book quote authors!")

    # ----------------------------------------------------
    # PASS 2: Highlight Quotes with Trapped URLs in Notes (40 quotes)
    # ----------------------------------------------------
    print("\n🔍 PASS 2: Extracting trapped URLs & metadata from highlight notes...")
    hl_rows = conn.execute("""
        SELECT id, atom_title, author, notes, text_content, raw_json, created_at
        FROM atoms
        WHERE kind = 'quote' AND (source_url IS NULL OR source_url = '') AND notes LIKE '%Highlight from:%'
    """).fetchall()

    pass2_count = 0
    for r in hl_rows:
        aid = r["id"]
        notes = r["notes"] or ""
        m_url = re.search(r"Source:\s*(https?://\S+)", notes)
        m_title = re.search(r"Highlight from:\s*(.+)", notes)
        if not m_url:
            continue

        target_url = m_url.group(1).strip()
        target_title = html.unescape(m_title.group(1).splitlines()[0]).strip() if m_title else (r["atom_title"] or "Quote")

        # Fetch live metadata
        live_meta = fetch_article_meta(target_url, session)
        final_title = target_title or live_meta.get("title") or "Quote"
        final_author = r["author"] or live_meta.get("author")
        final_site = live_meta.get("site_name") or get_site_name(target_url)
        final_favicon = live_meta.get("favicon")

        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        raw["provenance"] = {
            "source_url": target_url,
            "source_title": final_title,
            "canonical_url": target_url,
            "site_name": final_site,
            "author": final_author,
            "author_url": None,
            "published_at": None,
            "favicon": final_favicon
        }
        if "curation" in raw and isinstance(raw["curation"], dict):
            raw["curation"]["atom_title"] = final_title
            raw["curation"]["notes"] = None
        if "payload" in raw and isinstance(raw["payload"], dict):
            raw["payload"]["destination_url"] = target_url

        if "metadata_json" not in raw or not isinstance(raw["metadata_json"], dict):
            raw["metadata_json"] = {}
        raw["metadata_json"]["author"] = final_author
        raw["metadata_json"]["site_name"] = final_site
        raw["updated_at"] = now_iso
        new_raw = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET atom_title = ?,
                    author = ?,
                    source_url = ?,
                    destination_url = ?,
                    notes = NULL,
                    raw_json = ?
                WHERE id = ?
            """, (final_title, final_author, target_url, target_url, new_raw, aid))

        # Update atom.json on disk
        year = r["created_at"][:4] if r["created_at"] else "2026"
        month = r["created_at"][5:7] if r["created_at"] and len(r["created_at"]) >= 7 else "11"
        atom_file = VAULT_DIR / "atoms" / year / month / aid / "atom.json"
        if atom_file.exists():
            try:
                with open(atom_file, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        pass2_count += 1
        print(f"   [{pass2_count}/{len(hl_rows)}] ✨ {aid}: \"{final_title}\" ➔ {target_url} ({final_site} | {final_author or 'No author'})")

    print(f"✅ Pass 2 Complete: Enriched {pass2_count} highlight quotes with formal provenance!")

    # ----------------------------------------------------
    # PASS 3: Trapped URLs in Quote text_content (139 quotes)
    # ----------------------------------------------------
    print("\n🔗 PASS 3: Unwrapping & promoting trapped URLs in quote body text...")
    body_rows = conn.execute("""
        SELECT id, atom_title, author, text_content, raw_json, created_at
        FROM atoms
        WHERE kind = 'quote' AND (source_url IS NULL OR source_url = '') AND (text_content LIKE '%http://%' OR text_content LIKE '%https://%')
    """).fetchall()

    pass3_count = 0
    for r in body_rows:
        aid = r["id"]
        text = r["text_content"] or ""

        # Find markdown link or raw URL
        m_md = re.search(r"Source:\s*\[([^\]]+)\]\((https?://[^\s\)]+)\)", text)
        raw_url = None
        if m_md:
            raw_url = m_md.group(2)
        else:
            m_raw = re.search(r"(https?://\S+)", text)
            if m_raw:
                raw_url = m_raw.group(1).rstrip(')\",.>]')

        if not raw_url:
            continue

        # Unwrap shortlinks (bit.ly, ift.tt)
        canonical_url = resolve_shortlink(raw_url, session)
        site_name = get_site_name(canonical_url)

        # Check if title was a truncated snippet
        cur_t = r["atom_title"] or ""
        final_t = cur_t
        if cur_t.startswith('"') or cur_t.startswith('“') or cur_t.endswith("..."):
            # Check lines for article title
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for idx, l in enumerate(lines):
                if l.startswith("Source:") and idx > 0:
                    cand = lines[idx - 1]
                    if not cand.startswith('"') and not cand.startswith('“') and len(cand) < 120:
                        final_t = cand
                        break

        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        if "provenance" not in raw or not isinstance(raw["provenance"], dict):
            raw["provenance"] = {}
        raw["provenance"]["source_url"] = canonical_url
        raw["provenance"]["canonical_url"] = canonical_url
        raw["provenance"]["source_title"] = final_t
        raw["provenance"]["site_name"] = site_name
        if "curation" in raw and isinstance(raw["curation"], dict):
            raw["curation"]["atom_title"] = final_t
        if "payload" in raw and isinstance(raw["payload"], dict):
            raw["payload"]["destination_url"] = canonical_url

        raw["updated_at"] = now_iso
        new_raw = json.dumps(raw, ensure_ascii=False)

        # Update SQLite
        with conn:
            conn.execute("""
                UPDATE atoms
                SET atom_title = ?,
                    source_url = ?,
                    destination_url = ?,
                    raw_json = ?
                WHERE id = ?
            """, (final_t, canonical_url, canonical_url, new_raw, aid))

        # Update atom.json on disk
        year = r["created_at"][:4] if r["created_at"] else "2026"
        month = r["created_at"][5:7] if r["created_at"] and len(r["created_at"]) >= 7 else "11"
        atom_file = VAULT_DIR / "atoms" / year / month / aid / "atom.json"
        if atom_file.exists():
            try:
                with open(atom_file, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        pass3_count += 1
        if pass3_count <= 5 or pass3_count % 30 == 0:
            print(f"   [{pass3_count}/{len(body_rows)}] ✨ {aid}: {raw_url} ➔ {canonical_url} ({site_name})")

    print(f"✅ Pass 3 Complete: Unwrapped and promoted {pass3_count} body URLs!")

    # ----------------------------------------------------
    # PASS 4: Manifest & GCS Sync
    # ----------------------------------------------------
    print("\n📦 PASS 4: Regenerating public manifest & syncing to GCS...")
    public_rows = get_public_atoms(VAULT_DIR)
    generate_curation_export(VAULT_DIR, public_rows, bucket=DEFAULT_GCS_BUCKET)
    upload_manifest_to_gcs(VAULT_DIR, bucket=DEFAULT_GCS_BUCKET)

    print("\n" + "=" * 60)
    print("🎉 MULTI-PASS ENRICHMENT COMPLETE!")
    print(f"   • Pass 1 (Book Authors):  {pass1_count} updated")
    print(f"   • Pass 2 (Highlight URLs): {pass2_count} enriched")
    print(f"   • Pass 3 (Body URLs):      {pass3_count} unwrapped & promoted")
    print("=" * 60)


if __name__ == "__main__":
    main()
