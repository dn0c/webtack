#!/usr/bin/env python3
"""
WideWeb — AI Enrichment & Are.na Sync Module
Provides automated vision-based alt text generation (via Gemini Flash)
and two-way synchronization with Are.na blocks.
"""

import os
import re
import json
import base64
import mimetypes
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_MCP_PATH = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"


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


def get_arena_token(vault_dir: Path = None) -> str | None:
    """Get Are.na API token from environment, vault config, or MCP settings."""
    token = os.environ.get("ARENA_API_TOKEN")
    if token:
        return token

    if vault_dir:
        cred_file = vault_dir / ".sync_credentials.json"
        if cred_file.exists():
            try:
                with open(cred_file, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    token = c.get("arena_api_token")
                    if token:
                        return token
            except Exception:
                pass

    if CONFIG_MCP_PATH.exists():
        try:
            with open(CONFIG_MCP_PATH, "r", encoding="utf-8") as f:
                mcp = json.load(f).get("mcpServers", {})
                auth_header = mcp.get("arena", {}).get("headers", {}).get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    return auth_header[7:].strip()
        except Exception:
            pass

    return None


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
    if alt in ("Are.na Block", "Visual asset", "Image"):
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
            "Do not start with 'image of' or 'picture of'. Be specific about subjects, style, colors, and setting."
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


def extract_arena_block_id(source_url: str = None, doc: dict = None, vault_dir: Path = None) -> str | None:
    """Extract Are.na block ID from source URL, metadata, or vault scan cache."""
    if source_url:
        m = re.search(r"are\.na/block/(\d+)", source_url)
        if m:
            return m.group(1)
        m_api = re.search(r"api\.are\.na/v3/blocks/(\d+)", source_url)
        if m_api:
            return m_api.group(1)

    if doc:
        meta = doc.get("metadata_json") or {}
        if isinstance(meta, dict) and meta.get("arena_block_id"):
            return str(meta["arena_block_id"])
        # Check provenance
        prov_src = doc.get("provenance", {}).get("source_url")
        if prov_src:
            m = re.search(r"are\.na/block/(\d+)", prov_src)
            if m:
                return m.group(1)

        # Check .arena_scan_cache.json if available
        aid = doc.get("id")
        if aid:
            v_dir = vault_dir or REPO_ROOT / "vault"
            cache_file = v_dir / ".arena_scan_cache.json"
            if cache_file.exists():
                try:
                    if not hasattr(extract_arena_block_id, "_cache_map"):
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cdata = json.load(f)
                            extract_arena_block_id._cache_map = {x["aid"]: str(x["bid"]) for x in cdata if x.get("bid")}
                    return extract_arena_block_id._cache_map.get(aid)
                except Exception:
                    pass

    return None


def push_arena_alt_text(block_id: str | int, alt_text: str, token: str = None) -> tuple[bool, str]:
    """Push alt text to an Are.na block if the user has permission to manage it."""
    if not token:
        token = get_arena_token()
    if not token:
        return False, "No Are.na API token available"

    block_id = str(block_id)
    url = f"https://api.are.na/v3/blocks/{block_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "WideWeb/1.0"
    }

    try:
        chk = requests.get(url, headers=headers, timeout=8)
        if chk.status_code != 200:
            return False, f"Are.na check returned HTTP {chk.status_code}"

        bdata = chk.json()
        can_manage = bdata.get("can", {}).get("manage", False)
        if not can_manage:
            return False, f"External block {block_id} (cannot manage)"

        up = requests.put(url, headers=headers, json={"alt_text": alt_text}, timeout=8)
        if up.status_code == 200:
            return True, f"Updated Are.na block {block_id}"
        return False, f"Are.na update returned HTTP {up.status_code}: {up.text[:100]}"
    except Exception as e:
        return False, f"Are.na sync error: {e}"


def enrich_atom_image(doc: dict, vault_dir: Path, push_to_arena: bool = True) -> tuple[bool, str | None, str | None]:
    """
    Enrich an atom's cover image with Gemini alt text if needed,
    and sync to Are.na if it belongs to an Are.na block.
    Returns (updated, new_alt_text, arena_sync_status).
    """
    vault_dir = Path(vault_dir).resolve()
    cover_img = doc.get("payload", {}).get("cover_image", {})
    if not isinstance(cover_img, dict):
        return False, None, None

    curr_alt = cover_img.get("alt_text")
    if not is_placeholder_alt(curr_alt):
        return False, curr_alt, None

    rel_path = cover_img.get("relative_path")
    if not rel_path:
        return False, None, None

    abs_path = vault_dir / rel_path
    if not abs_path.exists():
        return False, None, None

    # Generate alt text
    new_alt = generate_image_alt_text(abs_path)
    if not new_alt:
        return False, None, None

    # Update doc
    cover_img["alt_text"] = new_alt
    doc["payload"]["cover_image"] = cover_img
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()

    arena_status = None
    if push_to_arena:
        bid = extract_arena_block_id(doc.get("provenance", {}).get("source_url"), doc)
        if bid:
            ok, msg = push_arena_alt_text(bid, new_alt)
            arena_status = msg

    return True, new_alt, arena_status


def batch_enrich_vault(vault_dir: Path, limit: int = None, force: bool = False, push_to_arena: bool = True):
    """Scan vault database for images needing alt text, generate with Gemini, and sync to Are.na."""
    vault_dir = Path(vault_dir).resolve()
    db_path = vault_dir / "vault.db"
    if not db_path.exists():
        print("❌ vault.db not found!")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, cover_file_path, raw_json FROM atoms WHERE kind = 'image' AND cover_file_path IS NOT NULL")
    rows = c.fetchall()

    targets = []
    for r in rows:
        raw = r["raw_json"]
        doc = json.loads(raw)
        cover_img = doc.get("payload", {}).get("cover_image", {})
        alt = cover_img.get("alt_text") if isinstance(cover_img, dict) else None
        if force or is_placeholder_alt(alt):
            targets.append((r["id"], doc, r["cover_file_path"]))

    print(f"🔍 Found {len(targets)} image atoms to enrich (total images: {len(rows)})")
    if not targets:
        print("🎉 All image atoms already have rich alt text!")
        return

    if limit:
        targets = targets[:limit]

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_count = 0
    arena_synced_count = 0

    for aid, doc, cpath in targets:
        abs_img = vault_dir / cpath
        print(f"🖼️ [{aid}] Generating alt text...", end=" ", flush=True)
        new_alt = generate_image_alt_text(abs_img)
        if not new_alt:
            print("❌ Failed or skipped")
            continue

        doc["payload"]["cover_image"]["alt_text"] = new_alt
        doc["updated_at"] = now_iso

        # Write atom.json
        atom_json_path = (vault_dir / cpath).parent / "atom.json"
        try:
            with open(atom_json_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Failed writing atom.json: {e}")

        # Write DB
        with conn:
            conn.execute(
                "UPDATE atoms SET updated_at = ?, raw_json = ? WHERE id = ?",
                (now_iso, json.dumps(doc, ensure_ascii=False), aid)
            )
        updated_count += 1

        arena_info = ""
        if push_to_arena:
            bid = extract_arena_block_id(doc.get("provenance", {}).get("source_url"), doc)
            if bid:
                ok, msg = push_arena_alt_text(bid, new_alt)
                if ok:
                    arena_synced_count += 1
                    arena_info = f" | ☁️ Are.na: {msg}"
                else:
                    arena_info = f" | ℹ️ Are.na: {msg}"

        print(f"✅ {new_alt[:60]}...{arena_info}")

    print(f"\n🎉 Done! Enriched {updated_count} atoms (Are.na blocks synced: {arena_synced_count})")
