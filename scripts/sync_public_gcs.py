#!/usr/bin/env python3
"""
Webtack — Google Cloud Storage Sync Wrapper
Delegates to integrations/gcs/sync.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.gcs.sync import sync_to_gcs, curate

if __name__ == "__main__":
    vault_dir = PROJECT_ROOT / "vault"
    manifest_only = "--manifest-only" in sys.argv
    sync_to_gcs(vault_dir, manifest_only=manifest_only)
