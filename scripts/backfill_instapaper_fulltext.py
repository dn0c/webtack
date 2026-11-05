#!/usr/bin/env python3
"""
WideWeb — Backfill Instapaper Full Text
Fetches parsed full-text articles directly from the Instapaper API (v2 /bookmarks/{id}/parse),
converts the HTML to clean Markdown, writes offline article.md sidecars,
promotes matching bookmarks to first-class 'article' atoms, and updates SQLite & viewer.
"""

import sys
import os
import json
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import concurrent.futures

import requests
import trafilatura
from bs4 import BeautifulSoup

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db
from viewer import generate_viewer

CONFIG_MCP_PATH = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"


def get_instapaper_token() -> str:
    """Retrieve Instapaper access token."""
    token = os.environ.get("INSTAPAPER_ACCESS_TOKEN")
    if token:
        return token

    local_cred = REPO_ROOT / "vault" / ".sync_credentials.json"
    if local_cred.exists():
        try:
            with open(local_cred, "r", encoding="utf-8") as f:
                c = json.load(f)
                if c.get("instapaper_access_token"):
                    return c["instapaper_access_token"]
        except Exception:
            pass

    if CONFIG_MCP_PATH.exists():
        try:
            with open(CONFIG_MCP_PATH, "r", encoding="utf-8") as f:
                mcp = json.load(f).get("mcpServers", {})
                token = mcp.get("instapaper", {}).get("env", {}).get("INSTAPAPER_ACCESS_TOKEN")
                if token:
                    return token
        except Exception:
            pass

    raise RuntimeError("Could not find Instapaper access token in env or mcp_config.json")


def clean_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    return u.rstrip("/")


def html_to_clean_markdown(html_content: str, url: str = None) -> tuple[str, int]:
    """Convert HTML article body to clean Markdown using trafilatura with BeautifulSoup fallback."""
    if not html_content:
        return "", 0

    # Try trafilatura first
    md = trafilatura.extract(
        html_content,
        url=url,
        include_links=True,
        include_images=True,
        output_format="markdown"
    )
    if md and len(md.split()) >= 40:
        return md.strip(), len(md.split())

    # Fallback to BeautifulSoup clean text extraction
    soup = BeautifulSoup(html_content, "html.parser")
    # Remove script, style, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()

    paragraphs = []
    for p in soup.find_all(["p", "h1", "h2", "h3", "h4", "blockquote", "li"]):
        txt = p.get_text(separator=" ", strip=True)
        if txt:
            if p.name.startswith("h"):
                level = p.name[1]
                paragraphs.append(f"{'#' * int(level)} {txt}\n")
            elif p.name == "blockquote":
                paragraphs.append(f"> {txt}\n")
            elif p.name == "li":
                paragraphs.append(f"- {txt}")
            else:
                paragraphs.append(f"{txt}\n")

    fallback_md = "\n\n".join(paragraphs).strip()
    words = len(fallback_md.split())
    return fallback_md, words


def fetch_all_instapaper_bookmarks(session: requests.Session, cache_file: Path) -> list[dict]:
    """Fetch bookmarks across unread, folders, starred, and archive with local caching."""
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if isinstance(cached, list) and len(cached) > 0:
                    print(f"📦 Loaded {len(cached)} bookmarks from local cache: {cache_file.name}")
                    return cached
        except Exception:
            pass

    print("📥 Indexing all bookmarks from Instapaper API...")
    all_bookmarks = {}

    def fetch_section(name: str, endpoint: str):
        offset = 0
        limit = 500
        count = 0
        while True:
            sep = "&" if "?" in endpoint else "?"
            url = f"{endpoint}{sep}limit={limit}&offset={offset}"
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code != 200:
                    print(f"   ⚠️ Instapaper API returned {resp.status_code} for {name} (offset={offset})")
                    break
                data = resp.json()
                bms = data.get("bookmarks", [])
                if not bms:
                    break
                for b in bms:
                    bid = str(b.get("id"))
                    if bid not in all_bookmarks:
                        b["_source_section"] = name
                        all_bookmarks[bid] = b
                count += len(bms)
                offset += len(bms)
                if len(bms) < limit:
                    break
            except Exception as e:
                print(f"   ❌ Error fetching {name} at offset {offset}: {e}")
                break
        print(f"   ✓ {name}: found {count} items")

    # 1. Home / Unread
    fetch_section("unread", "https://www.instapaper.com/api/2/bookmarks?section=home")

    # 2. Custom Folders
    try:
        f_resp = session.get("https://www.instapaper.com/api/2/folders", timeout=15)
        if f_resp.status_code == 200:
            folders = f_resp.json().get("folders", [])
            for f in folders:
                fid = f.get("id")
                ftitle = f.get("title", f"folder-{fid}")
                if fid:
                    fetch_section(f"folder:{ftitle}", f"https://www.instapaper.com/api/2/bookmarks?folder_id={fid}")
    except Exception as e:
        print(f"   ⚠️ Error fetching folders: {e}")

    # 3. Liked / Starred
    fetch_section("starred", "https://www.instapaper.com/api/2/bookmarks?section=liked")

    # 4. Archive
    fetch_section("archive", "https://www.instapaper.com/api/2/bookmarks?section=archive")

    result = list(all_bookmarks.values())
    print(f"✅ Total unique Instapaper bookmarks indexed: {len(result)}")

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"💾 Saved bookmarks index to {cache_file.name}")
    except Exception as e:
        print(f"⚠️ Could not write cache file: {e}")

    return result


def backfill_atom_fulltext(session: requests.Session, atom: dict, bookmark: dict, vault_dir: Path) -> bool:
    """Fetch article parse from Instapaper and update atom on disk and DB."""
    bid = bookmark.get("id")
    aid = atom["id"]
    created_at = atom["created_at"]
    year = created_at[:4] if created_at else "2026"
    month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
    atom_folder = vault_dir / "atoms" / year / month / aid

    if not atom_folder.exists():
        # Fallback search if folder path mismatch
        matches = list((vault_dir / "atoms").glob(f"**/{aid}"))
        if matches:
            atom_folder = matches[0]
        else:
            return False

    parse_url = f"https://www.instapaper.com/api/2/bookmarks/{bid}/parse"
    try:
        resp = session.get(parse_url, timeout=25)
        if resp.status_code != 200:
            return False
        data = resp.json()
    except Exception:
        return False

    content_obj = data.get("content")
    if not content_obj:
        return False

    html_body = content_obj.get("body") if isinstance(content_obj, dict) else content_obj
    if not html_body or len(html_body.strip()) < 100:
        return False

    target_url = bookmark.get("url") or atom.get("source_url")
    md, word_count = html_to_clean_markdown(html_body, url=target_url)

    if word_count < 80:
        # Not a full article
        return False

    # Extract author from metadata if available
    inst_meta = data.get("metadata", {})
    author_name = None
    if isinstance(inst_meta, dict) and inst_meta.get("author"):
        inst_auth = inst_meta["author"]
        if isinstance(inst_auth, dict):
            author_name = inst_auth.get("name")
        elif isinstance(inst_auth, str):
            author_name = inst_auth

    # 1. Write article.md
    article_path = atom_folder / "article.md"
    with open(article_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 2. Read and update atom.json
    atom_json_path = atom_folder / "atom.json"
    doc = {}
    if atom_json_path.exists():
        try:
            with open(atom_json_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            pass

    doc["kind"] = "article"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = now_iso

    # Ensure payload structure
    payload = doc.setdefault("payload", {})
    rel_article_path = str(article_path.relative_to(vault_dir))
    payload["article"] = {
        "file": "article.md",
        "relative_path": rel_article_path,
        "word_count": word_count,
        "byline": author_name or doc.get("provenance", {}).get("author") or atom.get("author")
    }

    # Ensure curation tags contain instapaper
    curation = doc.setdefault("curation", {})
    tags = curation.setdefault("tags", [])
    if "instapaper" not in tags:
        tags.append("instapaper")
    curation["tags"] = tags

    # Update metadata_json
    meta_json = doc.setdefault("metadata_json", {})
    meta_json["word_count"] = word_count
    if author_name and not doc.get("provenance", {}).get("author"):
        doc.setdefault("provenance", {})["author"] = author_name

    with open(atom_json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    # 3. Update SQLite
    conn = get_db(vault_dir)
    with conn:
        conn.execute("""
            UPDATE atoms
            SET kind = 'article',
                text_content = ?,
                author = COALESCE(?, author),
                metadata = ?,
                raw_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            md[:40000],  # excerpt/preview text in DB
            author_name,
            json.dumps(meta_json),
            json.dumps(doc),
            now_iso,
            aid
        ))

    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill Instapaper full-text into WideWeb library.")
    parser.add_argument("--workers", type=int, default=6, help="Number of concurrent worker threads (default: 6)")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of items to process (0 = all)")
    parser.add_argument("--refresh-cache", action="store_true", help="Force refresh of Instapaper bookmarks index")
    args = parser.parse_args()

    vault_dir = REPO_ROOT / "vault"
    token = get_instapaper_token()

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "User-Agent": "WideWeb-Backfill/1.0"
    })

    cache_file = vault_dir / ".instapaper_bookmarks_cache.json"
    if args.refresh_cache and cache_file.exists():
        cache_file.unlink()

    bookmarks = fetch_all_instapaper_bookmarks(session, cache_file)

    # Build lookup index by normalized URL and bookmark ID
    bm_by_url = {}
    bm_by_id = {}
    for b in bookmarks:
        bid = str(b.get("id"))
        bm_by_id[bid] = b
        u = b.get("url")
        if u:
            clean = clean_url(u)
            bm_by_url[clean] = b
            # Also without scheme
            p = urlparse(clean)
            host_path = f"{p.netloc}{p.path}".rstrip("/")
            bm_by_url[host_path] = b

    print(f"🔗 Indexed {len(bm_by_url)} unique URL keys for matching.")

    # Query vault for candidate atoms that need full article text
    conn = get_db(vault_dir)
    print("🔍 Scanning vault for atoms matching Instapaper bookmarks...")
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, author, destination_url, source_url, raw_json
        FROM atoms
    """).fetchall()

    tasks = []
    already_has_article = 0

    for r in rows:
        aid = r["id"]
        created_at = r["created_at"]
        year = created_at[:4] if created_at else "2026"
        month = created_at[5:7] if created_at and len(created_at) >= 7 else "11"
        atom_folder = vault_dir / "atoms" / year / month / aid

        # Check if article.md already exists
        art_path = atom_folder / "article.md"
        if art_path.exists():
            already_has_article += 1
            continue

        # Match against Instapaper
        src_clean = clean_url(r["source_url"] or "")
        dest_clean = clean_url(r["destination_url"] or "")

        matched_bm = None
        for u in (src_clean, dest_clean):
            if not u:
                continue
            if u in bm_by_url:
                matched_bm = bm_by_url[u]
                break
            p = urlparse(u)
            host_path = f"{p.netloc}{p.path}".rstrip("/")
            if host_path in bm_by_url:
                matched_bm = bm_by_url[host_path]
                break

        if matched_bm:
            tasks.append((r, matched_bm))

    print(f"📊 Vault Status:")
    print(f"   • Total atoms scanned: {len(rows)}")
    print(f"   • Already have offline article.md: {already_has_article}")
    print(f"   • Matching Instapaper candidates needing full text: {len(tasks)}")

    if not tasks:
        print("🎉 No candidate atoms need Instapaper backfill!")
        return

    if args.limit > 0:
        tasks = tasks[:args.limit]
        print(f"⚡ Limiting processing to first {len(tasks)} items.")

    print(f"\n🚀 Processing {len(tasks)} items with {args.workers} concurrent workers...\n")

    success_count = 0
    skipped_count = 0
    t0 = time.time()

    def worker(task):
        r, bm = task
        # Create a thread-local session
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "WideWeb-Backfill/1.0"
        })
        return r, bm, backfill_atom_fulltext(s, dict(r), bm, vault_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, t): t for t in tasks}
        for idx, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r, bm, ok = fut.result()
            title = (r["atom_title"] or bm.get("title") or "Untitled")[:40]
            if ok:
                success_count += 1
                status_str = "✅ Captured Full Text"
            else:
                skipped_count += 1
                status_str = "⏭️ No Full Text / Skipped"

            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0
            print(f"[{idx}/{len(tasks)}] {status_str} | {title} ({rate:.1f} items/s)")

    print(f"\n✨ Backfill Complete in {time.time()-t0:.1f}s!")
    print(f"   • Successfully promoted to article: {success_count}")
    print(f"   • Skipped (short or not parsed): {skipped_count}")

    if success_count > 0:
        print("\n🔄 Regenerating WideWeb viewer index...")
        generate_viewer(vault_dir)
        print("✅ Viewer index updated!")


if __name__ == "__main__":
    main()

