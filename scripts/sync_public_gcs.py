#!/usr/bin/env python3
"""
WideWeb — Sync Public Assets to Google Cloud Storage (GCS)
Wrapper script for `python3 curate.py sync`.
Uploads images belonging to public atoms to gs://<bucket>/atoms/
and exports vault/export/curation_public.json for digital garden syndication.
"""

import sys
import types
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from curate import (
    DEFAULT_GCS_BUCKET,
    get_public_atoms,
    generate_curation_export,
    get_gcs_access_token,
    upload_manifest_to_gcs as upload_manifest,
    sync_assets_to_gcs,
    cmd_sync
)

VAULT_DIR = PROJECT_ROOT / "vault"
GCS_BUCKET = DEFAULT_GCS_BUCKET
GCS_BASE_URL = f"https://storage.googleapis.com/{GCS_BUCKET}"


def main():
    manifest_only = "--manifest-only" in sys.argv
    args = types.SimpleNamespace(
        vault=str(VAULT_DIR),
        bucket=GCS_BUCKET,
        manifest_only=manifest_only
    )
    cmd_sync(args)


if __name__ == "__main__":
    main()
