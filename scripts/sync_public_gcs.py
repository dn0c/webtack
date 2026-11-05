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


def get_gcs_access_token():
    """Retrieve and refresh OAuth access token from gcloud credentials.db."""
    import requests
    cred_db = Path.home() / ".config" / "gcloud" / "credentials.db"
    if not cred_db.exists():
        return None
    try:
        conn = sqlite3.connect(cred_db)
        c = conn.cursor()
        row = c.execute("SELECT account_id, value FROM credentials").fetchone()
        if not row:
            return None
        account_id, val = row
        cred = json.loads(val)
        token_resp = requests.post(
            cred["token_uri"],
            data={
                "client_id": cred["client_id"],
                "client_secret": cred["client_secret"],
                "refresh_token": cred["refresh_token"],
                "grant_type": "refresh_token"
            },
            timeout=10
        )
        if token_resp.status_code == 200:
            token_data = token_resp.json()
            access_token = token_data["access_token"]
            # Also update access_tokens.db so gcloud CLI remains authenticated
            try:
                import time
                atk_db = Path.home() / ".config" / "gcloud" / "access_tokens.db"
                if atk_db.exists():
                    atk_conn = sqlite3.connect(atk_db)
                    expiry = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 3600))
                    with atk_conn:
                        atk_conn.execute("REPLACE INTO access_tokens (account_id, access_token, token_expiry) VALUES (?, ?, ?)",
                                         (account_id, access_token, expiry))
            except Exception:
                pass
            return access_token
    except Exception as e:
        print(f"⚠️ Could not refresh token from credentials.db: {e}")
    return None


def upload_manifest():
    """Upload curation_public.json directly to GCS using the high-speed REST API."""
    import requests
    json_path = VAULT_DIR / "export" / "curation_public.json"
    if not json_path.exists():
        print(f"❌ {json_path} does not exist.")
        return

    print("🚀 Uploading curation_public.json to GCS root via REST API...")
    token = get_gcs_access_token()
    if token:
        upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name=curation_public.json"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=60"
        }
        with open(json_path, "rb") as f:
            resp = requests.post(upload_url, headers=headers, data=f, timeout=60)
        if resp.status_code == 200:
            print(f"✅ Published JSON manifest to {GCS_BASE_URL}/curation_public.json")
            return
        else:
            print(f"⚠️ REST upload returned {resp.status_code}, falling back to gcloud CLI...")

    # Fallback to gcloud CLI
    gcloud_bin = "/Users/drew/Documents/google-cloud-sdk/bin/gcloud"
    if not Path(gcloud_bin).exists():
        gcloud_bin = "gcloud"
    cp_cmd = [
        gcloud_bin, "--quiet", "storage", "cp",
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
