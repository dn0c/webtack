#!/usr/bin/env python3
"""
Webtack — Google Cloud Storage (GCS) Asset & Manifest Sync Integration
Uploads public atom media (cover images, attachments) to Google Cloud Storage
and exports curation_public.json to power public digital gardens (e.g. drewshannon.net/garden).
"""

import sys
import types
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import curate


def sync_to_gcs(vault_dir: Path, bucket: str = None, manifest_only: bool = False):
    vault_dir = Path(vault_dir).resolve()
    bucket_name = curate.get_or_prompt_bucket(bucket)
    if not bucket_name:
        sys.exit("❌ Error: No GCS bucket provided. Pass --bucket <name>, set WEBTACK_GCS_BUCKET in .env, or enter it at the prompt.")

    rows = curate.get_public_atoms(vault_dir)
    print(f"🔍 Found {len(rows)} public atoms in vault.")
    curate.generate_curation_export(vault_dir, rows, bucket=bucket_name)
    curate.upload_manifest_to_gcs(vault_dir, bucket=bucket_name)
    if not manifest_only:
        curate.sync_assets_to_gcs(vault_dir, bucket=bucket_name)
    print(f"✨ GCS sync complete for bucket: {bucket_name}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync Webtack public vault assets to Google Cloud Storage")
    parser.add_argument("--vault", default="vault", help="Path to vault directory (default: vault)")
    parser.add_argument("--bucket", default=None, help="GCS bucket name (overrides WEBTACK_GCS_BUCKET in .env)")
    parser.add_argument("--manifest-only", action="store_true", help="Only upload curation_public.json without rsyncing media files")
    args = parser.parse_args()

    sync_to_gcs(Path(args.vault), bucket=args.bucket, manifest_only=args.manifest_only)
