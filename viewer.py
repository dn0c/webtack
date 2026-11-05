#!/usr/bin/env python3
"""
WideWeb HTML Viewer & Local Capture Server
Builds a high-aesthetic, local-first masonry showcase for browsing, reading, and capturing atoms.
"""

import json
import os
import sqlite3
import sys
import types
import urllib.parse
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def get_atoms_data(vault_dir: Path):
    """Load all atoms and compute kind counts from vault.db."""
    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM atoms ORDER BY created_at DESC").fetchall()

    atoms_data = []
    kind_counts = {"all": len(rows), "article": 0, "bookmark": 0, "video": 0, "quote": 0, "note": 0, "image": 0, "file": 0, "link": 0}

    for r in rows:
        raw = json.loads(r["raw_json"])
        created_at = r["created_at"]
        folder = vault_dir / "atoms" / created_at[:4] / created_at[5:7] / r["id"]

        article_text = r["text_content"] if (r["kind"] == "article" or raw.get("kind") == "article") else None

        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        tags = json.loads(r["tags"]) if r["tags"] else []
        kind = raw.get("kind") or r["kind"] or raw.get("curation", {}).get("kind")
        if kind in kind_counts:
            kind_counts[kind] += 1

        visibility = r["visibility"] if "visibility" in r.keys() and r["visibility"] else raw.get("curation", {}).get("visibility", "public")

        cover_image_data = raw.get("payload", {}).get("cover_image") or {}
        alt_text = cover_image_data.get("alt_text")

        atoms_data.append({
            "id": r["id"],
            "kind": kind,
            "visibility": visibility,
            "title": r["atom_title"],
            "notes": r["notes"],
            "tags": tags,
            "alt_text": alt_text,
            "date": r["created_at"][:10],
            "created_at": r["created_at"],
            "destination_url": r["destination_url"],
            "source_url": r["source_url"],
            "author": r["author"],
            "cover_path": r["cover_file_path"],
            "metadata": meta,
            "article_markdown": article_text,
            "excerpt": r["text_content"],
            "folder_path": f"atoms/{created_at[:4]}/{created_at[5:7]}/{r['id']}",
            "raw": raw
        })
    return atoms_data, kind_counts


def generate_viewer(vault_dir: Path) -> Path:
    """Generate vault/index.html containing the standalone reactive masonry viewer with capture modal."""
    atoms_data, kind_counts = get_atoms_data(vault_dir)
    atoms_json_str = json.dumps(atoms_data)
    counts_json_str = json.dumps(kind_counts)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WideWeb Vault</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {{
      --bg: #FAF8F5;
      --card-bg: #FFFFFF;
      --text: #1C1B19;
      --muted: #797670;
      --border: #E8E5DF;
      --accent: #2B4C7E;
      --tag-bg: #F0EDE6;
      --tag-text: #4F4B43;
      --shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.02);
      --radius: 12px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #141413;
        --card-bg: #1F1E1B;
        --text: #F2EFE9;
        --muted: #9E9A91;
        --border: #2D2B27;
        --accent: #7EA6E0;
        --tag-bg: #2B2925;
        --tag-text: #C4BFB5;
        --shadow: 0 2px 6px rgba(0,0,0,0.25);
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 32px 24px;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{
      max-width: 1400px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      flex-direction: column;
      gap: 20px;
      margin-bottom: 32px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
    }}
    .top-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .logo-area {{
      display: flex;
      align-items: baseline;
      gap: 10px;
    }}
    .logo {{
      font-size: 26px;
      font-weight: 600;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      font-size: 14px;
      color: var(--muted);
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .nav-hub-btn {{
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
      padding: 8px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .nav-hub-btn:hover {{
      background: var(--tag-bg);
      border-color: var(--muted);
      transform: translateY(-1px);
    }}
    .export-dropdown {{
      position: relative;
      display: inline-block;
    }}
    .export-btn {{
      background: var(--tag-bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 8px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .export-btn:hover {{
      background: var(--border);
      color: var(--text);
      transform: translateY(-1px);
    }}
    .export-menu {{
      display: none;
      position: absolute;
      right: 0;
      top: calc(100% + 8px);
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.15);
      width: 290px;
      padding: 6px;
      z-index: 200;
    }}
    .export-menu.show {{
      display: block;
    }}
    .export-item {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      text-decoration: none;
      color: var(--text);
      transition: background 0.12s ease;
      cursor: pointer;
    }}
    .export-item:hover {{
      background: var(--tag-bg);
    }}
    .export-item-icon {{
      font-size: 16px;
      line-height: 1.2;
    }}
    .export-item-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.2;
    }}
    .export-item-desc {{
      font-size: 11px;
      color: var(--muted);
      margin-top: 3px;
      line-height: 1.3;
    }}
    .capture-btn {{
      background: var(--text);
      color: var(--bg);
      border: none;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: opacity 0.15s ease, transform 0.15s ease;
    }}
    .capture-btn:hover {{
      opacity: 0.9;
      transform: translateY(-1px);
    }}
    .stats-badge {{
      font-size: 13px;
      color: var(--muted);
      background: var(--tag-bg);
      padding: 6px 14px;
      border-radius: 20px;
    }}
    .controls {{
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: space-between;
    }}
    .filter-tabs {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .tab-btn:hover {{
      color: var(--text);
      border-color: var(--text);
    }}
    .tab-btn.active {{
      background: var(--text);
      color: var(--bg);
      border-color: var(--text);
    }}
    .tab-badge {{
      font-size: 11px;
      opacity: 0.8;
    }}
    .search-box {{
      position: relative;
      min-width: 260px;
    }}
    .search-box input {{
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 14px 8px 34px;
      border-radius: 20px;
      font-size: 13px;
      outline: none;
      transition: border-color 0.15s ease;
    }}
    .search-box input:focus {{
      border-color: var(--accent);
    }}
    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 13px;
      color: var(--muted);
    }}
    
    /* Masonry Layout */
    .masonry {{
      columns: 4 300px;
      column-gap: 20px;
    }}
    @media (max-width: 1000px) {{
      .masonry {{ columns: 2 280px; }}
    }}
    @media (max-width: 600px) {{
      .masonry {{ columns: 1 auto; }}
    }}
    
    .card {{
      break-inside: avoid;
      margin-bottom: 20px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
      cursor: pointer;
    }}
    .card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      border-color: var(--accent);
    }}
    .card-header {{
      padding: 14px 16px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      color: var(--muted);
    }}
    .kind-pill {{
      text-transform: uppercase;
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.05em;
      padding: 2px 8px;
      border-radius: 4px;
      background: var(--tag-bg);
      color: var(--tag-text);
    }}
    .kind-article {{ color: #2B6CB0; background: rgba(43,108,176,0.1); }}
    .kind-bookmark {{ color: #0D9488; background: rgba(13,148,136,0.1); }}
    .kind-link {{ color: #0D9488; background: rgba(13,148,136,0.1); }}
    .kind-video {{ color: #6B46C1; background: rgba(107,70,193,0.1); }}
    .kind-quote {{ color: #9B2C2C; background: rgba(155,44,44,0.1); }}
    .kind-note {{ color: #7B341E; background: rgba(123,52,30,0.1); }}
    .kind-image {{ color: #2C7A7B; background: rgba(44,122,123,0.1); }}

    .vis-badge {{
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.04em;
      padding: 1px 6px;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }}
    .vis-badge.vis-private {{
      background: rgba(229, 62, 62, 0.12);
      color: #E53E3E;
      border: 1px solid rgba(229, 62, 62, 0.25);
    }}
    .vis-badge.vis-shared {{
      background: rgba(214, 158, 46, 0.12);
      color: #D69E2E;
      border: 1px solid rgba(214, 158, 46, 0.25);
    }}
    .vis-badge.vis-public {{
      background: rgba(56, 161, 105, 0.12);
      color: #38A169;
      border: 1px solid rgba(56, 161, 105, 0.25);
    }}
    .vis-tab-btn {{
      background: transparent;
      border: none;
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      padding: 4px 10px;
      border-radius: 6px;
      transition: all 0.15s ease;
    }}
    .vis-tab-btn:hover {{
      color: var(--text);
    }}
    .vis-tab-btn.active {{
      background: var(--bg);
      color: var(--text);
      font-weight: 600;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    
    .card-cover {{
      width: 100%;
      display: block;
      background: var(--tag-bg);
      object-fit: cover;
    }}
    .card-body {{
      padding: 14px 16px;
      flex-grow: 1;
    }}
    .card-title {{
      font-size: 16px;
      font-weight: 600;
      line-height: 1.35;
      margin-bottom: 8px;
      letter-spacing: -0.01em;
    }}
    .card-title a {{
      color: inherit;
      text-decoration: none;
    }}
    .card-title a:hover {{
      text-decoration: underline;
    }}
    .quote-content {{
      font-family: 'Newsreader', Georgia, serif;
      font-size: 18px;
      line-height: 1.45;
      margin-bottom: 12px;
      font-style: italic;
      color: var(--text);
    }}
    .author-byline {{
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .card-notes {{
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
      margin-bottom: 12px;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .card-notes.markdown-body p, .card-notes.markdown-body ul, .card-notes.markdown-body ol {{
      margin: 0 0 6px 0;
    }}
    .card-notes.markdown-body p:last-child {{
      margin-bottom: 0;
    }}
    .card-notes.markdown-body a {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .card-notes.markdown-body code {{
      font-family: var(--font-mono);
      font-size: 11.5px;
      background: var(--tag-bg);
      padding: 1px 4px;
      border-radius: 3px;
    }}
    .meta-notes-banner .markdown-body p {{
      margin: 0 0 8px 0;
    }}
    .meta-notes-banner .markdown-body p:last-child {{
      margin-bottom: 0;
    }}
    .meta-notes-banner .markdown-body ul, .meta-notes-banner .markdown-body ol {{
      margin: 4px 0 8px 18px;
      padding: 0;
    }}
    .meta-notes-banner .markdown-body a {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .meta-notes-banner .markdown-body code {{
      font-family: var(--font-mono);
      font-size: 12px;
      background: rgba(0, 0, 0, 0.06);
      padding: 1px 5px;
      border-radius: 3px;
    }}
    .card-footer {{
      padding: 10px 16px 14px;
      border-top: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      font-size: 12px;
    }}
    .tags {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}
    .tag {{
      background: var(--tag-bg);
      color: var(--tag-text);
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 4px;
      text-decoration: none;
    }}
    .read-btn {{
      background: var(--accent);
      color: #FFF;
      border: none;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: opacity 0.15s ease;
    }}
    .read-btn:hover {{
      opacity: 0.9;
    }}
    .palette-dots {{
      display: flex;
      gap: 4px;
      align-items: center;
    }}
    .palette-dot {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 1px solid rgba(0,0,0,0.1);
    }}

    /* Dialog Modals */
    dialog {{
      max-width: 760px;
      width: 90%;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-bg);
      color: var(--text);
      box-shadow: 0 20px 40px rgba(0,0,0,0.2);
      padding: 0;
      margin: auto;
      overflow: hidden;
    }}
    dialog::backdrop {{
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(4px);
    }}
    .modal-header {{
      padding: 18px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      background: var(--card-bg);
      z-index: 10;
    }}
    .modal-close {{
      background: var(--tag-bg);
      border: none;
      color: var(--text);
      width: 32px;
      height: 32px;
      border-radius: 50%;
      font-size: 16px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .modal-body {{
      padding: 32px 36px 48px;
      max-height: 80vh;
      overflow-y: auto;
      font-family: 'Newsreader', Georgia, serif;
      font-size: 19px;
      line-height: 1.7;
    }}
    .modal-meta {{
      font-family: 'Inter', sans-serif;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 24px;
      display: flex;
      gap: 12px;
    }}
    .modal-body h1 {{ font-size: 32px; margin-bottom: 12px; line-height: 1.25; font-family: 'Newsreader', Georgia, serif; font-weight: 500; }}
    .modal-body h2 {{ font-size: 24px; margin-top: 32px; margin-bottom: 12px; font-weight: 500; }}
    .modal-body p {{ margin-bottom: 20px; }}
    .modal-body blockquote {{
      border-left: 3px solid var(--accent);
      padding-left: 20px;
      margin: 24px 0;
      font-style: italic;
      color: var(--muted);
    }}
    .modal-body img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      margin: 20px 0;
    }}

    /* Metadata Inspector Modal Styling */
    .meta-dialog-body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 13.5px;
      line-height: 1.5;
      padding: 24px 28px 36px;
      max-height: 80vh;
      overflow-y: auto;
    }}
    .meta-headline {{
      font-family: 'Newsreader', Georgia, serif;
      font-size: 24px;
      font-weight: 500;
      line-height: 1.3;
      margin-bottom: 8px;
      color: var(--text);
    }}
    .meta-byline {{
      font-size: 13px;
      color: var(--muted);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px 10px;
      margin-bottom: 18px;
    }}
    .meta-actions-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 20px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--border);
    }}
    .meta-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.15s ease;
      border: 1px solid var(--border);
      background: var(--tag-bg);
      color: var(--text);
    }}
    .meta-btn:hover {{
      border-color: var(--text);
    }}
    .meta-btn.primary {{
      background: var(--accent);
      color: #FFF;
      border-color: var(--accent);
    }}
    .meta-btn.primary:hover {{
      opacity: 0.9;
    }}
    .meta-asset-box {{
      display: flex;
      gap: 18px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      margin-bottom: 20px;
      align-items: flex-start;
    }}
    @media (max-width: 650px) {{
      .meta-asset-box {{ flex-direction: column; }}
    }}
    .meta-asset-thumb {{
      max-width: 220px;
      max-height: 160px;
      border-radius: 6px;
      object-fit: cover;
      border: 1px solid var(--border);
    }}
    .meta-asset-fields {{
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
    }}
    .meta-field-row {{
      display: flex;
      gap: 10px;
    }}
    .meta-field-label {{
      width: 85px;
      flex-shrink: 0;
      color: var(--muted);
      font-weight: 500;
    }}
    .meta-field-value {{
      color: var(--text);
      word-break: break-all;
    }}
    .meta-quote-banner {{
      font-family: 'Newsreader', Georgia, serif;
      font-size: 19px;
      line-height: 1.5;
      font-style: italic;
      padding: 16px 20px;
      background: var(--bg);
      border-left: 3px solid var(--accent);
      border-radius: 0 8px 8px 0;
      margin-bottom: 20px;
    }}
    .meta-notes-banner {{
      padding: 14px 16px;
      background: var(--tag-bg);
      border-radius: 8px;
      font-size: 13px;
      color: var(--tag-text);
      margin-bottom: 20px;
    }}
    .meta-notes-title {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    /* 4-Tier Schema Layout */
    .schema-tiers-container {{
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 24px;
    }}
    .schema-tier-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    .schema-tier-card:hover {{
      border-color: var(--accent);
    }}
    .tier-badge-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }}
    .tier-number-pill {{
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 2px 7px;
      border-radius: 4px;
    }}
    .tier-envelope .tier-number-pill {{
      background: var(--tag-bg);
      color: var(--muted);
      border: 1px solid var(--border);
    }}
    .tier-provenance .tier-number-pill {{
      background: rgba(180, 83, 9, 0.12);
      color: #B45309;
    }}
    .tier-curation .tier-number-pill {{
      background: rgba(43, 76, 126, 0.12);
      color: var(--accent);
    }}
    .tier-payload .tier-number-pill {{
      background: rgba(13, 148, 136, 0.12);
      color: #0D9488;
    }}
    @media (prefers-color-scheme: dark) {{
      .tier-provenance .tier-number-pill {{ color: #F59E0B; background: rgba(245, 158, 11, 0.18); }}
      .tier-curation .tier-number-pill {{ color: #93C5FD; background: rgba(147, 197, 253, 0.18); }}
      .tier-payload .tier-number-pill {{ color: #2DD4BF; background: rgba(45, 212, 191, 0.18); }}
    }}
    .tier-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }}
    .tier-tagline {{
      font-size: 11.5px;
      color: var(--muted);
      margin-left: auto;
    }}
    @media (max-width: 600px) {{
      .tier-tagline {{ display: none; }}
    }}
    .tier-content-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px 18px;
      font-size: 12.5px;
    }}
    @media (max-width: 600px) {{
      .tier-content-grid {{ grid-template-columns: 1fr; }}
    }}
    .tier-prop {{
      display: flex;
      gap: 8px;
      align-items: baseline;
      word-break: break-all;
    }}
    .tier-prop.full-width {{
      grid-column: 1 / -1;
    }}
    .tier-null {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      color: var(--muted);
      opacity: 0.7;
      font-style: italic;
      padding: 1px 6px;
      background: var(--tag-bg);
      border-radius: 4px;
      display: inline-block;
      letter-spacing: 0.02em;
    }}
    .payload-slots-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
      gap: 6px;
      margin-top: 10px;
    }}
    .payload-slot-badge {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 11px;
    }}
    .payload-slot-badge.active {{
      border-color: #0D9488;
      background: rgba(13, 148, 136, 0.08);
      color: #0D9488;
      font-weight: 600;
    }}
    .payload-slot-badge.inactive {{
      opacity: 0.55;
      color: var(--muted);
    }}
    .tier-k {{
      width: 100px;
      flex-shrink: 0;
      font-size: 10.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }}
    .tier-v {{
      color: var(--text);
      font-size: 12.5px;
    }}
    .spec-mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11.5px;
    }}
    .meta-json-details {{
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      margin-top: 14px;
    }}
    .meta-json-summary {{
      padding: 10px 16px;
      background: var(--tag-bg);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      user-select: none;
    }}
    .meta-json-summary:hover {{
      background: var(--border);
    }}
    .meta-json-pre {{
      margin: 0;
      padding: 16px;
      background: var(--bg);
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11.5px;
      line-height: 1.45;
      max-height: 360px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    /* Capture Form Styling */
    .capture-form {{
      padding: 24px 28px;
    }}
    .capture-tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }}
    .cap-tab-btn {{
      background: transparent;
      border: none;
      font-size: 14px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      padding: 6px 12px;
      border-radius: 6px;
      transition: all 0.15s ease;
    }}
    .cap-tab-btn.active {{
      background: var(--tag-bg);
      color: var(--text);
      font-weight: 600;
    }}
    .form-group {{
      margin-bottom: 16px;
    }}
    .form-group label {{
      display: block;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .form-group input, .form-group textarea {{
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 14px;
      font-family: inherit;
      outline: none;
      transition: border-color 0.15s ease;
    }}
    .form-group textarea {{
      resize: vertical;
      min-height: 90px;
    }}
    .form-group input:focus, .form-group textarea:focus {{
      border-color: var(--accent);
    }}
    .form-actions {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 24px;
    }}
    .submit-btn {{
      background: var(--accent);
      color: #FFF;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: opacity 0.15s ease;
    }}
    .submit-btn:hover {{ opacity: 0.9; }}
    .bookmarklet-box {{
      font-size: 12px;
      color: var(--muted);
    }}
    .bookmarklet-link {{
      display: inline-block;
      padding: 4px 10px;
      background: var(--tag-bg);
      color: var(--tag-text);
      border-radius: 6px;
      text-decoration: none;
      font-weight: 500;
      border: 1px dashed var(--muted);
      cursor: grab;
    }}
    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--text);
      color: var(--bg);
      padding: 12px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 4px 14px rgba(0,0,0,0.2);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 100;
    }}
    .toast.show {{
      transform: translateY(0);
      opacity: 1;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="top-bar">
        <div class="logo-area">
          <span class="logo">WideWeb</span>
          <span class="subtitle">local curation vault</span>
        </div>
        <div class="top-actions">
          <div class="stats-badge" id="statsBadge">{len(atoms_data)} items</div>
          <a href="export.html" class="nav-hub-btn" title="Open full Knowledge Exports & Data Portability Hub">📦 Export Center</a>
          <div class="export-dropdown" id="exportDropdown">
            <button class="export-btn" onclick="toggleExportMenu(event)">📥 Quick Export ▾</button>
            <div class="export-menu" id="exportMenu">
              <a href="/api/export?target=digest" download="vault_digest.md" class="export-item" onclick="handleExportClick(event, 'digest')">
                <span class="export-item-icon">🤖</span>
                <div>
                  <div class="export-item-title">NotebookLM Digest (.md)</div>
                  <div class="export-item-desc">All articles, notes, quotes & transcripts in 1 file</div>
                </div>
              </a>
              <a href="/api/export?target=obsidian" download="vault_obsidian.zip" class="export-item" onclick="handleExportClick(event, 'obsidian')">
                <span class="export-item-icon">🧠</span>
                <div>
                  <div class="export-item-title">Obsidian Archive (.zip)</div>
                  <div class="export-item-desc">Discrete notes with YAML frontmatter for PKM</div>
                </div>
              </a>
              <a href="/api/export?target=bookmarks-html" download="bookmarks.html" class="export-item" onclick="handleExportClick(event, 'bookmarks-html')">
                <span class="export-item-icon">🌐</span>
                <div>
                  <div class="export-item-title">Universal HTML Bookmarks (.html)</div>
                  <div class="export-item-desc">Netscape format for Chrome, Safari, Firefox, Arc</div>
                </div>
              </a>
              <a href="/api/export?target=readwise" download="readwise.csv" class="export-item" onclick="handleExportClick(event, 'readwise')">
                <span class="export-item-icon">⚡</span>
                <div>
                  <div class="export-item-title">Readwise CSV (.csv)</div>
                  <div class="export-item-desc">Highlights format for active recall review</div>
                </div>
              </a>
              <a href="/api/export?target=arena-csv" download="arena_export.csv" class="export-item" onclick="handleExportClick(event, 'arena-csv')">
                <span class="export-item-icon">🧱</span>
                <div>
                  <div class="export-item-title">Are.na CSV (.csv)</div>
                  <div class="export-item-desc">Format ready for Are.na channel import</div>
                </div>
              </a>
              <a href="/api/export?target=pinterest-csv" download="pinterest_pins.csv" class="export-item" onclick="handleExportClick(event, 'pinterest-csv')">
                <span class="export-item-icon">📌</span>
                <div>
                  <div class="export-item-title">Pinterest Bulk Pins (.csv)</div>
                  <div class="export-item-desc">Format for Pinterest bulk pin & video upload</div>
                </div>
              </a>
              <a href="/api/export?target=raindrop-csv" download="raindrop_export.csv" class="export-item" onclick="handleExportClick(event, 'raindrop-csv')">
                <span class="export-item-icon">💧</span>
                <div>
                  <div class="export-item-title">Raindrop.io CSV (.csv)</div>
                  <div class="export-item-desc">Format for Raindrop collections, tags & notes</div>
                </div>
              </a>
              <a href="export.html" class="export-item" style="border-top: 1px solid var(--border); margin-top: 4px; padding-top: 8px;">
                <span class="export-item-icon">✨</span>
                <div>
                  <div class="export-item-title" style="color: var(--accent);">View All 12 Formats in Hub →</div>
                  <div class="export-item-desc">BibTeX, RSS Feed, JSONL, llms.txt & more</div>
                </div>
              </a>
            </div>
          </div>
          <button class="capture-btn" id="openCaptureBtn" onclick="openCaptureModal()">+ Capture</button>
        </div>
      </div>
      <div class="controls">
        <div class="filter-tabs">
          <button class="tab-btn active" data-filter="all">All <span class="tab-badge" id="badge-all"></span></button>
          <button class="tab-btn" data-filter="article">Articles <span class="tab-badge" id="badge-article"></span></button>
          <button class="tab-btn" data-filter="bookmark">Bookmarks <span class="tab-badge" id="badge-bookmark"></span></button>
          <button class="tab-btn" data-filter="video">Videos <span class="tab-badge" id="badge-video"></span></button>
          <button class="tab-btn" data-filter="quote">Quotes <span class="tab-badge" id="badge-quote"></span></button>
          <button class="tab-btn" data-filter="note">Notes <span class="tab-badge" id="badge-note"></span></button>
          <button class="tab-btn" data-filter="image">Images <span class="tab-badge" id="badge-image"></span></button>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <div class="visibility-tabs" style="display: flex; gap: 2px; background: var(--tag-bg); padding: 3px; border-radius: 8px; border: 1px solid var(--border);">
            <button class="vis-tab-btn active" data-vis="all">All</button>
            <button class="vis-tab-btn" data-vis="public" title="Public (Open web projection)">🌐 Public</button>
            <button class="vis-tab-btn" data-vis="shared" title="Shared (Trusted circle / Family)">👥 Shared</button>
            <button class="vis-tab-btn" data-vis="private" title="Private (Local vault only)">🔒 Private</button>
          </div>
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" id="searchInput" placeholder="Search title, author, tag, text... (Press /)">
          </div>
        </div>
      </div>
    </header>

    <div class="masonry" id="cardGrid"></div>
  </div>

  <!-- Capture Dialog Modal -->
  <dialog id="captureModal" closedby="any" style="max-width: 580px;">
    <div class="modal-header">
      <h3 style="font-size: 16px; font-weight: 600;">Capture to WideWeb</h3>
      <button class="modal-close" onclick="document.getElementById('captureModal').close()">✕</button>
    </div>
    <div class="capture-form">
      <div class="capture-tabs">
        <button class="cap-tab-btn active" data-tab="article" onclick="switchCaptureTab('article')">📖 Article</button>
        <button class="cap-tab-btn" data-tab="bookmark" onclick="switchCaptureTab('bookmark')">🔖 Bookmark</button>
        <button class="cap-tab-btn" data-tab="video" onclick="switchCaptureTab('video')">🎬 Video</button>
        <button class="cap-tab-btn" data-tab="quote" onclick="switchCaptureTab('quote')">✍️ Quote</button>
        <button class="cap-tab-btn" data-tab="note" onclick="switchCaptureTab('note')">📝 Note</button>
        <button class="cap-tab-btn" data-tab="image" onclick="switchCaptureTab('image')">🎨 Image</button>
      </div>

      <!-- Link / URL Form -->
      <form id="linkForm" onsubmit="handleCaptureSubmit(event, activeUrlKind)">
        <div class="form-group">
          <label>URL</label>
          <input type="url" id="capUrl" placeholder="https://example.com/essay" required autofocus>
        </div>
        <div class="form-group">
          <label>Custom Title (Optional)</label>
          <input type="text" id="capLinkTitle" placeholder="Leave blank to auto-scrape">
        </div>
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="capLinkTags" placeholder="systems, design, essay">
        </div>
        <div class="form-actions">
          <div class="bookmarklet-box">
            Bookmarklet: <a class="bookmarklet-link" href="javascript:(function(){{const u=location.href,t=document.title,s=window.getSelection().toString();window.open('http://127.0.0.1:8080/?capture_url='+encodeURIComponent(u)+'&capture_title='+encodeURIComponent(t)+'&capture_quote='+encodeURIComponent(s),'_blank');}})();" onclick="alert('Drag this link to your browser bookmarks bar for 1-click capture from any tab!'); return false;" title="Drag to bookmarks bar">⚡ Save to WideWeb</a>
          </div>
          <button type="submit" class="submit-btn" id="capLinkSubmit">Save Link</button>
        </div>
      </form>

      <!-- Video Form -->
      <form id="videoForm" style="display: none;" onsubmit="handleCaptureSubmit(event, 'video')">
        <div class="form-group">
          <label>Video Stream URL (YouTube, Vimeo, etc.)</label>
          <input type="url" id="capVideoUrl" placeholder="https://www.youtube.com/watch?v=..." required>
        </div>
        <div class="form-group">
          <label>Custom Title (Optional)</label>
          <input type="text" id="capVideoTitle" placeholder="Leave blank to auto-fetch video title">
        </div>
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="capVideoTags" placeholder="interviews, music-gear, tech">
        </div>
        <div class="form-actions">
          <div style="font-size: 11px; color: var(--muted); line-height: 1.3;">
            ⚡ Auto-downloads poster thumbnail and fetches full spoken transcript subtitles for search & LLM digest.
          </div>
          <button type="submit" class="submit-btn" id="capVideoSubmit">Save Video</button>
        </div>
      </form>

      <!-- Quote Form -->
      <form id="quoteForm" style="display: none;" onsubmit="handleCaptureSubmit(event, 'quote')">
        <div class="form-group">
          <label>Quote Excerpt</label>
          <textarea id="capQuoteText" placeholder="Paste the verbatim quote here..." required></textarea>
        </div>
        <div class="form-group">
          <label>Author</label>
          <input type="text" id="capQuoteAuthor" placeholder="e.g. Dieter Rams, Paul Graham">
        </div>
        <div class="form-group">
          <label>Source URL (Optional)</label>
          <input type="url" id="capQuoteSource" placeholder="https://...">
        </div>
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="capQuoteTags" placeholder="design, philosophy">
        </div>
        <div class="form-actions">
          <div></div>
          <button type="submit" class="submit-btn" id="capQuoteSubmit">Save Quote</button>
        </div>
      </form>

      <!-- Note Form -->
      <form id="noteForm" style="display: none;" onsubmit="handleCaptureSubmit(event, 'note')">
        <div class="form-group">
          <label>Personal Thought or Memo</label>
          <textarea id="capNoteText" placeholder="Capture your reflection or original thought..." required></textarea>
        </div>
        <div class="form-group">
          <label>Title (Optional)</label>
          <input type="text" id="capNoteTitle" placeholder="Short memo title">
        </div>
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="capNoteTags" placeholder="ideas, strategy">
        </div>
        <div class="form-actions">
          <div></div>
          <button type="submit" class="submit-btn" id="capNoteSubmit">Save Note</button>
        </div>
      </form>

      <!-- Image Form -->
      <form id="imageForm" style="display: none;" onsubmit="handleCaptureSubmit(event, 'image')">
        <div class="form-group">
          <label>Image URL or Local File Path</label>
          <input type="text" id="capImageSrc" placeholder="https://.../photo.jpg or ~/Downloads/graphic.png" required>
        </div>
        <div class="form-group">
          <label>Custom Title (Optional)</label>
          <input type="text" id="capImageTitle" placeholder="Leave blank to use filename or auto-title">
        </div>
        <div class="form-group">
          <label>Source Web URL (Optional)</label>
          <input type="url" id="capImageSource" placeholder="https://example.com/original-article">
        </div>
        <div class="form-group">
          <label>Author / Creator (Optional)</label>
          <input type="text" id="capImageAuthor" placeholder="e.g. Graphic Designer, Photographer">
        </div>
        <div class="form-group">
          <label>Alt Text / Visual Description (Optional)</label>
          <input type="text" id="capImageAlt" placeholder="Accessibility description of what the image depicts">
        </div>
        <div class="form-group">
          <label>Notes (Optional)</label>
          <textarea id="capImageNotes" placeholder="Context or thoughts on why you saved this image..."></textarea>
        </div>
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="capImageTags" placeholder="design, architecture, art">
        </div>
        <div class="form-actions">
          <div style="font-size: 11px; color: var(--muted); line-height: 1.3;">
            ⚡ Generates visual blurhash preview, computes aspect ratio, and extracts 5-color palette.
          </div>
          <button type="submit" class="submit-btn" id="capImageSubmit">Save Image</button>
        </div>
      </form>
    </div>
  </dialog>

  <!-- Reader Dialog Modal -->
  <dialog id="readerModal" closedby="any">
    <div class="modal-header">
      <div id="modalMeta" class="modal-meta" style="margin-bottom:0;"></div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button class="meta-btn" onclick="openMetaFromReader()" style="padding: 4px 10px; font-size: 12px;">ℹ️ View Metadata</button>
        <button class="modal-close" id="closeModalBtn" onclick="document.getElementById('readerModal').close()">✕</button>
      </div>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </dialog>

  <!-- Metadata Inspector Dialog Modal -->
  <dialog id="metadataModal" closedby="any" style="max-width: 840px; width: 92%;">
    <div class="modal-header">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span id="metaKindPill" class="kind-pill"></span>
        <span id="metaIdPill" style="font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--muted); background: var(--tag-bg); padding: 2px 8px; border-radius: 4px;"></span>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button class="meta-btn" id="copyIdBtn" onclick="copyCurrentId()" title="Copy Atom ID">📋 Copy ID</button>
        <button class="modal-close" onclick="document.getElementById('metadataModal').close()">✕</button>
      </div>
    </div>
    <div class="meta-dialog-body" id="metadataModalBody"></div>
  </dialog>

  <div class="toast" id="toast">✨ Saved to WideWeb vault!</div>

  <script>
    const ATOMS = {atoms_json_str};
    const COUNTS = {counts_json_str};

    let activeFilter = 'all';
    let activeVisibility = 'all';
    let searchQuery = '';

    // Set badge counts
    function updateBadges() {{
      for (const [k, v] of Object.entries(COUNTS)) {{
        const b = document.getElementById(`badge-${{k}}`);
        if (b) b.textContent = `(${{v}})`;
      }}
      document.getElementById('statsBadge').textContent = `${{ATOMS.length}} items saved`;
    }}
    updateBadges();

    function renderCards() {{
      const grid = document.getElementById('cardGrid');
      grid.innerHTML = '';

      const filtered = ATOMS.filter(a => {{
        if (activeFilter !== 'all' && a.kind !== activeFilter) return false;
        if (activeVisibility !== 'all' && (a.visibility || 'public') !== activeVisibility) return false;
        if (searchQuery) {{
          const q = searchQuery.toLowerCase();
          const matchTitle = (a.title || '').toLowerCase().includes(q);
          const matchAuthor = (a.author || '').toLowerCase().includes(q);
          const matchExcerpt = (a.excerpt || '').toLowerCase().includes(q);
          const matchNotes = (a.notes || '').toLowerCase().includes(q);
          const matchTags = (a.tags || []).some(t => t.toLowerCase().includes(q));
          if (!matchTitle && !matchAuthor && !matchExcerpt && !matchNotes && !matchTags) return false;
        }}
        return true;
      }});

      if (filtered.length === 0) {{
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--muted);">No matching atoms found.</div>';
        return;
      }}

      filtered.forEach(atom => {{
        const card = document.createElement('div');
        card.className = `card card-${{atom.kind}}`;

        let coverHtml = '';
        if (atom.cover_path) {{
          const ratio = atom.metadata && atom.metadata.aspect_ratio ? `style="aspect-ratio: ${{atom.metadata.aspect_ratio}};"` : '';
          const altLabel = escapeHtml(atom.alt_text || atom.title || 'Visual asset');
          coverHtml = `<img class="card-cover" src="${{atom.cover_path}}" ${{ratio}} loading="lazy" alt="${{altLabel}}" title="${{altLabel}}">`;
        }}

        let bodyHtml = '';
        if (atom.kind === 'quote') {{
          bodyHtml = `
            <div class="card-body">
              <div class="quote-content">“${{escapeHtml(atom.excerpt || atom.title)}}”</div>
              ${{atom.author ? `<div class="author-byline">— ${{escapeHtml(atom.author)}}</div>` : ''}}
              ${{atom.notes ? `<div class="card-notes markdown-body">${{renderMarkdown(atom.notes)}}</div>` : ''}}
            </div>
          `;
        }} else if (atom.kind === 'note') {{
          bodyHtml = `
            <div class="card-body">
              <div class="card-title">${{escapeHtml(atom.title)}}</div>
              <div class="card-notes markdown-body" style="-webkit-line-clamp: 8;">${{renderMarkdown(atom.excerpt || '')}}</div>
            </div>
          `;
        }} else {{
          bodyHtml = `
            <div class="card-body">
              <div class="card-title">
                ${{atom.destination_url ? `<a href="${{atom.destination_url}}" target="_blank" rel="noopener">${{escapeHtml(atom.title)}}</a>` : escapeHtml(atom.title)}}
              </div>
              ${{atom.author ? `<div class="author-byline">${{escapeHtml(atom.author)}}</div>` : ''}}
              ${{atom.notes ? `<div class="card-notes markdown-body">${{renderMarkdown(atom.notes)}}</div>` : ''}}
            </div>
          `;
        }}

        let tagsHtml = (atom.tags || []).map(t => `<span class="tag">#${{t}}</span>`).join('');
        let extrasHtml = '';
        if (atom.kind === 'video' || (atom.raw && atom.raw.payload && atom.raw.payload.video && atom.raw.payload.video.embed_url)) {{
          extrasHtml = `<button class="read-btn" style="background:#6B46C1;" onclick="openVideoPlayer('${{atom.id}}')">▶ Play</button>`;
        }} else if (atom.kind === 'article' || atom.article_markdown) {{
          extrasHtml = `<button class="read-btn" onclick="openReader('${{atom.id}}')">📖 Read</button>`;
        }} else if (atom.kind === 'note') {{
          extrasHtml = `<button class="read-btn" style="background:#4A5568;" onclick="openReader('${{atom.id}}')">📝 Open</button>`;
        }} else if (atom.kind === 'bookmark' && atom.destination_url) {{
          extrasHtml = `<a class="read-btn" style="background:transparent; border:1px solid var(--border); color:var(--text); text-decoration:none;" href="${{atom.destination_url}}" target="_blank" rel="noopener">↗ Visit</a>`;
        }} else if (atom.metadata && atom.metadata.color_palette && atom.metadata.color_palette.length) {{
          extrasHtml = `<div class="palette-dots">` + atom.metadata.color_palette.map(c => `<div class="palette-dot" style="background:${{c}}" title="${{c}}"></div>`).join('') + `</div>`;
        }} else if (atom.metadata && atom.metadata.word_count) {{
          extrasHtml = `<span style="color:var(--muted);">${{atom.metadata.word_count}}w</span>`;
        }}

        let visBadgeHtml = '';
        if (atom.visibility === 'private') {{
          visBadgeHtml = `<span class="vis-badge vis-private" title="Private (Local vault only)">🔒 private</span>`;
        }} else if (atom.visibility === 'shared') {{
          visBadgeHtml = `<span class="vis-badge vis-shared" title="Shared (Trusted circle / Family)">👥 shared</span>`;
        }}

        card.innerHTML = `
          <div class="card-header">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span class="kind-pill kind-${{atom.kind}}">${{atom.kind}}</span>
              ${{visBadgeHtml}}
            </div>
            <span>${{atom.date}}</span>
          </div>
          ${{coverHtml}}
          ${{bodyHtml}}
          <div class="card-footer">
            <div class="tags">${{tagsHtml}}</div>
            <div>${{extrasHtml}}</div>
          </div>
        `;

        card.addEventListener('click', (e) => {{
          if (e.target.closest('a') || e.target.closest('button')) {{
            return;
          }}
          openMetadataModal(atom.id);
        }});

        grid.appendChild(card);
      }});
    }}

    function showToast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3500);
    }}

    function openCaptureModal() {{
      document.getElementById('captureModal').showModal();
    }}

    function toggleExportMenu(e) {{
      e.stopPropagation();
      const m = document.getElementById('exportMenu');
      m.classList.toggle('show');
    }}

    function handleExportClick(e, target) {{
      const isHttp = window.location.protocol.startsWith('http');
      if (!isHttp) {{
        if (target === 'json') {{
          e.preventDefault();
          const blob = new Blob([JSON.stringify(ATOMS, null, 2)], {{ type: 'application/json' }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'vault_backup.json';
          a.click();
          URL.revokeObjectURL(url);
          document.getElementById('exportMenu').classList.remove('show');
          showToast('💾 Exported vault_backup.json');
          return;
        }}
        alert('Digest, llms.txt, and CSV exports require running WideWeb with the local server:\\n\\nDouble-click "Launch WideWeb.command" or run:\\npython3 curate.py view --server');
        return;
      }}
      document.getElementById('exportMenu').classList.remove('show');
      showToast(`📥 Preparing ${{target}} download...`);
    }}

    window.addEventListener('click', (e) => {{
      const m = document.getElementById('exportMenu');
      if (m && !m.contains(e.target)) {{
        m.classList.remove('show');
      }}
    }});

    let activeUrlKind = 'article';
    function switchCaptureTab(tab) {{
      document.querySelectorAll('.cap-tab-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.querySelector(`.cap-tab-btn[data-tab="${{tab}}"]`);
      if (activeBtn) activeBtn.classList.add('active');

      const isUrl = (tab === 'article' || tab === 'bookmark');
      document.getElementById('linkForm').style.display = isUrl ? 'block' : 'none';
      document.getElementById('videoForm').style.display = tab === 'video' ? 'block' : 'none';
      document.getElementById('quoteForm').style.display = tab === 'quote' ? 'block' : 'none';
      document.getElementById('noteForm').style.display = tab === 'note' ? 'block' : 'none';
      document.getElementById('imageForm').style.display = tab === 'image' ? 'block' : 'none';

      if (isUrl) {{
        activeUrlKind = tab;
        document.getElementById('capLinkSubmit').textContent = tab === 'article' ? 'Save Article' : 'Save Bookmark';
        document.getElementById('capUrl').placeholder = tab === 'article' ? 'https://example.com/essay' : 'https://linear.app';
      }}
    }}

    function cleanTags(str) {{
      if (!str) return null;
      return str.split(',')
        .map(s => s.trim().replace(/^#+/, '').toLowerCase().replace(/[\\s_]+/g, '-').replace(/[^a-z0-9.-]/g, '').replace(/^-+|-+$/g, ''))
        .filter(Boolean)
        .join(',');
    }}

    async function handleCaptureSubmit(e, kind) {{
      e.preventDefault();
      
      const isHttp = window.location.protocol.startsWith('http');
      let payload = {{ kind }};
      let submitBtn = null;

      if (kind === 'article' || kind === 'bookmark' || kind === 'link') {{
        submitBtn = document.getElementById('capLinkSubmit');
        payload.url = document.getElementById('capUrl').value.trim();
        payload.title = document.getElementById('capLinkTitle').value.trim() || null;
        payload.tags = cleanTags(document.getElementById('capLinkTags').value);
      }} else if (kind === 'video') {{
        submitBtn = document.getElementById('capVideoSubmit');
        payload.url = document.getElementById('capVideoUrl').value.trim();
        payload.title = document.getElementById('capVideoTitle').value.trim() || null;
        payload.tags = cleanTags(document.getElementById('capVideoTags').value);
      }} else if (kind === 'quote') {{
        submitBtn = document.getElementById('capQuoteSubmit');
        payload.quote = document.getElementById('capQuoteText').value.trim();
        payload.author = document.getElementById('capQuoteAuthor').value.trim() || null;
        payload.source = document.getElementById('capQuoteSource').value.trim() || null;
        payload.tags = cleanTags(document.getElementById('capQuoteTags').value);
      }} else if (kind === 'note') {{
        submitBtn = document.getElementById('capNoteSubmit');
        payload.text = document.getElementById('capNoteText').value.trim();
        payload.title = document.getElementById('capNoteTitle').value.trim() || null;
        payload.tags = cleanTags(document.getElementById('capNoteTags').value);
      }} else if (kind === 'image') {{
        submitBtn = document.getElementById('capImageSubmit');
        payload.src = document.getElementById('capImageSrc').value.trim();
        payload.title = document.getElementById('capImageTitle').value.trim() || null;
        payload.source = document.getElementById('capImageSource').value.trim() || null;
        payload.author = document.getElementById('capImageAuthor').value.trim() || null;
        payload.alt = document.getElementById('capImageAlt').value.trim() || null;
        payload.notes = document.getElementById('capImageNotes').value.trim() || null;
        payload.tags = cleanTags(document.getElementById('capImageTags').value);
      }}

      if (!isHttp) {{
        alert('Instant web capture requires WideWeb to be running locally via:\\n\\npython3 curate.py view --server\\n\\n(Currently running as a static file:// document).');
        return;
      }}

      const origText = submitBtn.textContent;
      submitBtn.textContent = 'Saving...';
      submitBtn.disabled = true;

      try {{
        const resp = await fetch('/api/capture', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const res = await resp.json();
        if (res.success && res.atom) {{
          ATOMS.unshift(res.atom);
          COUNTS.all++;
          COUNTS[res.atom.kind] = (COUNTS[res.atom.kind] || 0) + 1;
          updateBadges();
          renderCards();
          document.getElementById('captureModal').close();
          showToast(`✨ Saved "${{res.atom.title}}" to vault!`);
          e.target.reset();
        }} else {{
          alert('Error saving atom: ' + (res.error || 'Unknown error'));
        }}
      }} catch (err) {{
        alert('Network error connecting to WideWeb backend: ' + err.message);
      }} finally {{
        submitBtn.textContent = origText;
        submitBtn.disabled = false;
      }}
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function truncateUrl(url, maxLen = 42) {{
      if (!url) return '';
      if (url.length <= maxLen) return url;
      return url.slice(0, maxLen) + '...';
    }}

    function copyCurrentId() {{
      if (!window.currentMetaAtomId) return;
      navigator.clipboard.writeText(window.currentMetaAtomId).then(() => {{
        const btn = document.getElementById('copyIdBtn');
        const orig = btn.textContent;
        btn.textContent = '✓ Copied!';
        setTimeout(() => btn.textContent = orig, 1800);
      }});
    }}

    function copyAtomJson(atomId) {{
      const atom = ATOMS.find(a => a.id === atomId);
      if (!atom || !atom.raw) return;
      navigator.clipboard.writeText(JSON.stringify(atom.raw, null, 2)).then(() => {{
        const btn = document.getElementById('metaCopyJsonBtn');
        if (btn) {{
          const orig = btn.textContent;
          btn.textContent = '✓ JSON Copied!';
          setTimeout(() => btn.textContent = orig, 1800);
        }}
      }});
    }}

    function openReaderFromMeta(atomId) {{
      document.getElementById('metadataModal').close();
      openReader(atomId);
    }}

    function formatSeconds(seconds) {{
      const s = Math.floor(seconds);
      const m = Math.floor(s / 60);
      const sRem = s % 60;
      const h = Math.floor(m / 60);
      const mRem = m % 60;
      if (h > 0) return `${{h}}:${{String(mRem).padStart(2, '0')}}:${{String(sRem).padStart(2, '0')}}`;
      return `${{m}}:${{String(sRem).padStart(2, '0')}}`;
    }}

    function openVideoFromMeta(atomId) {{
      document.getElementById('metadataModal').close();
      openVideoPlayer(atomId);
    }}

    function playVideoAtTime(atomId, seconds) {{
      document.getElementById('metadataModal').close();
      openVideoPlayer(atomId, seconds);
    }}

    function openVideoPlayer(atomId, startTime = 0) {{
      const atom = ATOMS.find(a => a.id === atomId);
      if (!atom) return;

      const video = (atom.raw && atom.raw.payload && atom.raw.payload.video) || {{}};
      let embedUrl = video.embed_url || (atom.destination_url ? atom.destination_url.replace("watch?v=", "embed/") : null);
      if (!embedUrl) return;

      if (startTime > 0) {{
        embedUrl += (embedUrl.includes('?') ? '&' : '?') + 'start=' + Math.floor(startTime) + '&autoplay=1';
      }} else {{
        embedUrl += (embedUrl.includes('?') ? '&' : '?') + 'autoplay=1';
      }}

      window.currentReaderAtomId = atomId;

      const modal = document.getElementById('readerModal');
      const body = document.getElementById('modalBody');
      const meta = document.getElementById('modalMeta');

      meta.innerHTML = `
        <span><strong>${{atom.author || 'YouTube'}}</strong></span>
        <span>•</span>
        <span>${{atom.date}}</span>
        <span>•</span>
        <span>Video (${{video.provider || 'Stream'}})${{startTime > 0 ? ` • From ${{formatSeconds(startTime)}}` : ''}}</span>
      `;

      body.innerHTML = `
        <h1 style="font-size:22px; margin-bottom:16px; font-family:'Inter', sans-serif; font-weight:600; line-height:1.3;">${{escapeHtml(atom.title)}}</h1>
        <div style="position:relative; padding-bottom:56.25%; height:0; overflow:hidden; border-radius:10px; margin-bottom:20px; background:#000; box-shadow:0 4px 16px rgba(0,0,0,0.2);">
          <iframe src="${{embedUrl}}" style="position:absolute; top:0; left:0; width:100%; height:100%; border:none;" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
        ${{atom.notes ? `<div class="meta-notes-banner" style="margin-top:16px;">${{escapeHtml(atom.notes)}}</div>` : ''}}
      `;
      modal.showModal();
    }}

    function openMetaFromReader() {{
      document.getElementById('readerModal').close();
      if (window.currentReaderAtomId) {{
        openMetadataModal(window.currentReaderAtomId);
      }}
    }}

    function renderMarkdown(md) {{
      if (!md) return '';
      if (window.marked && typeof window.marked.parse === 'function') {{
        return window.marked.parse(md);
      }}
      return `<pre style="white-space:pre-wrap;">${{escapeHtml(md)}}</pre>`;
    }}

    function openReader(atomId) {{
      const atom = ATOMS.find(a => a.id === atomId);
      const content = atom ? (atom.article_markdown || (atom.kind === 'note' ? atom.excerpt : null)) : null;
      if (!atom || !content) return;

      window.currentReaderAtomId = atomId;

      const modal = document.getElementById('readerModal');
      const body = document.getElementById('modalBody');
      const meta = document.getElementById('modalMeta');

      const wordCount = atom.metadata && atom.metadata.word_count ? `${{atom.metadata.word_count}} words` : '';
      const readTime = atom.metadata && atom.metadata.word_count ? `~${{Math.ceil(atom.metadata.word_count / 225)}} min read` : '';

      meta.innerHTML = `
        <span><strong>${{atom.author || (atom.kind === 'note' ? 'Personal Note' : 'Author')}}</strong></span>
        <span>•</span>
        <span>${{atom.date}}</span>
        ${{wordCount ? `<span>•</span><span>${{wordCount}}</span>` : ''}}
        ${{readTime ? `<span>•</span><span>${{readTime}}</span>` : ''}}
      `;

      let parsedHtml = renderMarkdown(content);
      body.innerHTML = `<h1>${{escapeHtml(atom.title)}}</h1>` + parsedHtml;
      modal.showModal();
    }}

    function renderVal(val, isMono = false, isUrl = false, truncateLen = 48) {{
      if (val === null || val === undefined || val === '') {{
        return '<span class="tier-null">null</span>';
      }}
      if (typeof val === 'boolean') {{
        return `<span class="spec-mono" style="color:${{val ? '#0D9488' : 'var(--muted)'}}; font-weight:600;">${{val}}</span>`;
      }}
      if (Array.isArray(val)) {{
        if (val.length === 0) return '<span class="tier-null">[] (empty)</span>';
        return `<div class="tags" style="display:inline-flex; flex-wrap:wrap; gap:4px;">${{val.map(v => `<span class="tag">#${{escapeHtml(v)}}</span>`).join('')}}</div>`;
      }}
      if (isUrl) {{
        return `<a href="${{escapeHtml(val)}}" target="_blank" rel="noopener" style="color:var(--accent); text-decoration:none;">${{truncateUrl(val, truncateLen)}} ↗</a>`;
      }}
      const s = String(val);
      return `<span class="${{isMono ? 'spec-mono' : ''}}">${{escapeHtml(s)}}</span>`;
    }}

    function openMetadataModal(atomId) {{
      const atom = ATOMS.find(a => a.id === atomId);
      if (!atom) return;

      window.currentMetaAtomId = atom.id;

      const raw = atom.raw || {{}};
      const curation = raw.curation || {{}};
      const provenance = raw.provenance || {{}};
      const payload = raw.payload || {{}};
      const metadata = atom.metadata || raw.metadata_json || {{}};

      const kindPill = document.getElementById('metaKindPill');
      kindPill.className = `kind-pill kind-${{atom.kind}}`;
      kindPill.textContent = atom.kind.toUpperCase();
      document.getElementById('metaIdPill').textContent = atom.id;

      const modalBody = document.getElementById('metadataModalBody');

      // Format dates
      const createdDateStr = atom.created_at || (raw.created_at ? raw.created_at.slice(0, 19).replace('T', ' ') + ' UTC' : atom.date);
      const updatedDateStr = raw.updated_at ? raw.updated_at.slice(0, 19).replace('T', ' ') + ' UTC' : null;
      const publishedDateStr = provenance.published_at || metadata.published_at || null;

      // Byline items
      const bylineParts = [];
      if (atom.author) {{
        bylineParts.push(`<span><strong>${{escapeHtml(atom.author)}}</strong></span>`);
      }}
      if (provenance.site_name) {{
        const fav = provenance.favicon ? `<img src="${{provenance.favicon}}" alt="" style="width:14px;height:14px;border-radius:2px;vertical-align:middle;margin-right:4px;">` : '';
        bylineParts.push(`<span>${{fav}}${{escapeHtml(provenance.site_name)}}</span>`);
      }}
      if (publishedDateStr) {{
        bylineParts.push(`<span>Published: ${{publishedDateStr}}</span>`);
      }}
      bylineParts.push(`<span>Captured: ${{createdDateStr}}</span>`);

      // Actions
      const wordCount = metadata.word_count || (payload.article && payload.article.word_count) || (payload.text && payload.text.word_count);
      const readTime = wordCount ? `~${{Math.ceil(wordCount / 225)}} min read` : '';
      const wordCountLabel = wordCount ? `${{wordCount.toLocaleString()}} words` : '';

      const actions = [];
      if (atom.kind === 'video' || (payload.video && payload.video.embed_url)) {{
        actions.push(`<button class="meta-btn primary" style="background:#6B46C1; border-color:#6B46C1;" onclick="openVideoFromMeta('${{atom.id}}')">▶ Watch Video</button>`);
      }}
      if (atom.article_markdown) {{
        actions.push(`<button class="meta-btn primary" onclick="openReaderFromMeta('${{atom.id}}')">📖 Read Full Article ${{wordCountLabel ? `(${{wordCountLabel}})` : ''}}</button>`);
      }}
      const targetUrl = atom.destination_url || atom.source_url || provenance.canonical_url;
      if (targetUrl) {{
        actions.push(`<a class="meta-btn" href="${{targetUrl}}" target="_blank" rel="noopener">🔗 Visit Original URL ↗</a>`);
      }}
      actions.push(`<button class="meta-btn" onclick="copyAtomJson('${{atom.id}}')" id="metaCopyJsonBtn">📋 Copy atom.json</button>`);

      // Cover image asset section
      let assetHtml = '';
      const coverImg = payload.cover_image || payload.asset || {{}};
      const hasCover = Boolean(atom.cover_path || coverImg.relative_path || coverImg.file);
      const cPath = atom.cover_path || coverImg.relative_path || coverImg.file;
      const dims = coverImg.dimensions ? `${{coverImg.dimensions.width}} × ${{coverImg.dimensions.height}}` : (metadata.dimensions ? `${{metadata.dimensions.width}} × ${{metadata.dimensions.height}}` : null);
      const ratio = (coverImg.aspect_ratio !== undefined && coverImg.aspect_ratio !== null) ? coverImg.aspect_ratio : (metadata && metadata.aspect_ratio !== undefined ? metadata.aspect_ratio : null);
      const blur = coverImg.blurhash || (metadata && metadata.blurhash) || null;
      const mime = coverImg.mime_type || (hasCover ? 'image/jpeg' : null);
      const hash = coverImg.hash || null;
      const palette = coverImg.color_palette || (metadata && metadata.color_palette) || null;
      const altText = coverImg.alt_text || atom.alt_text || null;
      const origSrc = coverImg.original_src_url || null;
      const pubUrl = coverImg.public_url || null;

      let paletteDots = '';
      if (palette && palette.length) {{
        paletteDots = `<div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">` +
          palette.map(c => `<span style="display:inline-flex; align-items:center; gap:4px; font-family:ui-monospace, monospace; font-size:11px;"><span style="display:inline-block; width:13px; height:13px; border-radius:50%; background:${{c}}; border:1px solid rgba(0,0,0,0.15);"></span>${{c}}</span>`).join(' ') +
          `</div>`;
      }}

      if (hasCover) {{
        const assetTitle = atom.kind === 'image' ? 'Image Asset Specification' : 'Cover Image Asset Specification';
        assetHtml = `
          <div class="meta-asset-box" style="margin-bottom: 14px;">
            <a href="${{cPath}}" target="_blank" title="Click to view full image">
              <img src="${{cPath}}" class="meta-asset-thumb" alt="${{escapeHtml(altText || atom.title)}}">
            </a>
            <div class="meta-asset-fields">
              <div style="font-weight:600; font-size:13px; margin-bottom:6px; color:var(--text);">${{assetTitle}}</div>
              <div class="meta-field-row"><span class="meta-field-label">File Path:</span><span class="meta-field-value spec-mono">${{renderVal(cPath, true)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Alt Text:</span><span class="meta-field-value">${{altText ? `“${{escapeHtml(altText)}}”` : renderVal(null)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Dimensions:</span><span class="meta-field-value">${{dims ? `${{dims}} (aspect: ${{ratio || '—'}})` : renderVal(null)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Format / MIME:</span><span class="meta-field-value">${{renderVal(mime, true)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Blurhash:</span><span class="meta-field-value spec-mono" style="font-size:11px;">${{renderVal(blur, true)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Palette:</span><div class="meta-field-value">${{paletteDots || renderVal(null)}}</div></div>
              <div class="meta-field-row"><span class="meta-field-label">SHA-256:</span><span class="meta-field-value spec-mono" style="font-size:11px;">${{renderVal(hash, true)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Original URL:</span><span class="meta-field-value">${{renderVal(origSrc, true, true, 38)}}</span></div>
              <div class="meta-field-row"><span class="meta-field-label">Public URL:</span><span class="meta-field-value">${{renderVal(pubUrl, true, true, 38)}}</span></div>
            </div>
          </div>
        `;
      }} else {{
        assetHtml = `
          <div style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; font-weight:600;">Cover Image Asset</span>
            <span class="tier-null">null (no visual asset attached)</span>
          </div>
        `;
      }}

      // TIER 1: SYSTEM ENVELOPE
      const schemaUrl = raw['$schema'] || 'https://raw.githubusercontent.com/dn0c/wideweb/main/schema/atom.schema.json';
      const tier1Html = `
        <div class="schema-tier-card tier-envelope">
          <div class="tier-badge-header">
            <span class="tier-number-pill">Tier 1</span>
            <span class="tier-title">System Envelope</span>
            <span class="tier-tagline">Storage, identity & immutability</span>
          </div>
          <div class="tier-content-grid">
            <div class="tier-prop"><span class="tier-k">Atom ID</span><span class="tier-v spec-mono">${{escapeHtml(atom.id)}}</span></div>
            <div class="tier-prop"><span class="tier-k">Kind</span><span class="tier-v"><span class="kind-pill kind-${{atom.kind}}">${{atom.kind}}</span></span></div>
            <div class="tier-prop"><span class="tier-k">Version</span><span class="tier-v spec-mono">v${{raw.version || 2}} (OpenCurate Spec)</span></div>
            <div class="tier-prop"><span class="tier-k">Schema URL</span><span class="tier-v">${{renderVal(schemaUrl, true, true, 36)}}</span></div>
            <div class="tier-prop" style="grid-column: 1 / -1;"><span class="tier-k">Storage Path</span><span class="tier-v spec-mono">${{escapeHtml(atom.folder_path || `atoms/.../${{atom.id}}`)}}</span></div>
            <div class="tier-prop"><span class="tier-k">Captured At</span><span class="tier-v">${{renderVal(createdDateStr)}}</span></div>
            <div class="tier-prop"><span class="tier-k">Updated At</span><span class="tier-v">${{renderVal(updatedDateStr)}}</span></div>
          </div>
        </div>
      `;

      // TIER 2: PROVENANCE LAYER
      const fav = provenance.favicon;
      const favDisplay = fav ? `<span style="display:inline-flex; align-items:center; gap:6px;"><img src="${{escapeHtml(fav)}}" alt="" style="width:14px;height:14px;border-radius:2px;vertical-align:middle;"><a href="${{escapeHtml(fav)}}" target="_blank" rel="noopener" style="color:var(--accent); text-decoration:none;">${{truncateUrl(fav, 32)}} ↗</a></span>` : renderVal(null);
      const siteDisplay = provenance.site_name ? escapeHtml(provenance.site_name) : renderVal(null);
      const authorDisplay = atom.author ? `<strong>${{escapeHtml(atom.author)}}</strong>` : renderVal(null);
      const authorUrlDisplay = provenance.author_url ? `<a href="${{escapeHtml(provenance.author_url)}}" target="_blank" rel="noopener" style="color:var(--accent); text-decoration:none;">${{truncateUrl(provenance.author_url, 40)}} ↗</a>` : renderVal(null);
      const sourceTitleDisplay = provenance.source_title ? escapeHtml(provenance.source_title) : renderVal(null);
      const sourceUrlDisplay = provenance.source_url ? `<a href="${{escapeHtml(provenance.source_url)}}" target="_blank" rel="noopener" style="color:var(--accent); text-decoration:none;">${{truncateUrl(provenance.source_url, 52)}} ↗</a>` : renderVal(null);
      const canonUrlDisplay = provenance.canonical_url ? `<a href="${{escapeHtml(provenance.canonical_url)}}" target="_blank" rel="noopener" style="color:var(--accent); text-decoration:none;">${{truncateUrl(provenance.canonical_url, 52)}} ↗</a>` : renderVal(null);
      const publishedDisplay = publishedDateStr ? escapeHtml(publishedDateStr) : renderVal(null);

      const tier2Html = `
        <div class="schema-tier-card tier-provenance">
          <div class="tier-badge-header">
            <span class="tier-number-pill">Tier 2</span>
            <span class="tier-title">Provenance Layer</span>
            <span class="tier-tagline">Origin, attribution & publisher source</span>
          </div>
          <div class="tier-content-grid">
            <div class="tier-prop"><span class="tier-k">Author</span><span class="tier-v">${{authorDisplay}}</span></div>
            <div class="tier-prop"><span class="tier-k">Author URL</span><span class="tier-v">${{authorUrlDisplay}}</span></div>
            <div class="tier-prop"><span class="tier-k">Publisher</span><span class="tier-v">${{siteDisplay}}</span></div>
            <div class="tier-prop"><span class="tier-k">Favicon</span><span class="tier-v">${{favDisplay}}</span></div>
            <div class="tier-prop" style="grid-column: 1 / -1;"><span class="tier-k">Source Title</span><span class="tier-v">${{sourceTitleDisplay}}</span></div>
            <div class="tier-prop" style="grid-column: 1 / -1;"><span class="tier-k">Source URL</span><span class="tier-v">${{sourceUrlDisplay}}</span></div>
            <div class="tier-prop" style="grid-column: 1 / -1;"><span class="tier-k">Canonical URL</span><span class="tier-v">${{canonUrlDisplay}}</span></div>
            <div class="tier-prop"><span class="tier-k">Published Date</span><span class="tier-v">${{publishedDisplay}}</span></div>
          </div>
        </div>
      `;

      // TIER 3: CURATION LAYER
      const collectionsVal = (curation.collections && curation.collections.length) ? escapeHtml(curation.collections.join(', ')) : renderVal(null);
      const favoriteVal = curation.favorite ? '<span class="spec-mono" style="color:#D97706; font-weight:600;">★ true (favorited)</span>' : '<span class="spec-mono" style="color:var(--muted);">false</span>';
      const tagsVal = (atom.tags && atom.tags.length) ? `<div class="tags" style="display:inline-flex; flex-wrap:wrap; gap:4px;">${{(atom.tags || []).map(t => `<span class="tag">#${{escapeHtml(t)}}</span>`).join('')}}</div>` : renderVal(null);

      const notesHtml = atom.notes ? `
        <div class="meta-notes-banner" style="margin-top: 14px; margin-bottom: 0;">
          <div class="meta-notes-title" style="font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; text-transform: lowercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 6px;">notes</div>
          <div class="markdown-body" style="font-size: 13px; line-height: 1.6;">${{renderMarkdown(atom.notes)}}</div>
        </div>
      ` : `
        <div class="tier-prop" style="grid-column: 1 / -1; margin-top: 4px;">
          <span class="tier-k">notes</span>
          <span class="tier-v">${{renderVal(null)}} <span style="font-size:11px; color:var(--muted);">(no notes attached)</span></span>
        </div>
      `;

      const tier3Html = `
        <div class="schema-tier-card tier-curation">
          <div class="tier-badge-header">
            <span class="tier-number-pill">Tier 3</span>
            <span class="tier-title">Curation Layer</span>
            <span class="tier-tagline">Editorial perspective, taxonomy & annotations</span>
          </div>
          <div class="tier-content-grid">
            <div class="tier-prop"><span class="tier-k">Curated Title</span><span class="tier-v" style="font-weight:600;">${{escapeHtml(atom.title || 'Untitled Atom')}}</span></div>
            <div class="tier-prop"><span class="tier-k">Visibility</span><span class="tier-v"><span class="vis-badge vis-${{atom.visibility || 'public'}}">${{atom.visibility === 'private' ? '🔒 ' : (atom.visibility === 'shared' ? '👥 ' : '🌐 ')}}${{atom.visibility || 'public'}}</span></span></div>
            <div class="tier-prop"><span class="tier-k">Favorite</span><span class="tier-v">${{favoriteVal}}</span></div>
            <div class="tier-prop"><span class="tier-k">Collections</span><span class="tier-v">${{collectionsVal}}</span></div>
            <div class="tier-prop" style="grid-column: 1 / -1;"><span class="tier-k">Tags</span><span class="tier-v">${{tagsVal}}</span></div>
            ${{!atom.notes ? notesHtml : ''}}
          </div>
          ${{atom.notes ? notesHtml : ''}}
        </div>
      `;

      // TIER 4: PAYLOAD LAYER
      let payloadContentHtml = '';

      if (atom.kind === 'quote' && (atom.excerpt || atom.title)) {{
        payloadContentHtml += `
          <div class="meta-quote-banner" style="margin-bottom: 14px;">
            “${{escapeHtml(atom.excerpt || atom.title)}}”
            ${{atom.author ? `<div style="font-size:14px; font-style:normal; margin-top:8px; color:var(--muted);">— ${{escapeHtml(atom.author)}}</div>` : ''}}
          </div>
        `;
      }} else if (atom.kind === 'note' && atom.excerpt) {{
        const noteFile = payload.text && payload.text.file ? payload.text.file : 'note.md';
        payloadContentHtml += `
          <div style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <div style="font-weight:600; font-size:13px; margin-bottom:2px;">Markdown Note Body</div>
              <div style="font-size:12px; color:var(--muted);">
                Stored in <code class="spec-mono">${{noteFile}}</code>${{wordCount ? ` • ${{wordCount}} words` : ''}}
              </div>
            </div>
            <button class="meta-btn primary" onclick="openReaderFromMeta('${{atom.id}}')">📝 Open Note</button>
          </div>
          <div class="markdown-body" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:12px 16px; margin-bottom:14px; font-size:13px; line-height:1.6;">
            ${{renderMarkdown(atom.excerpt)}}
          </div>
        `;
      }}

      if (payload.article || atom.article_markdown) {{
        const artFile = payload.article && payload.article.file ? payload.article.file : 'article.md';
        const artWordCount = payload.article && payload.article.word_count ? payload.article.word_count : (wordCount || 0);
        payloadContentHtml += `
          <div style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <div style="font-weight:600; font-size:13px; margin-bottom:2px;">Offline Article Text</div>
              <div style="font-size:12px; color:var(--muted);">
                Stored in <code class="spec-mono">${{artFile}}</code> • ${{artWordCount.toLocaleString()}} words ${{readTime ? `(${{readTime}})` : ''}}
              </div>
            </div>
            ${{atom.article_markdown ? `<button class="meta-btn primary" onclick="openReaderFromMeta('${{atom.id}}')">📖 Read Article</button>` : ''}}
          </div>
        `;
      }}

      if (payload.video || atom.kind === 'video') {{
        const vidProvider = (payload.video && payload.video.provider) || 'Video';
        const vidEmbed = payload.video && payload.video.embed_url;
        const transLang = (payload.video && payload.video.transcript_language) || (atom.metadata && atom.metadata.transcript_language) || 'en';
        const hasTranscript = (payload.video && payload.video.has_transcript) || (atom.metadata && atom.metadata.has_transcript) || Boolean(atom.excerpt);

        let transcriptBlockHtml = '';
        if (hasTranscript && atom.excerpt) {{
          const lines = atom.excerpt.split('\\n').filter(Boolean);
          const formattedLines = lines.map(line => {{
            if (line.startsWith('[') && line.indexOf(']') > 1) {{
              const closeIdx = line.indexOf(']');
              const timeStr = line.substring(1, closeIdx).trim();
              const textStr = escapeHtml(line.substring(closeIdx + 1).trim());
              const parts = timeStr.split(':').map(Number);
              const sec = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1];
              return `<div style="display:flex; gap:10px; margin-bottom:6px; align-items:baseline;">
                <button class="ts-pill" onclick="playVideoAtTime('${{atom.id}}', ${{sec}})" style="background:rgba(107,70,193,0.12); color:#6B46C1; border:none; padding:2px 7px; border-radius:4px; font-family:var(--font-mono); font-size:11px; cursor:pointer; font-weight:600; white-space:nowrap;" title="Jump video to ${{timeStr}}">▶ ${{timeStr}}</button>
                <span style="color:var(--text); font-size:12px; line-height:1.5;">${{textStr}}</span>
              </div>`;
            }}
            return `<div style="margin-bottom:4px; color:var(--text); font-size:12px;">${{escapeHtml(line)}}</div>`;
          }}).join('');

          transcriptBlockHtml = `
            <details style="margin-bottom:14px; background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px 14px;">
              <summary style="cursor:pointer; font-weight:600; font-size:12px; color:var(--text); display:flex; justify-content:space-between; align-items:center; user-select:none;">
                <span style="display:flex; align-items:center; gap:6px;">📜 Video Captions & Transcript</span>
                <span style="font-size:10px; text-transform:uppercase; background:rgba(107,70,193,0.15); color:#6B46C1; padding:2px 7px; border-radius:4px; font-weight:700;">${{escapeHtml(transLang)}} (${{lines.length}} lines)</span>
              </summary>
              <div style="margin-top:12px; max-height:260px; overflow-y:auto; padding-right:6px;">
                ${{formattedLines}}
              </div>
            </details>
          `;
        }}

        payloadContentHtml += `
          <div style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <div style="font-weight:600; font-size:13px; margin-bottom:2px;">${{escapeHtml(vidProvider)}} Stream</div>
              <div style="font-size:12px; color:var(--muted);">
                Embedded player ready • Channel: <strong>${{escapeHtml(atom.author || 'Creator')}}</strong>
              </div>
            </div>
            ${{vidEmbed ? `<button class="meta-btn primary" style="background:#6B46C1; border-color:#6B46C1;" onclick="openVideoFromMeta('${{atom.id}}')">▶ Watch Video</button>` : ''}}
          </div>
          ${{transcriptBlockHtml}}
        `;
      }}

      if (assetHtml) {{
        payloadContentHtml += assetHtml;
      }}

      // Universal 5-Slot Modular Showcase
      const slotCoverActive = Boolean(hasCover);
      const slotArticleActive = Boolean(payload.article || atom.article_markdown);
      const slotTextActive = Boolean(payload.text || atom.kind === 'quote' || atom.kind === 'note');
      const slotVideoActive = Boolean(payload.video || atom.kind === 'video');
      const slotFileActive = Boolean(payload.file);

      const slotsShowcaseHtml = `
        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border);">
          <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; letter-spacing: 0.05em;">
            Universal Modular Payload Slots
          </div>
          <div class="payload-slots-grid">
            <div class="payload-slot-badge ${{slotCoverActive ? 'active' : 'inactive'}}">
              <span>cover_image</span>
              <span>${{slotCoverActive ? '✓ set' : 'null'}}</span>
            </div>
            <div class="payload-slot-badge ${{slotArticleActive ? 'active' : 'inactive'}}">
              <span>article</span>
              <span>${{slotArticleActive ? '✓ set' : 'null'}}</span>
            </div>
            <div class="payload-slot-badge ${{slotTextActive ? 'active' : 'inactive'}}">
              <span>text</span>
              <span>${{slotTextActive ? '✓ set' : 'null'}}</span>
            </div>
            <div class="payload-slot-badge ${{slotVideoActive ? 'active' : 'inactive'}}">
              <span>video</span>
              <span>${{slotVideoActive ? '✓ set' : 'null'}}</span>
            </div>
            <div class="payload-slot-badge ${{slotFileActive ? 'active' : 'inactive'}}">
              <span>file</span>
              <span>${{slotFileActive ? '✓ set' : 'null'}}</span>
            </div>
          </div>
        </div>
      `;

      // Tier 4 / metadata_json overflow
      const rawMeta = raw.metadata_json || atom.metadata || {{}};
      const metaKeys = Object.keys(rawMeta);
      let metaJsonHtml = '';
      if (metaKeys.length) {{
        metaJsonHtml = `
          <div class="tier-prop" style="grid-column: 1 / -1; margin-top: 4px;">
            <span class="tier-k">metadata_json</span>
            <div class="tier-v" style="width: 100%;">
              <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:2px;">
                ${{metaKeys.map(k => `
                  <span class="spec-mono" style="background:var(--bg); border:1px solid var(--border); padding:2px 7px; border-radius:4px; font-size:11px;">
                    <strong style="color:var(--text);">${{escapeHtml(k)}}:</strong> ${{escapeHtml(typeof rawMeta[k] === 'object' && rawMeta[k] !== null ? JSON.stringify(rawMeta[k]) : String(rawMeta[k]))}}
                  </span>
                `).join('')}}
              </div>
            </div>
          </div>
        `;
      }} else {{
        metaJsonHtml = `
          <div class="tier-prop" style="grid-column: 1 / -1; margin-top: 4px;">
            <span class="tier-k">metadata_json</span>
            <span class="tier-v">${{renderVal(null)}} <span style="font-size:11px; color:var(--muted);">(no overflow metadata)</span></span>
          </div>
        `;
      }}

      const payloadMetricsHtml = `
        <div class="tier-content-grid" style="margin-top: 10px;">
          <div class="tier-prop" style="grid-column: 1 / -1;">
            <span class="tier-k">Destination URL</span>
            <span class="tier-v">${{targetUrl ? renderVal(targetUrl, false, true, 52) : renderVal(null)}}</span>
          </div>
          <div class="tier-prop">
            <span class="tier-k">Total Words</span>
            <span class="tier-v">${{wordCount ? `${{wordCount.toLocaleString()}} words ${{readTime ? `(${{readTime}})` : ''}}` : renderVal(null)}}</span>
          </div>
          <div class="tier-prop">
            <span class="tier-k">Text File</span>
            <span class="tier-v spec-mono">${{(payload.text && payload.text.file) ? renderVal(payload.text.file, true) : renderVal(null)}}</span>
          </div>
          ${{metaJsonHtml}}
        </div>
      `;

      const tier4Html = `
        <div class="schema-tier-card tier-payload">
          <div class="tier-badge-header">
            <span class="tier-number-pill">Tier 4</span>
            <span class="tier-title">Payload Layer</span>
            <span class="tier-tagline">Offline assets, content body & extracted metrics</span>
          </div>
          ${{payloadContentHtml}}
          ${{payloadMetricsHtml}}
          ${{slotsShowcaseHtml}}
        </div>
      `;

      // Raw JSON
      const rawJsonFormatted = JSON.stringify(raw, null, 2);

      modalBody.innerHTML = `
        <div>
          <h2 class="meta-headline">${{escapeHtml(atom.title || 'Untitled Atom')}}</h2>
          <div class="meta-byline">${{bylineParts.join(' ')}}</div>
        </div>

        <div class="meta-actions-bar">
          ${{actions.join(' ')}}
        </div>

        <div class="schema-tiers-container">
          ${{tier1Html}}
          ${{tier2Html}}
          ${{tier3Html}}
          ${{tier4Html}}
        </div>

        <details class="meta-json-details">
          <summary class="meta-json-summary">
            <span>{{ }} Full <code>atom.json</code> Spec</span>
            <span style="font-size:11px; font-weight:500; color:var(--muted);">Click to inspect raw file</span>
          </summary>
          <pre class="meta-json-pre"><code>${{escapeHtml(rawJsonFormatted)}}</code></pre>
        </details>
      `;

      document.getElementById('metadataModal').showModal();
    }}

    // Check URL parameters for bookmarklet pre-fill
    window.addEventListener('DOMContentLoaded', () => {{
      const params = new URLSearchParams(window.location.search);
      if (params.get('capture_url')) {{
        openCaptureModal();
        switchCaptureTab('link');
        document.getElementById('capUrl').value = params.get('capture_url');
        if (params.get('capture_title')) {{
          document.getElementById('capLinkTitle').value = params.get('capture_title');
        }}
      }} else if (params.get('capture_quote')) {{
        openCaptureModal();
        switchCaptureTab('quote');
        document.getElementById('capQuoteText').value = params.get('capture_quote');
        if (params.get('capture_url')) {{
          document.getElementById('capQuoteSource').value = params.get('capture_url');
        }}
      }}
    }});

    // Keyboard shortcuts ('c' to capture, '/' to search, 'Esc' to close)
    window.addEventListener('keydown', (e) => {{
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'c' || e.key === 'C') {{
        e.preventDefault();
        openCaptureModal();
      }} else if (e.key === '/') {{
        e.preventDefault();
        document.getElementById('searchInput').focus();
      }}
    }});

    // Filter clicks
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        renderCards();
      }});
    }});

    // Visibility filter clicks
    document.querySelectorAll('.vis-tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.vis-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeVisibility = btn.dataset.vis;
        renderCards();
      }});
    }});

    // Search input
    document.getElementById('searchInput').addEventListener('input', (e) => {{
      searchQuery = e.target.value.trim();
      renderCards();
    }});

    // Close on backdrop click
    ['readerModal', 'captureModal', 'metadataModal'].forEach(id => {{
      document.getElementById(id).addEventListener('click', (e) => {{
        const dialog = document.getElementById(id);
        const rect = dialog.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {{
          dialog.close();
        }}
      }});
    }});

    renderCards();
  </script>
</body>
</html>
"""

    index_html_path = vault_dir / "index.html"
    with open(index_html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    generate_export_page(vault_dir)
    return index_html_path


def generate_export_page(vault_dir: Path) -> Path:
    """Generate vault/export.html: the dedicated Knowledge Exports & Data Portability Hub."""
    atoms_data, kind_counts = get_atoms_data(vault_dir)
    total_items = len(atoms_data)
    atoms_json_str = json.dumps(atoms_data)

    export_html_path = vault_dir / "export.html"
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WideWeb — Data Portability & Knowledge Exports</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #FAF8F5;
      --card-bg: #FFFFFF;
      --text: #1C1B19;
      --muted: #797670;
      --border: #E8E5DF;
      --accent: #2B4C7E;
      --tag-bg: #F0EDE6;
      --tag-text: #4F4B43;
      --shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.02);
      --radius: 12px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #141413;
        --card-bg: #1F1E1B;
        --text: #F2EFE9;
        --muted: #9E9A91;
        --border: #2D2B27;
        --accent: #7EA6E0;
        --tag-bg: #2B2925;
        --tag-text: #C4BFB5;
        --shadow: 0 2px 6px rgba(0,0,0,0.25);
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 32px 24px 80px;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{
      max-width: 1240px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 32px;
    }}
    .top-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }}
    .logo-area {{
      display: flex;
      align-items: baseline;
      gap: 12px;
    }}
    .logo {{
      font-family: 'Newsreader', serif;
      font-size: 28px;
      font-weight: 500;
      letter-spacing: -0.5px;
      text-decoration: none;
      color: var(--text);
    }}
    .subtitle {{
      font-size: 14px;
      color: var(--muted);
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .back-btn {{
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .back-btn:hover {{
      background: var(--tag-bg);
      border-color: var(--muted);
      transform: translateY(-1px);
    }}
    .stats-badge {{
      font-size: 13px;
      color: var(--muted);
      background: var(--tag-bg);
      padding: 6px 14px;
      border-radius: 20px;
    }}

    .hero-banner {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 36px 40px;
      margin-bottom: 32px;
      box-shadow: var(--shadow);
    }}
    .hero-title {{
      font-family: 'Newsreader', serif;
      font-size: 34px;
      font-weight: 500;
      letter-spacing: -0.5px;
      margin-bottom: 12px;
      line-height: 1.2;
    }}
    .hero-desc {{
      font-size: 15px;
      color: var(--muted);
      max-width: 880px;
      line-height: 1.6;
    }}
    .hero-stats-row {{
      display: flex;
      gap: 24px;
      margin-top: 24px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      flex-wrap: wrap;
    }}
    .hero-stat {{
      display: flex;
      flex-direction: column;
    }}
    .hero-stat-val {{
      font-size: 20px;
      font-weight: 600;
      color: var(--text);
    }}
    .hero-stat-lbl {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    .controls {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }}
    .filter-tabs {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid var(--border);
      padding: 7px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .tab-btn:hover {{
      color: var(--text);
      background: var(--tag-bg);
    }}
    .tab-btn.active {{
      background: var(--text);
      color: var(--bg);
      border-color: var(--text);
    }}
    .search-box {{
      position: relative;
      width: 320px;
    }}
    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 14px;
      color: var(--muted);
    }}
    .search-box input {{
      width: 100%;
      padding: 9px 14px 9px 36px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 20px;
      font-size: 13px;
      color: var(--text);
      outline: none;
      transition: border-color 0.15s ease;
    }}
    .search-box input:focus {{
      border-color: var(--accent);
    }}

    .formats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(370px, 1fr));
      gap: 20px;
    }}
    .format-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }}
    .format-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(0,0,0,0.06);
      border-color: var(--muted);
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .card-icon-title {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .format-icon {{
      font-size: 26px;
      line-height: 1;
    }}
    .format-title {{
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.2;
    }}
    .format-badges {{
      display: flex;
      gap: 6px;
      align-items: center;
    }}
    .ext-badge {{
      font-family: 'JetBrains Mono', ui-monospace, monospace;
      font-size: 11px;
      font-weight: 600;
      background: var(--tag-bg);
      color: var(--tag-text);
      padding: 2px 7px;
      border-radius: 6px;
      border: 1px solid var(--border);
    }}
    .cat-badge {{
      font-size: 11px;
      color: var(--accent);
      background: rgba(43, 76, 126, 0.08);
      padding: 2px 8px;
      border-radius: 6px;
      font-weight: 500;
    }}
    @media (prefers-color-scheme: dark) {{
      .cat-badge {{
        background: rgba(126, 166, 224, 0.15);
      }}
    }}
    .format-desc {{
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 16px;
    }}
    .format-included {{
      font-size: 12px;
      background: var(--tag-bg);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 16px;
      color: var(--tag-text);
      line-height: 1.4;
    }}
    .format-included strong {{
      color: var(--text);
    }}
    .tool-pills {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    .tool-pill {{
      font-size: 11px;
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 2px 8px;
      border-radius: 12px;
    }}
    .card-actions {{
      border-top: 1px solid var(--border);
      padding-top: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .dl-btn {{
      background: var(--text);
      color: var(--bg);
      border: none;
      padding: 9px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: opacity 0.15s ease, transform 0.15s ease;
      width: 100%;
      text-decoration: none;
    }}
    .dl-btn:hover {{
      opacity: 0.9;
      transform: translateY(-1px);
    }}
    .cli-box {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--tag-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-family: 'JetBrains Mono', ui-monospace, monospace;
      font-size: 11px;
    }}
    .cli-text {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--tag-text);
      margin-right: 8px;
    }}
    .cli-copy {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 4px;
      cursor: pointer;
      transition: background 0.15s ease;
      flex-shrink: 0;
    }}
    .cli-copy:hover {{
      background: var(--border);
    }}

    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--text);
      color: var(--bg);
      padding: 12px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 4px 14px rgba(0,0,0,0.2);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 100;
    }}
    .toast.show {{
      transform: translateY(0);
      opacity: 1;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="top-bar">
        <div class="logo-area">
          <a href="index.html" class="logo">WideWeb</a>
          <span class="subtitle">data portability hub</span>
        </div>
        <div class="top-actions">
          <div class="stats-badge">{total_items} items in vault</div>
          <a href="index.html" class="back-btn">← Back to Gallery</a>
        </div>
      </div>

      <div class="hero-banner">
        <h1 class="hero-title">Knowledge Exports & Data Portability</h1>
        <p class="hero-desc">
          WideWeb is built on the Payload Sidecar pattern: files on your local drive are the canonical source of truth. Your knowledge is never trapped inside proprietary cloud databases or walled gardens. Export your curated library into open standards for AI synthesis, personal knowledge management, browsers, and research.
        </p>
        <div class="hero-stats-row">
          <div class="hero-stat">
            <span class="hero-stat-val">12 Formats</span>
            <span class="hero-stat-lbl">Active Export Targets</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-val">{kind_counts.get('article', 0)}</span>
            <span class="hero-stat-lbl">Articles</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-val">{kind_counts.get('video', 0)}</span>
            <span class="hero-stat-lbl">Videos & Transcripts</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-val">{kind_counts.get('note', 0) + kind_counts.get('quote', 0)}</span>
            <span class="hero-stat-lbl">Notes & Quotes</span>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-val">{kind_counts.get('bookmark', 0)}</span>
            <span class="hero-stat-lbl">Bookmarks</span>
          </div>
        </div>
      </div>

      <div class="controls">
        <div class="filter-tabs">
          <button class="tab-btn active" data-cat="all">All Formats (12)</button>
          <button class="tab-btn" data-cat="ai">🤖 AI & LLM (3)</button>
          <button class="tab-btn" data-cat="pkm">🧠 PKM & Obsidian (1)</button>
          <button class="tab-btn" data-cat="browser">🌐 Browsers (1)</button>
          <button class="tab-btn" data-cat="reading">⚡ Active Recall & Curation (4)</button>
          <button class="tab-btn" data-cat="syndication">📚 Citations & Feeds (3)</button>
        </div>
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="Filter formats by tool (Obsidian, Readwise, Zotero)...">
        </div>
      </div>
    </header>

    <div class="formats-grid" id="formatsGrid"></div>
  </div>

  <div class="toast" id="toast">✨ Downloading export...</div>

  <script>
    const ATOMS = {atoms_json_str};

    const FORMATS = [
      {{
        id: "digest",
        category: "ai",
        category_name: "AI & Synthesis",
        title: "NotebookLM Knowledge Digest",
        filename: "vault_digest.md",
        ext: ".md",
        icon: "🤖",
        summary: "Unified longform Markdown compilation aggregating all articles, formatted notes, attributed quotes, and full spoken video transcripts into one cohesive document.",
        included: "Offline article text, full dialogue transcripts, curator notes, timestamps, tags",
        tools: ["NotebookLM", "Claude Projects", "Local LLMs", "ChatGPT"],
        cli: "python3 curate.py export --target digest"
      }},
      {{
        id: "obsidian",
        category: "pkm",
        category_name: "PKM",
        title: "Obsidian & Logseq Vault Archive",
        filename: "vault_obsidian.zip",
        ext: ".zip",
        icon: "🧠",
        summary: "Packaged zip archive containing discrete Markdown notes for every atom, fully equipped with YAML frontmatter, tags, source URLs, curator notes, and offline bodies.",
        included: "Individual .md files, YAML metadata frontmatter, curator notes, tags, body content",
        tools: ["Obsidian", "Logseq", "Foam", "Dendron", "SilverBullet"],
        cli: "python3 curate.py export --target obsidian"
      }},
      {{
        id: "bookmarks-html",
        category: "browser",
        category_name: "Browsers",
        title: "Universal HTML Bookmarks",
        filename: "bookmarks.html",
        ext: ".html",
        icon: "🌐",
        summary: "Standard Netscape bookmark specification (HTML). Imports seamlessly into any desktop browser or bookmark manager with full timestamp and tag preservation.",
        included: "Destination & source URLs, titles, timestamps, comma-separated tags, curator notes",
        tools: ["Chrome", "Safari", "Firefox", "Arc", "Raindrop.io", "Pinboard"],
        cli: "python3 curate.py export --target bookmarks-html"
      }},
      {{
        id: "readwise",
        category: "reading",
        category_name: "Active Recall",
        title: "Readwise & Reader Highlights",
        filename: "readwise.csv",
        ext: ".csv",
        icon: "⚡",
        summary: "Spec-compliant CSV formatted for Readwise highlight import. Pipes your curated quotes, highlights, and article reflections into daily active recall reviews.",
        included: "Highlight text, atom title, author attribution, source URL, notes, atom ID",
        tools: ["Readwise", "Readwise Reader", "Daily Review"],
        cli: "python3 curate.py export --target readwise"
      }},
      {{
        id: "llms-txt",
        category: "ai",
        category_name: "AI & Synthesis",
        title: "llms.txt Index Standard",
        filename: "llms.txt",
        ext: ".txt",
        icon: "📑",
        summary: "Compact, standardized index adhering to the emerging llms.txt standard. Provides LLMs with a clean, low-token sitemap of your vault's knowledge.",
        included: "Atom titles, canonical URLs, concise curator descriptions and excerpts",
        tools: ["RAG Ingestion", "Agent Context", "Context Window Optimizer"],
        cli: "python3 curate.py export --target llms-txt"
      }},
      {{
        id: "arena-csv",
        category: "reading",
        category_name: "Active Recall",
        title: "Are.na Channel Import",
        filename: "arena_export.csv",
        ext: ".csv",
        icon: "🧱",
        summary: "Bulk import CSV structured specifically for Are.na channel imports, mapping atom titles, URLs, curator notes, and hashtag arrays into channel blocks.",
        included: "Title, Source URL, Description with notes and hashtags",
        tools: ["Are.na Channels", "Curation Research"],
        cli: "python3 curate.py export --target arena-csv"
      }},
      {{
        id: "pinterest-csv",
        category: "reading",
        category_name: "Visual Curation",
        title: "Pinterest Bulk Pins Import",
        filename: "pinterest_pins.csv",
        ext: ".csv",
        icon: "📌",
        summary: "Official Pinterest bulk upload CSV for batch-creating Image and Video Pins across boards with automated keyword and outbound source link mapping.",
        included: "Title (max 100), Media URL, Board / Section routing, Video thumbnail, Description (max 500), Outbound Link, Keywords",
        tools: ["Pinterest Business", "Visual Boards", "Pin Scheduling", "Outbound Traffic"],
        cli: "python3 curate.py export --target pinterest-csv"
      }},
      {{
        id: "raindrop-csv",
        category: "reading",
        category_name: "Visual Curation",
        title: "Raindrop.io Custom CSV Import",
        filename: "raindrop_export.csv",
        ext: ".csv",
        icon: "💧",
        summary: "Official Raindrop.io custom CSV import format mapping collections to nested folders, with tags, notes/excerpts, and ISO creation timestamps.",
        included: "folder (nested collections), url (required), title, note (annotations/quotes), tags (comma-separated), created (ISO 8601)",
        tools: ["Raindrop.io", "Visual Bookmarks", "Collection Hierarchy", "Web Archives"],
        cli: "python3 curate.py export --target raindrop-csv"
      }},
      {{
        id: "rss",
        category: "syndication",
        category_name: "Syndication",
        title: "RSS 2.0 Syndication Feed",
        filename: "feed.xml",
        ext: ".xml",
        icon: "📡",
        summary: "Standard XML RSS feed generated from your curated library. Allows you to subscribe to your own vault via feed readers or syndicate your curation publicly.",
        included: "RSS items, RFC 822 pubDates, CDATA html descriptions, author tags, categories",
        tools: ["Feedly", "NetNewsWire", "Inoreader", "Static Web"],
        cli: "python3 curate.py export --target rss"
      }},
      {{
        id: "bibtex",
        category: "syndication",
        category_name: "Citations",
        title: "BibTeX Academic Citations",
        filename: "vault.bib",
        ext: ".bib",
        icon: "📚",
        summary: "Formal BibTeX bibliography file with @article and @misc citation blocks. Designed for essayists, researchers, and academics managing bibliographies in Zotero or LaTeX.",
        included: "Citation keys (atom IDs), titles, authors, years, URLs, keywords/tags, notes",
        tools: ["Zotero", "Mendeley", "LaTeX / Overleaf", "BibDesk"],
        cli: "python3 curate.py export --target bibtex"
      }},
      {{
        id: "jsonl",
        category: "ai",
        category_name: "AI & Synthesis",
        title: "JSONL Dataset (Vector & RAG)",
        filename: "vault.jsonl",
        ext: ".jsonl",
        icon: "🔍",
        summary: "Newline-delimited JSON with one full atom envelope per line. Optimized for batch vector embedding pipelines, LangChain, LlamaIndex, and local fine-tuning.",
        included: "Complete raw atom envelope JSON per line (one document per row)",
        tools: ["ChromaDB", "Pinecone", "LangChain", "LlamaIndex", "Embeddings"],
        cli: "python3 curate.py export --target jsonl"
      }},
      {{
        id: "json",
        category: "syndication",
        category_name: "Backup",
        title: "Complete Vault Backup (JSON)",
        filename: "vault_backup.json",
        ext: ".json",
        icon: "💾",
        summary: "Complete, loss-free dump of your entire vault's atom envelopes, including sidecar file references, color palettes, blurhashes, and provenance.",
        included: "Complete raw JSON array of all atom schemas and sidecar metadata",
        tools: ["Disaster Recovery", "Vault Migration", "Automated Backups"],
        cli: "python3 curate.py export --target json"
      }}
    ];

    let activeCategory = 'all';
    let searchQuery = '';

    function showToast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3500);
    }}

    function copyCli(cmd, btn) {{
      navigator.clipboard.writeText(cmd).then(() => {{
        const orig = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => btn.textContent = orig, 2000);
        showToast('📋 Copied CLI command to clipboard!');
      }}).catch(err => {{
        alert('Could not copy command: ' + err);
      }});
    }}

    function triggerDownload(target, filename) {{
      const isHttp = window.location.protocol.startsWith('http');
      if (!isHttp) {{
        if (target === 'json') {{
          const blob = new Blob([JSON.stringify(ATOMS, null, 2)], {{ type: 'application/json' }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          a.click();
          URL.revokeObjectURL(url);
          showToast('💾 Exported ' + filename);
          return;
        }}
        alert('Server generation is required for this format:\\n\\nDouble-click "Launch WideWeb.command" or run:\\npython3 curate.py view --server\\n\\nOr run via CLI:\\npython3 curate.py export --target ' + target);
        return;
      }}
      showToast('📥 Preparing ' + filename + ' download...');
      window.location.href = '/api/export?target=' + target;
    }}

    function renderFormats() {{
      const grid = document.getElementById('formatsGrid');
      grid.innerHTML = '';

      const q = searchQuery.toLowerCase();
      const filtered = FORMATS.filter(fmt => {{
        const matchCat = (activeCategory === 'all' || fmt.category === activeCategory);
        const matchQuery = !q ||
          fmt.title.toLowerCase().includes(q) ||
          fmt.summary.toLowerCase().includes(q) ||
          fmt.ext.toLowerCase().includes(q) ||
          fmt.tools.some(t => t.toLowerCase().includes(q));
        return matchCat && matchQuery;
      }});

      if (filtered.length === 0) {{
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--muted);">No matching export formats found.</div>';
        return;
      }}

      filtered.forEach(fmt => {{
        const card = document.createElement('div');
        card.className = 'format-card';
        card.innerHTML = `
          <div>
            <div class="card-top">
              <div class="card-icon-title">
                <span class="format-icon">${{fmt.icon}}</span>
                <div>
                  <div class="format-title">${{fmt.title}}</div>
                </div>
              </div>
              <div class="format-badges">
                <span class="cat-badge">${{fmt.category_name}}</span>
                <span class="ext-badge">${{fmt.ext}}</span>
              </div>
            </div>

            <div class="format-desc">${{fmt.summary}}</div>

            <div class="format-included">
              <strong>Includes:</strong> ${{fmt.included}}
            </div>

            <div class="tool-pills">
              ${{fmt.tools.map(t => `<span class="tool-pill">${{t}}</span>`).join('')}}
            </div>
          </div>

          <div class="card-actions">
            <button class="dl-btn" onclick="triggerDownload('${{fmt.id}}', '${{fmt.filename}}')">
              📥 Download ${{fmt.filename}}
            </button>
            <div class="cli-box">
              <span class="cli-text">${{fmt.cli}}</span>
              <button class="cli-copy" onclick="copyCli('${{fmt.cli}}', this)">📋 Copy</button>
            </div>
          </div>
        `;
        grid.appendChild(card);
      }});
    }}

    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeCategory = btn.dataset.cat;
        renderFormats();
      }});
    }});

    document.getElementById('searchInput').addEventListener('input', (e) => {{
      searchQuery = e.target.value.trim();
      renderFormats();
    }});

    renderFormats();
  </script>
</body>
</html>
"""

    with open(export_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return export_html_path


class WideWebCaptureHandler(SimpleHTTPRequestHandler):
    """Local HTTP Server that serves static vault files and handles /api/capture & /api/export requests."""
    vault_dir = None

    def __init__(self, *args, **kwargs):
        directory = str(self.vault_dir) if self.vault_dir else None
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/export":
            query = urllib.parse.parse_qs(parsed.query)
            target = query.get("target", ["digest"])[0]
            script_dir = str(Path(__file__).resolve().parent)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            import curate

            export_dir = self.vault_dir / "export"
            export_dir.mkdir(parents=True, exist_ok=True)

            try:
                if target in ("digest", "notebooklm", "llms"):
                    out_path = export_dir / "vault_digest.md"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="digest", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/markdown; charset=utf-8"
                    filename = "vault_digest.md"
                elif target == "llms-txt":
                    out_path = export_dir / "llms.txt"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="llms-txt", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/plain; charset=utf-8"
                    filename = "llms.txt"
                elif target in ("obsidian", "logseq"):
                    out_path = export_dir / "vault_obsidian.zip"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="obsidian", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "application/zip"
                    filename = "vault_obsidian.zip"
                elif target in ("bookmarks-html", "bookmarks", "netscape"):
                    out_path = export_dir / "bookmarks.html"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="bookmarks-html", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/html; charset=utf-8"
                    filename = "bookmarks.html"
                elif target == "readwise":
                    out_path = export_dir / "readwise.csv"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="readwise", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/csv; charset=utf-8"
                    filename = "readwise.csv"
                elif target in ("arena-csv", "csv"):
                    out_path = export_dir / "arena_export.csv"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="arena-csv", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/csv; charset=utf-8"
                    filename = "arena_export.csv"
                elif target in ("pinterest-csv", "pinterest"):
                    out_path = export_dir / "pinterest_pins.csv"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="pinterest-csv", out=str(out_path), board="WideWeb")
                    curate.cmd_export(args)
                    mime = "text/csv; charset=utf-8"
                    filename = "pinterest_pins.csv"
                elif target in ("raindrop-csv", "raindrop"):
                    out_path = export_dir / "raindrop_export.csv"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="raindrop-csv", out=str(out_path), folder="WideWeb")
                    curate.cmd_export(args)
                    mime = "text/csv; charset=utf-8"
                    filename = "raindrop_export.csv"
                elif target in ("rss", "feed"):
                    out_path = export_dir / "feed.xml"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="rss", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "application/rss+xml; charset=utf-8"
                    filename = "feed.xml"
                elif target in ("bibtex", "bib"):
                    out_path = export_dir / "vault.bib"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="bibtex", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "text/plain; charset=utf-8"
                    filename = "vault.bib"
                elif target == "jsonl":
                    out_path = export_dir / "vault.jsonl"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="jsonl", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "application/x-ndjson; charset=utf-8"
                    filename = "vault.jsonl"
                elif target == "json":
                    out_path = export_dir / "vault_backup.json"
                    args = types.SimpleNamespace(vault=str(self.vault_dir), kind=None, tag=None, target="json", out=str(out_path))
                    curate.cmd_export(args)
                    mime = "application/json; charset=utf-8"
                    filename = "vault_backup.json"
                else:
                    self.send_error(400, f"Unsupported export target: {target}")
                    return

                with open(out_path, "rb") as f:
                    content_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content_bytes)))
                self.end_headers()
                self.wfile.write(content_bytes)
            except Exception as e:
                self.send_error(500, f"Export generation error: {e}")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/capture":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8"))
                script_dir = str(Path(__file__).resolve().parent)
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                import curate
                kind = data.get("kind", "link")
                
                if kind in ("article", "bookmark", "link"):
                    args = types.SimpleNamespace(
                        url=data["url"],
                        title=data.get("title"),
                        notes=None,
                        tags=data.get("tags"),
                        collection=None,
                        image_url=None,
                        quote=None,
                        favorite=False,
                        vault=str(self.vault_dir),
                        target_kind="article" if kind == "article" else ("bookmark" if kind == "bookmark" else None)
                    )
                    atom_doc = curate.cmd_save_link(args)
                elif kind == "video":
                    args = types.SimpleNamespace(
                        url=data["url"],
                        title=data.get("title"),
                        notes=None,
                        tags=data.get("tags"),
                        collection=None,
                        favorite=False,
                        vault=str(self.vault_dir)
                    )
                    atom_doc = curate.cmd_video(args)
                elif kind == "quote":
                    args = types.SimpleNamespace(
                        quote=data["quote"],
                        title=None,
                        source=data.get("source"),
                        source_title=None,
                        author=data.get("author"),
                        notes=None,
                        tags=data.get("tags"),
                        collection=None,
                        favorite=False,
                        vault=str(self.vault_dir)
                    )
                    atom_doc = curate.cmd_quote(args)
                elif kind == "note":
                    args = types.SimpleNamespace(
                        text=data["text"],
                        title=data.get("title"),
                        tags=data.get("tags"),
                        collection=None,
                        favorite=False,
                        vault=str(self.vault_dir)
                    )
                    atom_doc = curate.cmd_note(args)
                elif kind == "image":
                    args = types.SimpleNamespace(
                        src=data["src"],
                        title=data.get("title"),
                        source=data.get("source"),
                        author=data.get("author"),
                        alt=data.get("alt"),
                        notes=data.get("notes"),
                        tags=data.get("tags"),
                        collection=None,
                        favorite=False,
                        vault=str(self.vault_dir)
                    )
                    atom_doc = curate.cmd_image(args)
                else:
                    raise ValueError(f"Unsupported kind: {kind}")

                # Regenerate viewer index with fresh atom
                generate_viewer(self.vault_dir)

                # Format atom for immediate UI card injection
                created_at = atom_doc["created_at"]
                folder = self.vault_dir / "atoms" / created_at[:4] / created_at[5:7] / atom_doc["id"]
                article_text = None
                if atom_doc.get("payload", {}).get("article", {}):
                    art_file = atom_doc["payload"]["article"].get("file")
                    if art_file and (folder / art_file).exists():
                        try:
                            with open(folder / art_file, "r", encoding="utf-8") as f:
                                article_text = f.read()
                        except Exception:
                            pass

                excerpt_text = None
                if atom_doc.get("kind") == "video":
                    trans_file = folder / "transcript.txt"
                    if trans_file.exists():
                        try:
                            with open(trans_file, "r", encoding="utf-8") as tf:
                                excerpt_text = tf.read()
                        except Exception:
                            pass
                elif atom_doc.get("payload", {}).get("text", {}):
                    excerpt_text = atom_doc["payload"]["text"].get("excerpt")
                elif atom_doc.get("payload", {}).get("quote", {}):
                    excerpt_text = atom_doc["payload"]["quote"].get("text")

                card_data = {
                    "id": atom_doc["id"],
                    "kind": atom_doc.get("kind") or atom_doc.get("curation", {}).get("kind"),
                    "title": atom_doc["curation"]["atom_title"],
                    "notes": atom_doc["curation"]["notes"],
                    "tags": atom_doc["curation"]["tags"],
                    "date": created_at[:10],
                    "created_at": created_at,
                    "destination_url": atom_doc.get("payload", {}).get("destination_url"),
                    "source_url": atom_doc.get("provenance", {}).get("source_url"),
                    "author": atom_doc.get("provenance", {}).get("author"),
                    "cover_path": atom_doc.get("payload", {}).get("cover_image", {}).get("relative_path") if atom_doc.get("payload", {}).get("cover_image") else None,
                    "metadata": atom_doc.get("metadata_json", {}),
                    "article_markdown": article_text,
                    "excerpt": excerpt_text,
                    "folder_path": f"atoms/{created_at[:4]}/{created_at[5:7]}/{atom_doc['id']}",
                    "raw": atom_doc
                }

                response_bytes = json.dumps({"success": True, "atom": card_data}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_bytes)))
                self.end_headers()
                self.wfile.write(response_bytes)

            except Exception as e:
                err_bytes = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_bytes)))
                self.end_headers()
                self.wfile.write(err_bytes)
        else:
            self.send_error(404, "Endpoint not found")


def run_viewer_server(vault_dir: Path, port: int = 8080, open_browser: bool = True):
    """Run the local WideWeb HTTP server for instant web viewing and live in-browser capture."""
    vault_dir = Path(vault_dir).resolve()
    generate_viewer(vault_dir)
    os.chdir(vault_dir)
    WideWebCaptureHandler.vault_dir = vault_dir
    server = HTTPServer(("127.0.0.1", port), WideWebCaptureHandler)
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"\n🚀 WideWeb Live Vault & Capture running at: {url}")
    print(f"   • Press 'c' in the browser to quick-capture links, quotes, or notes")
    print(f"   • Press 'Ctrl+C' in terminal to stop server")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWideWeb server stopped.")


if __name__ == "__main__":
    v_dir = Path("vault")
    out = generate_viewer(v_dir)
    print(f"✨ Regenerated WideWeb viewer at: {out}")
