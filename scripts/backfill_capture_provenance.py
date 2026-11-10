#!/usr/bin/env python3
"""
WebTack — Backfill Capture Provenance
Populates capture_method, capture_id, and capture_url in the Source Layer
for all atoms in the vault, inferring from:
  1. vault/.arena_scan_cache.json (direct aid -> bid mapping)
  2. metadata_json.arena_block_id
  3. vault/import/arena_*.json (block source/image url -> block id)
  4. vault/.instapaper_bookmarks_cache.json (url -> bookmark id)
  5. tags ('instapaper', 'arena') & collection names
"""

import sys
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curate import get_db, generate_curation_export, upload_manifest_to_gcs, get_public_atoms, DEFAULT_GCS_BUCKET

VAULT_DIR = REPO_ROOT / "vault"
ARENA_SCAN_CACHE = VAULT_DIR / ".arena_scan_cache.json"
INSTAPAPER_CACHE = VAULT_DIR / ".instapaper_bookmarks_cache.json"
IMPORT_DIR = VAULT_DIR / "import"


def normalize_lookup_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


def main():
    print("🚀 Starting WebTack Capture Provenance Backfill...")

    conn = get_db(VAULT_DIR)

    # 1. Load Arena scan cache (aid -> bid)
    aid_to_bid = {}
    if ARENA_SCAN_CACHE.exists():
        try:
            with open(ARENA_SCAN_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("aid") and item.get("bid"):
                            aid_to_bid[item["aid"]] = str(item["bid"])
            print(f"📦 Loaded {len(aid_to_bid)} atom-to-block mappings from {ARENA_SCAN_CACHE.name}")
        except Exception as e:
            print(f"⚠️ Warning loading arena scan cache: {e}")

    # 2. Load Instapaper cache (url -> bookmark_id)
    url_to_instapaper_id = {}
    if INSTAPAPER_CACHE.exists():
        try:
            with open(INSTAPAPER_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("id") and item.get("url"):
                            nurl = normalize_lookup_url(item["url"])
                            if nurl:
                                url_to_instapaper_id[nurl] = str(item["id"])
            print(f"📦 Loaded {len(url_to_instapaper_id)} URL mappings from {INSTAPAPER_CACHE.name}")
        except Exception as e:
            print(f"⚠️ Warning loading instapaper cache: {e}")

    # 3. Load Are.na import channels (url -> block_id)
    url_to_arena_bid = {}
    if IMPORT_DIR.exists():
        import_files = list(IMPORT_DIR.glob("arena_*.json"))
        for ip in import_files:
            try:
                with open(ip, "r", encoding="utf-8") as f:
                    idata = json.load(f)
                blocks = (
                    idata.get("result", {}).get("data", [])
                    or idata.get("data", [])
                    or idata.get("contents", [])
                    or (idata if isinstance(idata, list) else [])
                )
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    bid = str(b.get("id")) if b.get("id") else None
                    if not bid:
                        continue
                    # Source URL
                    if b.get("source") and isinstance(b["source"], dict):
                        src = b["source"].get("url")
                        if src:
                            nurl = normalize_lookup_url(src)
                            if nurl:
                                url_to_arena_bid[nurl] = bid
                    # Image URLs
                    if b.get("image") and isinstance(b["image"], dict):
                        for k in ["original", "display", "thumb"]:
                            io = b["image"].get(k)
                            if isinstance(io, dict) and io.get("url"):
                                nurl = normalize_lookup_url(io["url"])
                                if nurl:
                                    url_to_arena_bid[nurl] = bid
                    # Attachment URL
                    if b.get("attachment") and isinstance(b["attachment"], dict):
                        att = b["attachment"].get("url")
                        if att:
                            nurl = normalize_lookup_url(att)
                            if nurl:
                                url_to_arena_bid[nurl] = bid
            except Exception as e:
                print(f"⚠️ Warning reading {ip.name}: {e}")
        print(f"📦 Loaded {len(url_to_arena_bid)} URL mappings from Are.na channel imports")

    # 4. Fetch all atoms from database
    rows = conn.execute("SELECT id, kind, created_at, source_url, destination_url, tags, collections, metadata, raw_json FROM atoms").fetchall()
    print(f"🔍 Analyzing {len(rows)} atoms in vault database...")

    stats = {
        "arena": 0,
        "instapaper": 0,
        "cli": 0,
        "mcp": 0,
        "total_updated": 0,
        "skipped_unchanged": 0
    }

    updates = []

    for r in rows:
        aid = r["id"]
        created_at = r["created_at"]
        tags = json.loads(r["tags"]) if r["tags"] else []
        collections = json.loads(r["collections"]) if r["collections"] else []
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}

        src_layer = raw.get("source") or raw.get("provenance") or {}
        existing_method = src_layer.get("capture_method")
        existing_id = src_layer.get("capture_id")
        existing_url = src_layer.get("capture_url")

        final_method = existing_method
        final_id = existing_id
        final_url = existing_url

        # Check sources if not fully populated or if currently generic 'cli' without ID
        if not final_method or not final_id or final_method == "cli":
            # Check 1: Are.na scan cache
            if aid in aid_to_bid:
                final_method = "arena"
                final_id = aid_to_bid[aid]
                final_url = f"https://www.are.na/block/{final_id}"

            # Check 2: metadata_json.arena_block_id
            elif meta.get("arena_block_id"):
                final_method = "arena"
                final_id = str(meta["arena_block_id"])
                final_url = f"https://www.are.na/block/{final_id}"

            # Check 3: Arena channel import lookup
            elif normalize_lookup_url(r["source_url"] or "") in url_to_arena_bid:
                final_method = "arena"
                final_id = url_to_arena_bid[normalize_lookup_url(r["source_url"] or "")]
                final_url = f"https://www.are.na/block/{final_id}"

            elif normalize_lookup_url(r["destination_url"] or "") in url_to_arena_bid:
                final_method = "arena"
                final_id = url_to_arena_bid[normalize_lookup_url(r["destination_url"] or "")]
                final_url = f"https://www.are.na/block/{final_id}"

            # Check 4: Instapaper lookup
            else:
                n_src = normalize_lookup_url(r["source_url"] or "")
                n_dest = normalize_lookup_url(r["destination_url"] or "")
                if n_src in url_to_instapaper_id:
                    final_method = "instapaper"
                    final_id = url_to_instapaper_id[n_src]
                    final_url = f"https://www.instapaper.com/read/{final_id}"
                elif n_dest in url_to_instapaper_id:
                    final_method = "instapaper"
                    final_id = url_to_instapaper_id[n_dest]
                    final_url = f"https://www.instapaper.com/read/{final_id}"
                elif "instapaper" in tags:
                    final_method = "instapaper"
                    final_id = None
                    final_url = None

                # Check 5: Arena tags / collection origin
                elif "arena" in tags or any("arena" in str(c).lower() for c in collections):
                    final_method = "arena"
                    final_id = None
                    final_url = None
                elif "are.na" in (r["source_url"] or "") or "are.na" in (r["destination_url"] or ""):
                    final_method = "arena"
                    m = re.search(r'/block/(\d+)', r["source_url"] or r["destination_url"] or "")
                    if m:
                        final_id = m.group(1)
                        final_url = f"https://www.are.na/block/{final_id}"

                # Default: Native capture via CLI
                else:
                    final_method = "cli"
                    final_id = None
                    final_url = None

        # Ensure capture_url is populated if we have capture_id
        if final_id and not final_url:
            if final_method == "arena":
                final_url = f"https://www.are.na/block/{final_id}"
            elif final_method == "instapaper":
                final_url = f"https://www.instapaper.com/read/{final_id}"

        # If it was imported from Are.na, make sure "are.na" is in tags
        curation = raw.setdefault("curation", {})
        cur_tags = curation.get("tags") or []
        tag_added = False
        if final_method == "arena" and "are.na" not in cur_tags and "arena" not in cur_tags:
            cur_tags.append("are.na")
            curation["tags"] = cur_tags
            tag_added = True

        # Check if anything changed
        if (final_method != existing_method or 
            str(final_id or '') != str(existing_id or '') or 
            str(final_url or '') != str(existing_url or '') or
            tag_added or
            "provenance" in raw):

            src_layer["capture_method"] = final_method
            src_layer["capture_id"] = str(final_id) if final_id is not None else None
            src_layer["capture_url"] = final_url
            raw["source"] = src_layer
            raw.pop("provenance", None)

            # Update on disk atom.json
            atom_path = VAULT_DIR / "atoms" / created_at[:4] / created_at[5:7] / aid / "atom.json"
            if atom_path.exists():
                try:
                    with open(atom_path, "r", encoding="utf-8") as af:
                        disk_doc = json.load(af)
                    d_src = disk_doc.setdefault("source", {})
                    d_src["capture_method"] = final_method
                    d_src["capture_id"] = str(final_id) if final_id is not None else None
                    d_src["capture_url"] = final_url
                    disk_doc.pop("provenance", None)
                    if final_method == "arena":
                        d_cur = disk_doc.setdefault("curation", {})
                        d_tags = d_cur.get("tags") or []
                        if "are.na" not in d_tags and "arena" not in d_tags:
                            d_tags.append("are.na")
                            d_cur["tags"] = d_tags
                    with open(atom_path, "w", encoding="utf-8") as af:
                        json.dump(disk_doc, af, indent=2, ensure_ascii=False)
                except Exception as de:
                    print(f"⚠️ Error writing {atom_path}: {de}")

            updates.append((json.dumps(raw, ensure_ascii=False), json.dumps(curation.get("tags", [])), aid))
            stats["total_updated"] += 1
            if final_method in stats:
                stats[final_method] += 1
        else:
            stats["skipped_unchanged"] += 1

    # Batch update SQLite database
    if updates:
        print(f"💾 Updating {len(updates)} records in SQLite database...")
        with conn:
            conn.executemany("UPDATE atoms SET raw_json = ?, tags = ? WHERE id = ?", updates)

    print("\n✅ Backfill Complete Summary:")
    print(f"   • Total atoms updated: {stats['total_updated']}")
    print(f"   • Captured via Are.na: {stats['arena']}")
    print(f"   • Captured via Instapaper: {stats['instapaper']}")
    print(f"   • Captured via CLI (Native): {stats['cli']}")
    print(f"   • Skipped (Already matching): {stats['skipped_unchanged']}")

    # Re-export public manifests and upload to GCS
    print("\n📦 Re-exporting curation manifests...")
    pub_rows = get_public_atoms(VAULT_DIR)
    generate_curation_export(VAULT_DIR, pub_rows, bucket=DEFAULT_GCS_BUCKET)
    upload_manifest_to_gcs(VAULT_DIR, bucket=DEFAULT_GCS_BUCKET)
    print("🚀 GCS sync complete!")


if __name__ == "__main__":
    main()
