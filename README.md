# WideWeb

A local-first, durable web curation and bookmarking framework using the **Payload Sidecar** pattern.

Decouples capture and long-term storage from proprietary platforms. The filesystem is the canonical source of truth; SQLite is a disposable, fast index.

---

## The 7 Kinds of Atoms

WideWeb categorizes every curated piece of content into an explicit semantic `kind`:

| Kind | Role | Primary Payload | Key Metadata |
| :--- | :--- | :--- | :--- |
| **`article`** | Longform essay, newsletter, or post | `cover.jpg` + `article.md` | `published_at`, `favicon`, `word_count`, `read_time`, `blurhash` |
| **`bookmark`** | Lightweight web pointer (tool, repo, site) | `cover.jpg` (OG card) | `destination_url`, `favicon`, `blurhash`, `palette` |
| **`video`** | YouTube, Vimeo, or video stream | `cover.jpg` + `transcript.txt` | `provider`, `embed_url`, `captions_count`, `language` |
| **`quote`** | Attributed verbatim excerpt | `quote.txt` | `author`, `source_url`, `word_count` |
| **`note`** | Personal thought, memo, or reflection | `note.md` | `word_count` (zero external URL required) |
| **`image`** | Photo, artwork, diagram, or scan | `cover.jpg` | `dimensions`, `aspect_ratio`, `blurhash`, `color_palette`, `alt_text` |
| **`file`** | Document, PDF, or attachment | `document.pdf` + `cover.png` | `file_size_bytes`, `file_extension`, `page_count` |

---

## Quickstart

Run commands from the repository directory:

```bash
python3 -m pip install -r requirements.txt
```

### 1. Save a Link or Article (`curate.py link`)
Fetches Open Graph metadata, downloads the cover image (`cover.png`), extracts dominant colors + blurhash + aspect ratio, and saves the full offline readable article text (`article.md`):

```bash
python3 curate.py link "https://www.drewshannon.net/a-series-of-tubes/" \
  --tags "systems,tubes"
```

### 2. Save an Attributed Quote (`curate.py quote`)
Captures an exact quote, calculates word count, and anchors it to author and source provenance:

```bash
python3 curate.py quote "Productivity is an information routing problem, not an attention shortage problem." \
  --author "Drew Shannon" \
  --source "https://www.drewshannon.net/a-series-of-tubes/" \
  --tags "productivity,systems"
```

### 3. Save a Personal Note (`curate.py note`)
Captures an original reflection or memo (no external URL required):

```bash
python3 curate.py note "Information routing is the architecture of thought." \
  --tags "systems,philosophy"
```

### 4. Save an Image (`curate.py image`)
Captures a local photo or direct web image URL, computes aspect ratio, blurhash, and color palette:

```bash
python3 curate.py image "/path/to/diagram.png" \
  --title "Information Routing Funnel" \
  --tags "diagram,systems"
```

### 5. List Saved Atoms (`curate.py list`)
List recent atoms with optional filtering by `kind`, `tag`, or `collection`:

```bash
python3 curate.py list
python3 curate.py list --kind quote
python3 curate.py list --kind link
python3 curate.py list --tag systems
```

### 6. Visual Gallery & Live Capture Studio (`curate.py view`)
Browse your vault with high-aesthetic typography, 4-tier schema inspection, responsive video player, and distraction-free reader mode:

```bash
# Zero-Terminal macOS Launcher:
# Simply double-click "Launch WideWeb.command" in Finder!

# Or launch via terminal:
python3 curate.py view --server
```

**In-Browser Studio Features:**
- **`+ Capture` Modal (`c`)**: 1-click capture tabs for **Articles** (scraped Markdown), **Bookmarks** (lightweight pointers), **Videos** (auto-transcription & posters), **Quotes**, **Notes** (Markdown), and **Images** (blurhash & color extraction).
- **`📥 Export ▾` Menu**: 1-click browser downloads for:
  - 🤖 **NotebookLM Digest (`.md`)**: Unified longform document with articles, notes, quotes, and full video transcripts.
  - 📑 **`llms.txt` Index (`.txt`)**: Compact, LLM-friendly index standard.
  - 🧱 **Are.na CSV (`.csv`)**: Import-ready file for Are.na channels.
  - 💾 **Full Vault Backup (`.json`)**: Complete raw schemas & metadata.
- **⚡ Bookmarklet**: Drag the "Save to WideWeb" bookmarklet to your browser's favorites bar for 1-click capture from any web page.

---

## AI Integration: Model Context Protocol (MCP)

WideWeb includes an embedded [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server so AI assistants (**Claude Desktop**, **Antigravity**, **Cursor**) can search and read from your vault.

### 1. Claude Desktop Setup
Add this to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "wideweb": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/wideweb/wideweb_mcp.py"
      ]
    }
  }
}
```

### 2. Available AI Tools
Once connected, your AI assistant can invoke:
- `search_vault(query, kind, tag)`: Fast search across titles, notes, article text, and transcripts.
- `get_atom(atom_id)`: Retrieve full structured metadata and offline content body.
- `get_transcript(atom_id)`: Read timestamped dialogue for any video.
- `get_article(atom_id)`: Read the full offline Markdown body for any article.
- `save_note(text, title, tags)`: Save a new thought directly into your vault.
- `save_bookmark(url, title, tags)`: Bookmark a web link into your vault.

---

## Knowledge Exports & Data Portability

WideWeb guarantees your knowledge is never held hostage in a proprietary silo. You can export your library into 12 open standards via the **Export Hub** (`/export.html`) or the CLI:

| Target | Command | Primary Ecosystem | Output File |
| :--- | :--- | :--- | :--- |
| **NotebookLM Digest** | `curate.py export --target digest` | NotebookLM, Claude Projects | `vault_digest.md` |
| **Obsidian Vault** | `curate.py export --target obsidian` | Obsidian, Logseq, Foam | `vault_obsidian.zip` |
| **HTML Bookmarks** | `curate.py export --target bookmarks-html` | Chrome, Safari, Firefox, Arc | `bookmarks.html` |
| **Raindrop.io CSV** | `curate.py export --target raindrop-csv` | Raindrop.io Collections | `raindrop_export.csv` |
| **Readwise Highlights**| `curate.py export --target readwise` | Readwise, Reader | `readwise.csv` |
| **`llms.txt` Index** | `curate.py export --target llms-txt` | LLM Agents, Context Optimization | `llms.txt` |
| **Are.na CSV** | `curate.py export --target arena-csv` | Are.na Channels | `arena_export.csv` |
| **Pinterest Bulk CSV** | `curate.py export --target pinterest-csv` | Pinterest Business, Visual Boards | `pinterest_pins.csv` |
| **RSS 2.0 Feed** | `curate.py export --target rss` | Feedly, NetNewsWire, RSS Readers | `feed.xml` |
| **BibTeX Citations** | `curate.py export --target bibtex` | Zotero, LaTeX, Mendeley | `vault.bib` |
| **JSONL Dataset** | `curate.py export --target jsonl` | Vector Embeddings, LangChain, RAG | `vault.jsonl` |
| **Full Raw Backup** | `curate.py export --target json` | Disaster Recovery, Migration | `vault_backup.json` |

To browse, search, and download all exports in your browser, click **📦 Export Center** in the top navigation bar of the web gallery (`/export.html`).

---

## Inbound Sync (`curate.py pull`)

Pulls newly captured content from Instapaper and Are.na directly into your vault:
- **Instapaper**: Ingests new unread bookmarks with titles, excerpts, tags, and cover images.
- **Are.na**: Ingests new blocks added across your account (Links, Images, and Text notes).
- **Deduplication**: Automatic matching by destination URL and external IDs prevents duplicates.

```bash
# Pull new items from both Instapaper and Are.na
python3 curate.py pull

# Pull from a specific service only
python3 curate.py pull --service instapaper
python3 curate.py pull --service arena
```

---

## Sync to Public Garden (`curate.py sync`)

Publishes public atoms to your live digital garden (e.g., `drewshannon.net/garden`):
1. Exports `curation_public.json` containing metadata, tags, and excerpts for atoms where `visibility = 'public'` (keeps private atoms local-only).
2. Uploads the manifest to Google Cloud Storage (`gs://wideweb-assets-drew/curation_public.json`).
3. Rsyncs public cover images to `gs://wideweb-assets-drew/atoms/`.

```bash
# Full sync: manifest + image assets
python3 curate.py sync

# Fast sync: manifest only (instant updates for tags/titles/notes)
python3 curate.py sync --manifest-only
```

---

## Disaster Recovery (`reindex`)

Deletes `vault.db`, walks your local `atoms/` directory, and reconstructs the entire SQLite search database from the `atom.json` sidecars in seconds:

```bash
python3 curate.py reindex
```

---

## Vault Architecture

```text
wideweb/
├── curate.py                 # Core CLI ingestion & pipeline engine
├── viewer.py                 # Visual presentation & local capture server
├── wideweb_mcp.py            # Model Context Protocol (MCP) server for AI tools
├── requirements.txt          # Python dependencies
├── schema/
│   └── atom.schema.json      # Formal JSON Schema specification (v2)
└── vault/                    # Canonical user vault (gitignored / syncable)
    ├── vault.db              # Disposable SQLite search catalog
    ├── index.html            # Zero-dependency single-page visual gallery
    ├── export/               # Generated LLM digests & export files
    └── atoms/
        └── YYYY/
            └── MM/
                └── atm_YYYYMMDD.../
                    ├── atom.json      # 4-tier structured metadata envelope
                    ├── cover.jpg      # Universal visual preview (480px, blurhash, palette)
                    ├── article.md     # Offline readable article text (for articles)
                    ├── transcript.txt # Timestamped spoken dialogue (for videos)
                    ├── transcript.json# Machine-readable dialogue offsets
                    ├── note.md        # Formatted markdown thoughts (for notes)
                    └── quote.txt      # Text excerpt (for quotes)
```
