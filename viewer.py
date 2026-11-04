#!/usr/bin/env python3
"""
WideWeb HTML Viewer Generator
Builds a high-aesthetic, local-first masonry showcase for browsing and reading saved atoms.
"""

import json
import os
import sqlite3
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def generate_viewer(vault_dir: Path) -> Path:
    """Generate vault/index.html containing the standalone reactive masonry viewer."""
    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM atoms ORDER BY created_at DESC").fetchall()

    atoms_data = []
    kind_counts = {"all": len(rows), "link": 0, "quote": 0, "note": 0, "image": 0, "video": 0, "file": 0}

    for r in rows:
        raw = json.loads(r["raw_json"])
        created_at = r["created_at"]
        folder = vault_dir / "atoms" / created_at[:4] / created_at[5:7] / r["id"]

        # Read offline article markdown if present
        article_text = None
        if raw.get("payload", {}).get("article", {}):
            art_file = raw["payload"]["article"].get("file")
            if art_file and (folder / art_file).exists():
                try:
                    with open(folder / art_file, "r", encoding="utf-8") as f:
                        article_text = f.read()
                except Exception:
                    pass

        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        tags = json.loads(r["tags"]) if r["tags"] else []
        kind = r["kind"]
        if kind in kind_counts:
            kind_counts[kind] += 1

        atoms_data.append({
            "id": r["id"],
            "kind": kind,
            "title": r["atom_title"],
            "notes": r["notes"],
            "tags": tags,
            "date": r["created_at"][:10],
            "destination_url": r["destination_url"],
            "source_url": r["source_url"],
            "author": r["author"],
            "cover_path": r["cover_file_path"],
            "metadata": meta,
            "article_markdown": article_text,
            "excerpt": r["text_content"]
        })

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
      align-items: baseline;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .logo {{
      font-size: 26px;
      font-weight: 600;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      font-size: 14px;
      color: var(--muted);
      margin-left: 10px;
    }}
    .stats-badge {{
      font-size: 13px;
      color: var(--muted);
      background: var(--tag-bg);
      padding: 4px 12px;
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
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
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
    .kind-link {{ color: #2B6CB0; background: rgba(43,108,176,0.1); }}
    .kind-quote {{ color: #9B2C2C; background: rgba(155,44,44,0.1); }}
    .kind-note {{ color: #7B341E; background: rgba(123,52,30,0.1); }}
    .kind-image {{ color: #2C7A7B; background: rgba(44,122,123,0.1); }}
    
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

    /* Reader Dialog Modal */
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
      padding: 20px 28px;
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
      font-size: 18px;
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
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="top-bar">
        <div>
          <span class="logo">WideWeb</span>
          <span class="subtitle">local curation vault</span>
        </div>
        <div class="stats-badge" id="statsBadge">{len(rows)} items</div>
      </div>
      <div class="controls">
        <div class="filter-tabs">
          <button class="tab-btn active" data-filter="all">All <span class="tab-badge" id="badge-all"></span></button>
          <button class="tab-btn" data-filter="link">Links <span class="tab-badge" id="badge-link"></span></button>
          <button class="tab-btn" data-filter="quote">Quotes <span class="tab-badge" id="badge-quote"></span></button>
          <button class="tab-btn" data-filter="note">Notes <span class="tab-badge" id="badge-note"></span></button>
          <button class="tab-btn" data-filter="image">Images <span class="tab-badge" id="badge-image"></span></button>
        </div>
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="Search title, author, tag, text...">
        </div>
      </div>
    </header>

    <div class="masonry" id="cardGrid"></div>
  </div>

  <dialog id="readerModal" closedby="any">
    <div class="modal-header">
      <div id="modalMeta" class="modal-meta" style="margin-bottom:0;"></div>
      <button class="modal-close" id="closeModalBtn" onclick="document.getElementById('readerModal').close()">✕</button>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </dialog>

  <script>
    const ATOMS = {atoms_json_str};
    const COUNTS = {counts_json_str};

    let activeFilter = 'all';
    let searchQuery = '';

    // Set badge counts
    for (const [k, v] of Object.entries(COUNTS)) {{
      const b = document.getElementById(`badge-${{k}}`);
      if (b) b.textContent = `(${{v}})`;
    }}
    document.getElementById('statsBadge').textContent = `${{ATOMS.length}} items saved`;

    function renderCards() {{
      const grid = document.getElementById('cardGrid');
      grid.innerHTML = '';

      const filtered = ATOMS.filter(a => {{
        if (activeFilter !== 'all' && a.kind !== activeFilter) return false;
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
          coverHtml = `<img class="card-cover" src="${{atom.cover_path}}" ${{ratio}} loading="lazy" alt="${{atom.title}}">`;
        }}

        let bodyHtml = '';
        if (atom.kind === 'quote') {{
          bodyHtml = `
            <div class="card-body">
              <div class="quote-content">“${{atom.excerpt || atom.title}}”</div>
              ${{atom.author ? `<div class="author-byline">— ${{atom.author}}</div>` : ''}}
              ${{atom.notes ? `<div class="card-notes">${{atom.notes}}</div>` : ''}}
            </div>
          `;
        }} else if (atom.kind === 'note') {{
          bodyHtml = `
            <div class="card-body">
              <div class="card-title">${{atom.title}}</div>
              <div class="card-notes" style="-webkit-line-clamp: 8;">${{atom.excerpt || ''}}</div>
            </div>
          `;
        }} else {{
          bodyHtml = `
            <div class="card-body">
              <div class="card-title">
                ${{atom.destination_url ? `<a href="${{atom.destination_url}}" target="_blank" rel="noopener">${{atom.title}}</a>` : atom.title}}
              </div>
              ${{atom.author ? `<div class="author-byline">${{atom.author}}</div>` : ''}}
              ${{atom.notes ? `<div class="card-notes">${{atom.notes}}</div>` : ''}}
            </div>
          `;
        }}

        // Footer
        let tagsHtml = (atom.tags || []).map(t => `<span class="tag">#${{t}}</span>`).join('');
        let extrasHtml = '';
        if (atom.article_markdown) {{
          extrasHtml = `<button class="read-btn" onclick="openReader('${{atom.id}}')">📖 Read</button>`;
        }} else if (atom.metadata && atom.metadata.color_palette && atom.metadata.color_palette.length) {{
          extrasHtml = `<div class="palette-dots">` + atom.metadata.color_palette.map(c => `<div class="palette-dot" style="background:${{c}}" title="${{c}}"></div>`).join('') + `</div>`;
        }} else if (atom.metadata && atom.metadata.word_count) {{
          extrasHtml = `<span style="color:var(--muted);">${{atom.metadata.word_count}}w</span>`;
        }}

        card.innerHTML = `
          <div class="card-header">
            <span class="kind-pill kind-${{atom.kind}}">${{atom.kind}}</span>
            <span>${{atom.date}}</span>
          </div>
          ${{coverHtml}}
          ${{bodyHtml}}
          <div class="card-footer">
            <div class="tags">${{tagsHtml}}</div>
            <div>${{extrasHtml}}</div>
          </div>
        `;

        grid.appendChild(card);
      }});
    }}

    function openReader(atomId) {{
      const atom = ATOMS.find(a => a.id === atomId);
      if (!atom || !atom.article_markdown) return;

      const modal = document.getElementById('readerModal');
      const body = document.getElementById('modalBody');
      const meta = document.getElementById('modalMeta');

      const wordCount = atom.metadata && atom.metadata.word_count ? `${{atom.metadata.word_count}} words` : '';
      const readTime = atom.metadata && atom.metadata.word_count ? `~${{Math.ceil(atom.metadata.word_count / 225)}} min read` : '';

      meta.innerHTML = `
        <span><strong>${{atom.author || 'Author'}}</strong></span>
        <span>•</span>
        <span>${{atom.date}}</span>
        ${{wordCount ? `<span>•</span><span>${{wordCount}}</span>` : ''}}
        ${{readTime ? `<span>•</span><span>${{readTime}}</span>` : ''}}
      `;

      let parsedHtml = '';
      if (window.marked && typeof window.marked.parse === 'function') {{
        parsedHtml = window.marked.parse(atom.article_markdown);
      }} else {{
        parsedHtml = `<pre style="white-space:pre-wrap;">${{atom.article_markdown}}</pre>`;
      }}

      body.innerHTML = `<h1>${{atom.title}}</h1>` + parsedHtml;
      modal.showModal();
    }}

    // Filter clicks
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        renderCards();
      }});
    }});

    // Search input
    document.getElementById('searchInput').addEventListener('input', (e) => {{
      searchQuery = e.target.value.trim();
      renderCards();
    }});

    // Close on backdrop click
    document.getElementById('readerModal').addEventListener('click', (e) => {{
      const dialog = document.getElementById('readerModal');
      const rect = dialog.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {{
        dialog.close();
      }}
    }});

    // Initial render
    renderCards();
  </script>
</body>
</html>
"""

    index_html_path = vault_dir / "index.html"
    with open(index_html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    return index_html_path
