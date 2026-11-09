#!/usr/bin/env python3
"""
WideWeb — Universal AI Enrichment Module
Provides automated vision-based accessibility alt text generation via Gemini Flash
and updates canonical atom.json sidecars and SQLite index.
"""

import os
import re
import json
import base64
import mimetypes
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import requests

REPO_ROOT = Path(__file__).resolve().parent


def load_env(env_path: Path = None):
    """Load key-value pairs from .env into os.environ if not already set."""
    if env_path is None:
        env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


# Automatically load .env on module import
load_env()


def get_gemini_api_key() -> str | None:
    """Get Gemini API key from environment."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def is_placeholder_alt(alt: str | None) -> bool:
    """Detect if an alt text string is missing, generic, or a filename."""
    if not alt:
        return True
    alt = alt.strip()
    if not alt:
        return True
    if re.search(r"\.(png|jpg|jpeg|webp|gif|svg)$", alt, re.I):
        return True
    if alt.startswith("Image from ") or alt.startswith("Are.na - "):
        return True
    if alt in ("Are.na Block", "Visual asset", "Image", "Cover Image"):
        return True
    if alt.startswith("media_"):
        return True
    if len(alt) < 15 and " " not in alt:
        return True
    return False


def generate_image_alt_text(image_path: Path, model: str = "gemini-3.8-flash") -> str | None:
    """Generate concise, descriptive accessibility alt text using Gemini Flash."""
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    image_path = Path(image_path).resolve()
    if not image_path.exists():
        return None

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type or not mime_type.startswith("image/"):
        ext = image_path.suffix.lower().lstrip(".")
        if ext in ("jpg", "jpeg"):
            mime_type = "image/jpeg"
        elif ext == "png":
            mime_type = "image/png"
        elif ext == "gif":
            mime_type = "image/gif"
        elif ext == "webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

    try:
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        prompt = (
            "Provide a concise, highly descriptive accessibility alt text for this image (1-2 sentences). "
            "Do not start with 'image of' or 'picture of'. Be specific about subjects, style, colors, composition, and setting."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}}
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 150
            }
        }

        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            res_data = resp.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        else:
            print(f"⚠️ Gemini API returned HTTP {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"⚠️ Error generating alt text via Gemini: {e}")

    return None


def batch_enrich_vault(vault_dir: Path, limit: int = None, force: bool = False) -> int:
    """
    Scan image atoms in the vault for missing or placeholder alt text,
    generate new descriptions with Gemini Vision, and update atom.json and SQLite.
    """
    vault_dir = Path(vault_dir).resolve()
    db_path = vault_dir / "vault.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}. Run 'python3 curate.py reindex' first.")
        return 0

    api_key = get_gemini_api_key()
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment or .env. Please set it to use AI enrichment.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT id, created_at, atom_title, cover_image, raw_json
        FROM atoms
        WHERE kind = 'image'
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()

    to_process = []
    for r in rows:
        raw = r["raw_json"]
        doc = json.loads(raw) if raw else {}
        cover_info = (doc.get("content") or doc.get("payload") or {}).get("cover_image", {})
        alt = cover_info.get("alt_text")

        if force or is_placeholder_alt(alt):
            cpath = cover_info.get("relative_path") or cover_info.get("path")
            if not cpath:
                cpath = f"atoms/{r['created_at'][:4]}/{r['created_at'][5:7]}/{r['id']}/cover.jpg"
            full_img_path = vault_dir / cpath
            if full_img_path.exists():
                to_process.append({
                    "id": r["id"],
                    "title": r["atom_title"],
                    "image_path": full_img_path,
                    "atom_json_path": full_img_path.parent / "atom.json",
                    "doc": doc
                })

    print(f"🔍 Found {len(to_process)} image atoms requiring alt text enrichment.")
    if limit and limit > 0:
        to_process = to_process[:limit]
        print(f"⚡ Limiting run to {limit} atoms.")

    if not to_process:
        print("✅ All image atoms already have rich alt text descriptions!")
        conn.close()
        return 0

    updated_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, item in enumerate(to_process, 1):
        aid = item["id"]
        title = item["title"]
        img_path = item["image_path"]
        atom_json = item["atom_json_path"]
        doc = item["doc"]

        print(f"\n[{idx}/{len(to_process)}] Generating alt text for {aid} ({title[:35]}...):")
        alt = generate_image_alt_text(img_path)
        if not alt:
            print("   ⚠️ Failed to generate alt text. Skipping.")
            continue

        print(f"   ✨ Alt text: \"{alt}\"")

        # Update document
        content_tier = doc.setdefault("content", doc.setdefault("payload", {}))
        cover_tier = content_tier.setdefault("cover_image", {})
        cover_tier["alt_text"] = alt
        doc["updated_at"] = now_iso

        # Write to disk
        try:
            with open(atom_json, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ⚠️ Failed to write {atom_json}: {e}")
            continue

        # Update SQLite
        with conn:
            conn.execute(
                "UPDATE atoms SET updated_at = ?, raw_json = ? WHERE id = ?",
                (now_iso, json.dumps(doc, ensure_ascii=False), aid)
            )

        updated_count += 1

    conn.close()
    print(f"\n🎉 Successfully enriched {updated_count} image atoms with AI alt text!")
    return updated_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WideWeb AI Enrichment Tool")
    parser.add_argument("--vault", default="vault", help="Path to vault directory (default: vault)")
    parser.add_argument("--limit", type=int, default=None, help="Max images to enrich")
    parser.add_argument("--force", action="store_true", help="Re-generate alt text even if already present")
    args = parser.parse_args()

    batch_enrich_vault(Path(args.vault), limit=args.limit, force=args.force)
