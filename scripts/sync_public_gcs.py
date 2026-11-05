#!/usr/bin/env python3
"""
WideWeb — Sync Public Assets to Google Cloud Storage (GCS)
Uploads images belonging to public atoms to gs://wideweb-assets-drew/atoms/
and exports vault/export/curation_public.json for the Ghost digital garden.
"""

import sys
import os
import json
import sqlite3
import subprocess
from pathlib import Path

WIDEWEB_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = WIDEWEB_DIR / "vault"
GCS_BUCKET = "wideweb-assets-drew"
GCS_BASE_URL = f"https://storage.googleapis.com/{GCS_BUCKET}"


def get_public_atoms():
    conn = sqlite3.connect(VAULT_DIR / "vault.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, kind, created_at, atom_title, notes, tags, collections,
               destination_url, cover_file_path, text_content, source_url,
               author, metadata, raw_json
        FROM atoms
        WHERE visibility = 'public'
        ORDER BY created_at DESC
    """).fetchall()
    return rows


def generate_curation_export(rows):
    export_dir = VAULT_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    public_items = []
    for r in rows:
        tags = json.loads(r["tags"]) if r["tags"] else []
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        cover_rel = r["cover_file_path"]

        # GCS public URL if cover exists, otherwise fallback to original src
        cover_url = None
        if cover_rel:
            cover_url = f"{GCS_BASE_URL}/{cover_rel}"
        elif meta.get("cover_image", {}).get("original_src_url"):
            cover_url = meta["cover_image"]["original_src_url"]

        item = {
            "id": r["id"],
            "kind": r["kind"],
            "title": r["atom_title"] or "Untitled",
            "notes": r["notes"],
            "tags": tags,
            "date": r["created_at"][:10] if r["created_at"] else "",
            "author": r["author"],
            "destination_url": r["destination_url"],
            "source_url": r["source_url"],
            "cover_url": cover_url,
            "excerpt": (r["text_content"][:300] + "...") if r["text_content"] and len(r["text_content"]) > 300 else r["text_content"],
            "metadata": meta
        }
        public_items.append(item)

    out_file = export_dir / "curation_public.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(public_items, f, indent=2, ensure_ascii=False)

    print(f"📄 Generated {out_file} ({len(public_items)} public atoms)")
    return out_file


def upload_manifest():
    gcloud_bin = "/Users/drew/Documents/google-cloud-sdk/bin/gcloud"
    if not Path(gcloud_bin).exists():
        gcloud_bin = "gcloud"

    json_path = VAULT_DIR / "export" / "curation_public.json"
    if json_path.exists():
        print("🚀 Uploading curation_public.json to GCS root...")
        cp_cmd = [
            gcloud_bin, "storage", "cp",
            str(json_path),
            f"gs://{GCS_BUCKET}/curation_public.json",
            "--cache-control=public, max-age=60"
        ]
        res_json = subprocess.run(cp_cmd, capture_output=True, text=True)
        if res_json.returncode == 0:
            print(f"✅ Published JSON manifest to {GCS_BASE_URL}/curation_public.json")
        else:
            print(f"⚠️ JSON upload warning: {res_json.stderr}")


def sync_assets_to_gcs():
    print(f"🚀 Syncing public image assets to gs://{GCS_BUCKET}/atoms/ ...")
    gcloud_bin = "/Users/drew/Documents/google-cloud-sdk/bin/gcloud"
    if not Path(gcloud_bin).exists():
        gcloud_bin = "gcloud"

    # Exclude metadata, texts, notes, and private atoms
    exclude_regex = ".*(\\.json|\\.txt|\\.md|\\.DS_Store|atm_20261104210906_a7152e|atm_20261104210908_e2ecc1|atm_20261104210910_f82447|atm_20261104210911_9c6058|atm_20261104210912_f6a4da).*"

    cmd = [
        gcloud_bin, "storage", "rsync",
        str(VAULT_DIR / "atoms"),
        f"gs://{GCS_BUCKET}/atoms",
        "--recursive",
        f"--exclude={exclude_regex}"
    ]

    print("Running image sync...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("✅ Image assets sync complete!")
    else:
        print(f"⚠️ Image sync warning: {res.stderr}")


def main():
    rows = get_public_atoms()
    print(f"🔍 Found {len(rows)} public atoms in vault.")
    generate_curation_export(rows)
    # Upload manifest first so garden is instantly live with new data
    upload_manifest()
    # Then sync image assets
    if "--manifest-only" not in sys.argv:
        sync_assets_to_gcs()


if __name__ == "__main__":
    main()
