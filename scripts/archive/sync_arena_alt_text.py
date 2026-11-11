#!/usr/bin/env python3
"""
WebTack — Are.na Alt Text Sync Wrapper
Delegates to integrations/arena/sync_alt_text.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.arena.sync_alt_text import push_all_alt_texts

if __name__ == "__main__":
    vault_dir = PROJECT_ROOT / "vault"
    push_all_alt_texts(vault_dir)
