#!/usr/bin/env python3
"""
scripts/split_hybrid_quotes_and_articles.py

Splits hybrid atoms (which currently contain both quote.md and article.md) into:
1. Pure Quote Atoms:
   - Preserves original atom ID and folder
   - kind: "quote"
   - content.text points to quote.md
   - content.article is set to None
   - article.md deleted from disk
   - Preserves tags and collections

2. Dedicated Article Atoms:
   - For each unique article source_url without an existing independent article atom,
     creates a dedicated kind: "article" atom
   - content.article points to article.md
   - content.text is None
   - tags: ['reading', 'instapaper'], collections: ['Reading']
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import curate
import viewer


def find_hybrid_atoms_fast(vault_dir: Path):
    """Find all hybrid atoms by querying vault.db and verifying folder contents."""
    conn = sqlite3.connect(vault_dir / "vault.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, created_at, source_url FROM atoms")
    rows = c.fetchall()

    hybrids = []
    for r in rows:
        dt = r["created_at"]
        folder = vault_dir / "atoms" / dt[:4] / dt[5:7] / r["id"]
        quote_file = folder / "quote.md"
        article_file = folder / "article.md"
        atom_json = folder / "atom.json"
        if quote_file.exists() and article_file.exists() and atom_json.exists():
            try:
                doc = json.loads(atom_json.read_text(encoding="utf-8"))
                hybrids.append((folder, atom_json, doc))
            except Exception as e:
                print(f"⚠️ Error reading {atom_json}: {e}")

    conn.close()
    return hybrids


def find_existing_independent_articles_fast(vault_dir: Path, hybrid_ids: set):
    """Find existing non-hybrid articles via vault.db."""
    conn = sqlite3.connect(vault_dir / "vault.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, created_at, source_url FROM atoms WHERE kind = 'article'")
    rows = c.fetchall()

    articles_by_url = defaultdict(list)
    for r in rows:
        aid = r["id"]
        if aid in hybrid_ids:
            continue
        u = r["source_url"]
        if u:
            articles_by_url[u].append(aid)

    conn.close()
    return articles_by_url


def run_split(vault_dir: Path, dry_run: bool = False):
    print(f"🔍 Searching for hybrid atoms in {vault_dir}...", flush=True)
    hybrids = find_hybrid_atoms_fast(vault_dir)
    print(f"Found {len(hybrids)} hybrid atoms with both quote.md and article.md.", flush=True)

    hybrid_ids = {d["id"] for _, _, d in hybrids}
    existing_articles = find_existing_independent_articles_fast(vault_dir, hybrid_ids)

    # Group hybrid atoms by source_url
    by_url = defaultdict(list)
    for folder, json_path, doc in hybrids:
        url = (doc.get("source") or {}).get("source_url")
        by_url[url].append((folder, json_path, doc))

    print(f"Grouped into {len(by_url)} unique source URLs.", flush=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    articles_created = 0
    articles_skipped_existing = 0
    quotes_restored = 0

    # 1. Create dedicated article atoms for unique URLs
    for url, atom_list in by_url.items():
        if url and url in existing_articles:
            articles_skipped_existing += 1
            continue

        # Choose the best representative hybrid atom for article metadata and markdown
        rep_folder, rep_json_path, rep_doc = atom_list[0]
        max_wc = 0
        for f, jp, d in atom_list:
            wc = ((d.get("content") or {}).get("article") or {}).get("word_count", 0) or 0
            if wc > max_wc:
                max_wc = wc
                rep_folder, rep_json_path, rep_doc = f, jp, d

        article_md_src = rep_folder / "article.md"
        if not article_md_src.exists():
            continue

        rep_cur = rep_doc.get("curation") or {}
        rep_src = rep_doc.get("source") or {}
        rep_art = (rep_doc.get("content") or {}).get("article") or {}

        word_count = rep_art.get("word_count") or 0
        article_title = rep_cur.get("atom_title") or rep_src.get("source_title") or "Article"
        author_name = rep_art.get("byline") or rep_src.get("author")

        # Generate new atom ID
        new_atom_id = curate.generate_atom_id()
        created_str = rep_doc.get("created_at") or now_iso
        try:
            dt = datetime.fromisoformat(created_str)
            year_str = f"{dt.year:04d}"
            month_str = f"{dt.month:02d}"
        except Exception:
            year_str = "2026"
            month_str = "11"

        new_rel_dir = Path("atoms") / year_str / month_str / new_atom_id
        new_abs_dir = vault_dir / new_rel_dir

        new_doc = {
            "$schema": "https://raw.githubusercontent.com/dn0c/webtack/main/schema/atom.schema.json",
            "id": new_atom_id,
            "kind": "article",
            "version": 3,
            "created_at": created_str,
            "updated_at": now_iso,
            "curation": {
                "atom_title": article_title,
                "notes": None,
                "tags": ["reading", "instapaper"],
                "collections": ["Reading"],
                "favorite": False,
                "visibility": rep_cur.get("visibility", "public")
            },
            "metadata_json": {
                "word_count": word_count,
                "author": author_name
            },
            "content": {
                "cover_image": None,
                "text": None,
                "article": {
                    "file": "article.md",
                    "relative_path": str(new_rel_dir / "article.md"),
                    "word_count": word_count,
                    "byline": author_name
                },
                "video": None,
                "file": None
            },
            "source": {
                "source_url": rep_src.get("source_url") or url,
                "source_title": rep_src.get("source_title") or article_title,
                "site_name": rep_src.get("site_name"),
                "author": author_name,
                "published_at": rep_src.get("published_at"),
                "favicon": rep_src.get("favicon"),
                "capture_method": rep_src.get("capture_method") or "instapaper",
                "capture_id": rep_src.get("capture_id"),
                "capture_url": rep_src.get("capture_url")
            }
        }

        if not dry_run:
            new_abs_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(article_md_src, new_abs_dir / "article.md")
            (new_abs_dir / "atom.json").write_text(json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        articles_created += 1

    # 2. Restore all 468 Quote Atoms
    for folder, json_path, doc in hybrids:
        quote_text_obj = (doc.get("content") or {}).get("text") or {}
        quote_word_count = quote_text_obj.get("word_count") or 0
        quote_excerpt = quote_text_obj.get("excerpt") or ""

        # Update doc
        doc["kind"] = "quote"
        doc["updated_at"] = now_iso

        content = doc.setdefault("content", {})
        # Remove article slot
        content["article"] = None

        created_str = doc.get("created_at") or now_iso
        try:
            dt = datetime.fromisoformat(created_str)
            year_str = f"{dt.year:04d}"
            month_str = f"{dt.month:02d}"
        except Exception:
            year_str = "2026"
            month_str = "11"

        rel_quote_path = f"atoms/{year_str}/{month_str}/{doc['id']}/quote.md"
        content["text"] = {
            "file": "quote.md",
            "relative_path": rel_quote_path,
            "excerpt": quote_excerpt,
            "word_count": quote_word_count
        }

        # Update metadata_json
        meta_json = doc.setdefault("metadata_json", {})
        meta_json["word_count"] = quote_word_count

        if not dry_run:
            # Overwrite atom.json
            json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            # Remove redundant article.md from quote folder
            article_md_file = folder / "article.md"
            if article_md_file.exists():
                article_md_file.unlink()

        quotes_restored += 1

    print(f"\nMigration Results {'(DRY RUN)' if dry_run else ''}:", flush=True)
    print(f"  • Quotes cleanly restored to kind='quote': {quotes_restored}", flush=True)
    print(f"  • Dedicated articles created (kind='article'): {articles_created}", flush=True)
    print(f"  • URLs with pre-existing independent articles (skipped creation): {articles_skipped_existing}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split hybrid quote/article atoms into dedicated atoms.")
    parser.add_argument("--vault", default="vault", help="Path to vault directory")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without modifying files")
    args = parser.parse_args()

    vault_dir = Path(args.vault).resolve()
    run_split(vault_dir, dry_run=args.dry_run)
