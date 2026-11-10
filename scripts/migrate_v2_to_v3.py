#!/usr/bin/env python3
"""
WebTack Schema Migration: v2 -> v3
Migrates vault atom.json files to WebTack v3:
1. Renames 'payload' layer to 'content'
2. Sets 'version': 3
3. Cleans up deprecated URL fields:
   - Consolidates canonical_url / destination_url into provenance.source_url
   - Removes provenance.canonical_url and provenance.author_url
   - Removes content.destination_url and cover_image.original_src_url
4. Updates SQLite database catalog
5. Regenerates vault/index.html
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import curate
import viewer


def migrate_atom_dict(doc: dict) -> tuple[dict, bool]:
    """
    Migrate a single atom document dictionary from v2 to v3.
    Returns (updated_doc, was_changed).
    """
    changed = False

    # 1. Version update
    if doc.get("version") != 3:
        doc["version"] = 3
        changed = True

    # 2. Rename payload -> content
    if "payload" in doc:
        payload_data = doc.pop("payload")
        if "content" not in doc:
            doc["content"] = payload_data
        else:
            # Merge if content already exists
            if isinstance(payload_data, dict) and isinstance(doc["content"], dict):
                for k, v in payload_data.items():
                    if k not in doc["content"]:
                        doc["content"][k] = v
        changed = True

    # Ensure content exists
    if "content" not in doc:
        doc["content"] = {
            "cover_image": None,
            "text": None,
            "article": None,
            "video": None,
            "file": None
        }
        changed = True

    content = doc.get("content")

    # 3. Rename provenance -> source & clean up URLs
    src_data = doc.pop("provenance", None)
    if src_data is not None:
        changed = True
        if "source" not in doc:
            doc["source"] = src_data
        else:
            if isinstance(src_data, dict) and isinstance(doc["source"], dict):
                for k, v in src_data.items():
                    if k not in doc["source"]:
                        doc["source"][k] = v

    if "source" not in doc:
        doc["source"] = {
            "source_url": None,
            "source_title": None,
            "site_name": None,
            "author": None,
            "published_at": None,
            "favicon": None,
            "capture_method": None,
            "capture_id": None,
            "capture_url": None
        }
        changed = True

    src = doc.get("source")
    if isinstance(src, dict):
        source_url = src.get("source_url")
        canonical_url = src.pop("canonical_url", None)
        author_url = src.pop("author_url", None)

        if canonical_url is not None:
            changed = True
        if author_url is not None:
            changed = True

        # Fallback to canonical_url if source_url is missing
        if not source_url and canonical_url:
            src["source_url"] = canonical_url
            changed = True

        # Fallback to content destination_url if still missing
        if isinstance(content, dict) and not src.get("source_url") and content.get("destination_url"):
            src["source_url"] = content.get("destination_url")
            changed = True

    # 4. Clean up content URLs
    if isinstance(content, dict):
        if "destination_url" in content:
            content.pop("destination_url", None)
            changed = True

        cover_img = content.get("cover_image")
        if isinstance(cover_img, dict) and "original_src_url" in cover_img:
            cover_img.pop("original_src_url", None)
            changed = True

    return doc, changed


def run_migration(vault_dir: Path, dry_run: bool = False, limit: int | None = None):
    vault_dir = Path(vault_dir).resolve()
    atoms_dir = vault_dir / "atoms"
    if not atoms_dir.exists():
        print(f"❌ Atoms directory not found: {atoms_dir}")
        return

    print(f"🚀 Scanning {atoms_dir} for atom.json files...")
    atom_files = list(atoms_dir.rglob("atom.json"))
    total_found = len(atom_files)
    print(f"📦 Found {total_found:,} atoms in vault.")

    if limit:
        atom_files = atom_files[:limit]
        print(f"ℹ️ Limiting execution to first {limit:,} atoms.")

    migrated_count = 0
    already_v3_count = 0
    error_count = 0

    start_time = time.time()

    for idx, fpath in enumerate(atom_files, 1):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                doc = json.load(f)

            updated_doc, changed = migrate_atom_dict(doc)

            if changed:
                migrated_count += 1
                if not dry_run:
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(updated_doc, f, indent=2, ensure_ascii=False)
            else:
                already_v3_count += 1

        except Exception as e:
            error_count += 1
            print(f"⚠️ Error migrating {fpath}: {e}")

        if idx % 1000 == 0 or idx == len(atom_files):
            elapsed = time.time() - start_time
            print(f"  [{idx:,}/{len(atom_files):,}] processed ({migrated_count:,} upgraded, {already_v3_count:,} unchanged) in {elapsed:.1f}s")

    elapsed = time.time() - start_time
    action_verb = "Would migrate" if dry_run else "Successfully migrated"
    print(f"\n✨ {action_verb} {migrated_count:,} atoms to Schema v3 in {elapsed:.2f}s.")
    if already_v3_count:
        print(f"✅ {already_v3_count:,} atoms were already up to date.")
    if error_count:
        print(f"⚠️ Encountered {error_count:,} errors.")

    if not dry_run and migrated_count > 0:
        print("\n🔄 Rebuilding SQLite catalog (vault.db)...")
        args = argparse.Namespace(vault=str(vault_dir))
        curate.cmd_reindex(args)

        print("\n🎨 Refreshing gallery viewer (vault/index.html)...")
        idx_path = viewer.generate_viewer(vault_dir)
        print(f"✅ Gallery regenerated: {idx_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate WebTack atoms from v2 (payload) to v3 (content + consolidated URLs)")
    parser.add_argument("--vault", default=str(curate.DEFAULT_VAULT), help="Path to WebTack vault directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate migration without modifying files")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N atoms")

    args = parser.parse_args()
    run_migration(Path(args.vault), dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
