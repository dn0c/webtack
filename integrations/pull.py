#!/usr/bin/env python3
"""
Webtack — Inbound Sync Orchestrator
Coordinates inbound sync from configured upstream integrations (Instapaper, Are.na).
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.instapaper.sync import sync_instapaper
from integrations.arena.sync import sync_arena


def pull_all(vault_dir: Path, service: str = "all", limit: int = 100, visibility: str = "public") -> int:
    """Run inbound pull for Instapaper, Are.na, or both."""
    vault_dir = Path(vault_dir).resolve()
    total = 0
    if service in ("all", "instapaper"):
        total += sync_instapaper(vault_dir, limit=limit, visibility=visibility)
    if service in ("all", "arena"):
        total += sync_arena(vault_dir, limit=limit, visibility=visibility)

    if total > 0:
        print(f"\n🎉 Total new atoms imported: {total}")
    else:
        print(f"\n⚡ Vault is up to date (0 new items to import).")
    return total


if __name__ == "__main__":
    vault = PROJECT_ROOT / "vault"
    service = sys.argv[1] if len(sys.argv) > 1 else "all"
    pull_all(vault, service=service)
