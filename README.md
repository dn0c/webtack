# Webtack

A local-first, durable web curation and bookmarking framework using the **Content Sidecar** pattern.  
**Website:** [https://webtack.net](https://webtack.net)

Decouples capture and long-term storage from proprietary platforms. The filesystem is the canonical source of truth; SQLite is a disposable, fast index.

---

## Quickstart (Try it in 60 seconds)

Clone the repository and view the included specimen vault:

```bash
# 1. Clone repository & install dependencies
git clone https://github.com/dn0c/webtack.git
cd webtack
pip install -r requirements.txt

# 2. Open the visual gallery viewer (auto-indexes the demo vault)
python3 viewer.py --vault fixtures/demo_vault

# 3. Or launch the local server with 1-click browser capture
python3 viewer.py --vault fixtures/demo_vault --server
```

---

## The 7 Kinds of Atoms

Webtack categorizes every curated piece of content into an explicit semantic `kind`:

| Kind | Role | Primary Content | Key Metadata |
| :--- | :--- | :--- | :--- |
| **`article`** | Longform essay, newsletter, or post | `cover.jpg` + `article.md` | `published_at`, `favicon`, `word_count`, `read_time`, `blurhash` |
| **`bookmark`** | Lightweight web pointer (tool, repo, site) | `cover.jpg` (OG card) | `source_url`, `favicon`, `blurhash`, `palette` |
| **`video`** | YouTube, Vimeo, or video stream | `cover.jpg` + `transcript.txt` | `provider`, `embed_url`, `captions_count`, `language` |
| **`quote`** | Attributed verbatim excerpt | `quote.md` | `author`, `source_url`, `word_count` |
| **`note`** | Personal thought, memo, or reflection | `note.md` | `word_count` (zero external URL required) |
| **`image`** | Photo, artwork, diagram, or scan | `cover.jpg` | `dimensions`, `aspect_ratio`, `blurhash`, `color_palette`, `alt_text` |
| **`file`** | Document, PDF, or attachment | `document.pdf` + `cover.png` | `file_size_bytes`, `file_extension`, `page_count` |

---

## Webtack Schema Specification (v3)

> For the formal data protocol, sidecar storage contracts, and extension rules, read the complete **[SPECIFICATION.md](SPECIFICATION.md)**.

Every atom is anchored by a canonical `atom.json` metadata sidecar structured into three decoupled knowledge tiers wrapped in a lightweight system envelope:

```
┌────────────────────────────────────────────────────────┐
│  System Envelope (Document Header)                     │
│  (id, kind, version, created_at, updated_at, $schema)  │
├────────────────────────────────────────────────────────┤
│  Tier 1: Curation Layer                                │
│  (atom_title, notes, tags, collections, visibility)    │
├────────────────────────────────────────────────────────┤
│  Tier 2: Source Layer                                  │
│  (source_url, source_title, site_name, author, capture)│
├────────────────────────────────────────────────────────┤
│  Tier 3: Content Layer                                 │
│  (cover_image, article, text, video, file attachments) │
└────────────────────────────────────────────────────────┘
```

### System Envelope
Document identity, machine routing, and specification versioning.

| Field | Type | Description |
| :--- | :--- | :--- |
| **`id`** | `string` | Unique chronological identifier (e.g. `2026-11-05-d286-9ac7`). |
| **`kind`** | `string` | Semantic discriminator: `article`, `bookmark`, `video`, `quote`, `note`, `image`, or `file`. |
| **`version`** | `integer` | Schema specification version (`3`). |
| **`created_at`** | `string (ISO 8601)` | Timestamp when the atom was first ingested into the vault. |
| **`updated_at`** | `string (ISO 8601)` | Timestamp of most recent edit or enrichment. |
| **`$schema`** | `string (URI)` | Canonical URL pointing to the JSON Schema validator. |

---

### Tier 1: Curation Layer (`curation`)
Editorial perspective, personal taxonomy, annotations, and privacy controls.

| Field | Type | Description |
| :--- | :--- | :--- |
| **`atom_title`** | `string` | Curated human-readable title (defaults to source title or user override). |
| **`notes`** | `string \| null` | Personal Markdown thoughts, synthesis, or commentary. |
| **`tags`** | `array[string]` | Normalized lowercase kebab-style slugs (e.g. `["systems-thinking", "design"]`). |
| **`collections`** | `array[string]` | Named project, reading list, or channel collections (e.g. `["Reading List"]`). |
| **`visibility`** | `string` | Egress classification: `public` (garden), `shared` (circle), or `private` (local machine only). |
| **`favorite`** | `boolean` | Starred/favorited status for quick filtering. |

---

### Tier 2: Source Layer (`source`)
Origin, attribution, publisher source, and upstream capture pipeline.

| Field | Type | Description |
| :--- | :--- | :--- |
| **`source_url`** | `string \| null` | Canonical public web address of the original content. |
| **`source_title`** | `string \| null` | Original HTML `<title>` or upstream publication headline. |
| **`site_name`** | `string \| null` | Publisher or platform name (e.g. `The New Yorker`, `YouTube`, `Substack`). |
| **`author`** | `string \| null` | Original author, artist, or channel creator. |
| **`published_at`** | `string (ISO 8601) \| null` | Original publication date if detected via metadata/Open Graph. |
| **`favicon`** | `string (URL) \| null` | Direct URL to the publisher's favicon. |
| **`capture_method`**| `string \| null` | Ingestion tool or pipeline (`cli`, `arena`, `instapaper`, `mcp`, `extension`). |
| **`capture_id`** | `string \| null` | Upstream item ID on source platform (e.g. Are.na block ID, Instapaper bookmark ID). |
| **`capture_url`** | `string (URL) \| null` | Direct link to the item on the upstream capture service. |

---

### Tier 3: Content Layer (`content`)
The immutable physical foundation: offline readable text, media streams, visual anchors, and attachments via a modular 5-slot architecture:

| Slot / Field | Type | Description |
| :--- | :--- | :--- |
| **`cover_image`** | `object \| null` | **Universal Visual Anchor**: photo, article OG card, video poster, or PDF preview. Holds `file`, `relative_path`, `mime_type`, `dimensions`, `aspect_ratio`, `blurhash`, `color_palette`, `alt_text`, and `public_url`. |
| **`text`** | `object \| null` | **Shortform Body**: quotes and notes. Holds `file` (`quote.md` or `note.md`), `excerpt` (inline markdown), and `word_count`. |
| **`article`** | `object \| null` | **Offline Longform Body**: extracted full text. Holds `file` (`article.md`), `word_count`, and `byline`. |
| **`video`** | `object \| null` | **Video & Transcripts**: stream player and audio captions. Holds `provider`, `embed_url`, `duration_seconds`, `transcript_file`, `transcript_json`, `transcript_language`, `transcript_is_generated`, and `has_transcript`. |
| **`file`** | `object \| null` | **Document Attachment**: document or binary file. Holds `filename`, `file_size_bytes`, `file_extension`, and `page_count`. |

---

### Overflow Bag (`metadata_json`)
A flexible JSON dictionary for niche, plugin, or experimental metadata without breaking canonical schema validation (e.g. detected reading speed, custom AI tags, color weights).

### Example Canonical Atom (`atom.json`)

```json
{
  "$schema": "https://raw.githubusercontent.com/dn0c/webtack/main/schema/atom.schema.json",
  "id": "2026-11-05-b2e3-c4d5",
  "kind": "article",
  "version": 3,
  "created_at": "2026-11-05T12:00:00Z",
  "updated_at": "2026-11-05T12:00:00Z",
  "curation": {
    "atom_title": "On Information Routing",
    "notes": "Essential thesis on treating productivity as a routing problem.",
    "tags": ["systems", "productivity"],
    "collections": ["Core Essays"],
    "visibility": "public",
    "favorite": true
  },
  "source": {
    "source_url": "https://example.com/essay",
    "source_title": "On Information Routing",
    "site_name": "Digital Garden",
    "author": "Drew Shannon",
    "published_at": "2026-11-05T08:00:00Z",
    "favicon": "https://example.com/favicon.ico",
    "capture_method": "cli",
    "capture_id": null,
    "capture_url": null
  },
  "content": {
    "cover_image": {
      "file": "cover.jpg",
      "relative_path": "atoms/2026/11/atm_20261105024437_b2e3c4/cover.jpg",
      "mime_type": "image/jpeg",
      "dimensions": { "width": 1200, "height": 630 },
      "aspect_ratio": 1.905,
      "blurhash": "L9RfkBxu~q-;-;j?IUt7afoeRQof",
      "color_palette": ["#1A202C", "#EDF2F7"],
      "alt_text": "Minimalist diagram of information nodes and network routing"
    },
    "text": "Productivity is an information routing problem, not an attention shortage problem.",
    "article": {
      "file": "article.md",
      "relative_path": "atoms/2026/11/atm_20261105024437_b2e3c4/article.md",
      "word_count": 2840,
      "byline": "Drew Shannon"
    },
    "video": null,
    "file": null
  },
  "metadata_json": {
    "reading_time_minutes": 13
  }
}
```

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
# Simply double-click "Launch Webtack.command" in Finder!

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
- **⚡ Bookmarklet**: Drag the "Save to Webtack" bookmarklet to your browser's favorites bar for 1-click capture from any web page.

---

## AI Integration: Model Context Protocol (MCP)

Webtack includes an embedded [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server so AI assistants (**Claude Desktop**, **Antigravity**, **Cursor**) can search and read from your vault.

### 1. Claude Desktop Setup
Add this to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "webtack": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/webtack/webtack_mcp.py"
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

Webtack guarantees your knowledge is never held hostage in a proprietary silo. You can export your library into 12 open standards via the **Export Hub** (`/export.html`) or the CLI:

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

## The Enrichment Lifecycle

Webtack follows a core operational rule: **Ingress is lightweight; enrichment is layered.**

Capturing content should never fail or hang because an external AI service is down or audio transcription takes 30 seconds. Fast metadata is saved immediately at ingestion (`curate.py`); heavy semantic layers (vision alt-text, speech transcripts, full-text backfills) are layered onto atom sidecars asynchronously whenever you choose.

```
┌────────────────────────────────────────────────────────┐
│  Phase 1: Ingestion-Time Enrichment (curate.py)        │
│  Fast, synchronous (0–2s) at the moment of capture     │
├────────────────────────────────────────────────────────┤
│  Phase 2: Deep / Asynchronous Enrichment (scripts/)    │
│  Heavy, optional, offline batch or on-demand pipelines │
└────────────────────────────────────────────────────────┘
```

### Phase 1: Ingestion-Time Enrichment (`curate.py`)
Runs automatically during capture to ensure instant visual parity in the viewer:
* **Articles:** Trafilatura extracts clean markdown into `article.md`, calculates `word_count` and `read_time`, downloads the hero image, and fetches the site's `favicon`.
* **Bookmarks:** Scrapes OpenGraph tags (`og:title`, `og:description`, `og:image`) and calculates the `blurhash` and `color_palette` for instant progressive rendering in the UI.
* **Quotes:** Normalizes typography (curly quotes, em-dashes), captures creator attribution, and saves clean markdown in `quote.md`.
* **Videos:** Scrapes channel name, duration, and high-res video thumbnail.

---

### Phase 2: Deep / Batch Enrichment (`curate.py enrich` & scripts)
Runs asynchronously, in the background, or in batch when you want to upgrade your library:

| Target | Command | What it Adds to the Atom |
| :--- | :--- | :--- |
| **Image Vision & Accessibility** | `curate.py enrich`<br>*(runs `scripts/enrich.py`)* | Resolves rich, descriptive accessibility `alt_text` using a 5-tier resolution engine. |
| **Spoken Dialogue & Audio** | `curate.py backfill-transcripts` | Extracts dialogue into `transcript.txt` and timestamped offset cues in `transcript.json`. |
| **Full Article Text** | `scripts/backfill_instapaper_fulltext.py` | Upgrades lightweight bookmark pointers into full offline `article.md` reading sidecars. |
| **Quote Sources & Authors** | `scripts/enrich_quotes_deep.py` | Matches quotes against publication domains to resolve missing author attributions. |

#### Accessibility Alt Text & Vision Engine (`curate.py enrich`)

Webtack resolves accessibility alt text through a cascading **5-tier resolution engine**:
1. **Embedded Metadata (EXIF/IPTC)**: Reads photographer descriptions stored inside the image binary (0ms, zero keys).
2. **Upstream Web Scraping**: Extracts `<figcaption>`, `<img alt="...">`, or `og:image:alt` from the source webpage (zero keys).
3. **Multi-Provider Cloud Vision**: If configured in `.env`, generates rich narrative descriptions via **Gemini** (`GEMINI_API_KEY`), **OpenAI** (`OPENAI_API_KEY`), **Anthropic** (`ANTHROPIC_API_KEY`), **Groq** (`GROQ_API_KEY`), or **OpenRouter** (`OPENROUTER_API_KEY`).
4. **Native macOS Vision**: Offline fallback using Apple Silicon Neural Engine (`VNRecognizeTextRequest` + `VNClassifyImageRequest`) for local OCR and scene classification (zero keys, zero network).
5. **Fallback**: Gracefully uses the atom title or curator description.

```bash
# Enrich images missing alt text
python3 curate.py enrich

# Force regenerate alt text for up to 10 images
python3 curate.py enrich --limit 10 --force
```

---

## Upstream Integrations (`integrations/`)

Webtack is designed to be local-first and platform-agnostic. Optional connectors to external services live in the modular `integrations/` folder:

* **Are.na** (`integrations/arena/`):
  * Import entire channels: `python3 integrations/arena/import_channel.py <channel-slug>`
  * Inbound feed sync: `python3 integrations/arena/sync.py`
  * Two-way alt text sync: `python3 integrations/arena/sync_alt_text.py`
* **Instapaper** (`integrations/instapaper/`):
  * Sync unread reading list with parsed readability text: `python3 integrations/instapaper/sync.py`
* **Google Cloud Storage** (`integrations/gcs/`):
  * Sync public assets & `curation_public.json` to GCS for your digital garden: `python3 integrations/gcs/sync.py`

You can also run automated inbound pulls across configured services using:

```bash
# Pull new items from configured services
python3 curate.py pull
```

---

## Sync to Public Garden (`curate.py sync`)

Publishes public atoms to your live digital garden (e.g., `drewshannon.net/garden`):
1. Exports `curation_public.json` containing metadata, tags, and excerpts for atoms where `visibility = 'public'` (keeps private atoms local-only).
2. Uploads the manifest to Google Cloud Storage (`gs://webtack-assets-drew/curation_public.json`).
3. Rsyncs public cover images to `gs://webtack-assets-drew/atoms/`.

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

## Schema & Sidecar Validation (`validate`)

Lints every `atom.json` against the formal JSON schema and verifies that all referenced media/markdown sidecars exist on disk:

```bash
# Validate entire vault
python3 curate.py validate

# Validate the demo vault
python3 curate.py validate --vault fixtures/demo_vault

# Validate a specific atom
python3 curate.py validate --atom atm_20261108200100_demoart
```

---

## Vault Architecture

```text
webtack/
├── curate.py                 # Core CLI ingestion & pipeline engine
├── viewer.py                 # Visual presentation & local capture server
├── webtack_mcp.py            # Model Context Protocol (MCP) server for AI tools
├── requirements.txt          # Python dependencies
├── LICENSE                   # Open source license (MIT for code, CC0 for schema)
├── SPECIFICATION.md          # Formal architectural specification & storage contract
├── schema/
│   └── atom.schema.json      # Formal JSON Schema specification (v3)
├── fixtures/
│   └── demo_vault/           # Self-contained specimen vault (6 canonical kinds)
└── vault/                    # Canonical user vault (gitignored / syncable)
    ├── vault.db              # Disposable SQLite search catalog
    ├── index.html            # Zero-dependency single-page visual gallery
    ├── export/               # Generated LLM digests & export files
    └── atoms/
        └── YYYY/
            └── MM/
                └── atm_YYYYMMDD.../
                    ├── atom.json      # 4-tier structured metadata envelope (Envelope, Provenance, Curation, Content)
                    ├── cover.jpg      # Universal visual preview (480px, blurhash, palette)
                    ├── article.md     # Offline readable article text (for articles)
                    ├── transcript.txt # Timestamped spoken dialogue (for videos)
                    ├── transcript.json# Machine-readable dialogue offsets
                    ├── note.md        # Formatted markdown thoughts (for notes)
                    └── quote.md       # Formatted markdown quote/excerpt (for quotes)
```

---

## License

- **Software & Tooling** (`curate.py`, `viewer.py`, `webtack_mcp.py`, etc.): [MIT License](LICENSE)
- **Schema & Specification** (`schema/atom.schema.json`): [Creative Commons Zero v1.0 Universal (CC0 1.0)](LICENSE)

