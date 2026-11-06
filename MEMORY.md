# WideWeb Project Memory & Decision Log

This document records the foundational architecture, schema evolutions, sync pipelines, export standards, and operational conventions for the WideWeb project. It serves as persistent context across agent sessions and development workstreams.

---

## 1. System Architecture & Core Philosophy

- **Local-First & Platform Independent**: WideWeb liberates personal knowledge curation from closed platforms (Are.na, Instapaper, Pinboard, Raindrop). Captures are preserved as permanent, human-readable local artifacts.
- **Content Sidecar Pattern**: The filesystem is the single canonical source of truth. Every curated atom resides in its own date-partitioned directory:
  ```text
  vault/atoms/YYYY/MM/atm_YYYYMMDDHHMMSS_xxxxxx/
    ├── atom.json          (Canonical metadata envelope)
    ├── cover.jpg          (Universal visual anchor / OG preview / artwork)
    ├── article.md         (Offline reader markdown body for longform articles)
    ├── quote.md           (Verbatim text excerpt for quotes)
    ├── note.md            (Personal thought/memo body for notes)
    ├── transcript.txt     (Spoken audio/video captions in plain text)
    ├── transcript.json    (Timestamped subtitle cues for media playback)
    └── document.pdf       (Attached binary document or book)
  ```
- **Disposable Index**: SQLite (`vault/vault.db`) is strictly a derived, high-performance query cache. If deleted, corrupted, or schema-upgraded, the entire database is reconstructed from disk in seconds via `python3 curate.py reindex`.
- **Three-Tier Decoupling**: Metadata in `atom.json` strictly separates editorial perspective (`curation`), upstream provenance (`source`), and physical media payload (`content`), wrapped in a lightweight system envelope.

---

## 2. Schema Evolution History (v1 → v2 → v3)

- **v1 (Flat Schema)**: Early prototype with loose URL fields, untyped assets, and display hints (`display_hint = "text" | "image"`).
- **v2 (Payload Sidecar Specification)**:
  - Formally partitioned metadata into 4 tiers: `root envelope`, `provenance`, `curation`, and `payload`.
  - Introduced the 7 core kinds (`article`, `bookmark`, `video`, `image`, `quote`, `note`, `file`).
  - Separated `article` (extracted readability text) from `bookmark` (lightweight pointer).
- **v3 (Canonical Content Architecture - Current)**:
  - Renamed `provenance` → `source` for conciseness.
  - Renamed `payload` → `content` and codified the modular 5-slot architecture (`cover_image`, `text`, `article`, `video`, `file`).
  - Promoted `kind` to the root envelope as the primary schema discriminator.
  - Renamed `curation.notes` → `curation.description` to resolve collision with `kind: "note"`.
  - Consolidated duplicate `link` kind into canonical `bookmark`.
  - Deprecated and removed unused `content.cover_image.public_url`.

---

## 3. Key Architectural Decisions Log

### [2026-11-05] Schema v3 Refinements & Consolidations

#### Decision 1: Consolidate `link` into `bookmark`
- **Context**: Schema previously included both `bookmark` and `link` in the `kind` enum, causing taxonomy ambiguity.
- **Decision**: Consolidate strictly to **`bookmark`** as the canonical kind for lightweight web pointers (tools, repositories, sites without full article bodies).
- **Implementation**:
  - Removed `"link"` from `kind` enum in `schema/atom.schema.json`.
  - Updated CLI filter choices (`--kind`) in `curate.py`.
  - Kept `curate.py link` / `save` CLI intake commands as smart auto-detect entry points that inspect URLs and output canonical `bookmark` or `article` atoms.
  - Reindexer preserves backwards compatibility: legacy `link` atoms in folders are mapped to `bookmark` (or `article` if `article.md` exists).

#### Decision 2: Rename `curation.notes` → `curation.description`
- **Context**: Having `curation.notes` alongside `kind: "note"` (atoms with personal thoughts in `note.md`) caused conceptual confusion. Furthermore, web bookmarks, RSS feeds, and platform exports treat this field as the curator's summary/description.
- **Decision**: Rename to **`curation.description`** across the schema.
- **Implementation**:
  - `atom.schema.json` defines `description` as the primary property, retaining `notes` as an optional legacy alias.
  - `curate.py` writes `"description": ...` in new atoms and accepts both `--description` and `--notes` CLI flags (`dest="description"`).
  - `viewer.py` and the SQLite reindexer check `cur.get("description") or cur.get("notes")` for seamless backwards compatibility.

#### Decision 3: Delete `content.cover_image.public_url`
- **Context**: The schema contained an optional `public_url` under `cover_image`.
- **Decision**: Remove `public_url` from the schema.
- **Rationale**: Vault audit confirmed 0 items used this field. WideWeb dynamically constructs public asset URLs on export or cloud sync (e.g. `https://storage.googleapis.com/<bucket>/atoms/.../cover.jpg`) rather than storing hardcoded bucket URLs in canonical metadata.

#### Decision 4: Retain `relative_path` across Content Slots
- **Context**: Evaluated whether `relative_path` (`atoms/YYYY/MM/<id>/<file>`) provides high semantic signal versus pure operational plumbing.
- **Decision**: Keep `relative_path` in place for now across all content slots (`cover_image`, `text`, `article`, `video`, `file`).
- **Rationale**: While `file` (`cover.jpg`, `article.md`) is the canonical local anchor, `relative_path` is a practical convenience pointer for SQLite indexing and flat static web serving without requiring runtime folder recalculations.

#### Decision 5: Retain `mime_type` on `cover_image`
- **Context**: Evaluated necessity of storing explicit image MIME types.
- **Decision**: Keep `content.cover_image.mime_type`.
- **Rationale**:
  1. Required by Gemini Vision API (`inline_data.mime_type`) in `ai_enrich.py` to generate multimodal alt text.
  2. Required by Google Cloud Storage sync (`curate.py sync`) to set proper HTTP `Content-Type` headers so browsers display rather than download images.
  3. Disambiguates WebP/AVIF images served with generic `.jpg` extensions.

#### Decision 6: Retain `content.video.embed_url`
- **Context**: Evaluated whether `source_url` could replace `embed_url`.
- **Decision**: Keep `content.video.embed_url`.
- **Rationale**: Standard video watch URLs (`youtube.com/watch?v=...`, `vimeo.com/...`) cannot be loaded in an `<iframe>` due to platform `X-Frame-Options: SAMEORIGIN` and CSP headers. Dedicated embed endpoints (`youtube.com/embed/...`, `player.vimeo.com/video/...`) allow direct iframe embedding across viewers and exported HTML without client-side regex parsing.

#### Decision 7: Intrinsic Egress & Visibility Classification (`public` vs `shared` vs `private`)
- **Context**: Curators collect everything from public web essays to internal team notes and sensitive personal journals. Relying on directory placement or external access control lists (ACLs) leads to accidental leaks when syncing or moving files.
- **Decision**: Bake egress classification directly into `curation.visibility` on every atom with three explicit tiers:
  1. **`public` (Digital Garden & Open Web)**:
     - **Intent**: Essays, bookmarks, artwork, and videos intended for open web syndication and public discovery.
     - **Egress Behavior**: Synced to Google Cloud Storage (`gs://wideweb-assets-drew`), included in `curation_public.json` for `drewshannon.net/garden`, syndicated in RSS feeds, and included in public export targets.
  2. **`shared` (Trusted Circle & Collaborative)**:
     - **Intent**: Material curated for a trusted inner circle (family, project collaborators, client deliverables) that should not be indexed by Google or exposed to random site visitors.
     - **Egress Behavior**: Strictly excluded from public GCS sync and digital garden manifests. Selectively exportable via `curate.py export --visibility shared` (e.g. generating a dedicated Raindrop folder or Obsidian sub-vault for a teammate). Prepares WideWeb for future authenticated sharing portals without schema rewrites.
  3. **`private` (Zero-Egress Local Vault)**:
     - **Intent**: Confidential journal entries, draft notes, sensitive health/financial bookmarks, internal receipts.
     - **Egress Behavior**: Never leaves the local machine. Defense-in-depth enforcement: excluded from SQLite public queries, and explicitly regex-blocked in `sync_assets_to_gcs` from ever uploading to cloud buckets. Searchable and readable solely inside the local masonry viewer (`viewer.py` on `127.0.0.1:8080`).

#### Decision 8: Defer Reading Lifecycle Status & Metrics
- **Context**: Evaluated adding reading state enums (`status: inbox | reading | archived`) and `read_time_minutes`.
- **Decision**: Deferred / Skipped for now to keep the canonical schema lean and avoid workflow state overhead. Word count remains available on articles.

#### Decision 9: `content.text.excerpt` Purpose & Enrichment
- **Context**: Defined roles and future enrichment pipeline for `content.text.excerpt`.
- **Role**:
  - `quote` atoms: Verbatim quote text (inline copy).
  - `note` atoms: Thought/memo body.
  - `article` atoms: Pull-quote or lead deck.
- **Future AI Trajectory**: Prime candidate for automated LLM synthesis (generating a high-signal 2–3 sentence executive summary/excerpt for longform articles).

---

## 4. Ingestion, Provenance & Synchronization Ecosystem

### Inbound Ingestion Pipelines (`curate.py pull`)
WideWeb features automated, deduplicated sync engines for external services:
1. **Instapaper Ingestion**:
   - Pulls unread bookmarks and reading highlights via the Instapaper Full API.
   - Extracts and saves full offline readability text directly from Instapaper's `/api/1/bookmarks/get_text` endpoint into `article.md`.
   - Title reconciliation script (`scripts/sync_instapaper_titles.py`) matches and updates clean editorial headlines while avoiding URL collisions.
2. **Are.na Ingestion**:
   - Ingests blocks from channels or user feeds.
   - Parses "Via:" and "Source:" notes to recover canonical external web links while retaining the Are.na block link in `source.capture_url`.
   - Two-Way Sync: AI-generated alt text created in WideWeb is synced back upstream to Are.na block descriptions (`ai_enrich.py`).
3. **YouTube Ingestion & Transcription (`curate.py backfill-transcripts`)**:
   - Ingests video bookmarks and channel playlists.
   - Background drip fetches spoken audio transcripts via `youtube-transcript-api`.
   - Auto-detects local `cookies.txt` (gitignored) to bypass YouTube bot detection/rate limits and gracefully handles `RequestBlocked` errors.
   - Generates both `transcript.txt` (plain text) and `transcript.json` (timestamped cues).

### Provenance & URL Normalization
- **URL Consolidation**: Deprecated conflicting fields (`destination_url`, `canonical_url`, `original_src_url`, `author_url`) into a single canonical `source.source_url`.
- **Origin vs Capture**: Strictly separated `source.source_url` (where content lives on the open web) from `source.capture_url` (where the curator discovered it).
- **Shortlink Unwrapping**: Automated tool (`scripts/unwrap_ifttt_links.py`) unrolls legacy IFTTT (`ift.tt`) redirect links to final destinations.
- **Tag Normalization**: Tags are strictly normalized to lowercase kebab-case (`^[a-z0-9.\\-]+$`) with hash marks and punctuation stripped.
- **Quote Standardization**: All quotes are standardized into `quote.md` sidecars with verbatim text in `content.text.excerpt`, creator attribution in `source.author`, and source titles in `source.source_title`.

---

## 5. Public Website, Digital Garden & GCP Hosting Architecture

### Target & Egress Boundaries
- **Public Digital Garden**: Live website hosted on **Ghost** (`drewshannon.net/garden`).
- **Privacy Partitioning**: Only atoms with `curation.visibility == 'public'` are exported into the public manifest and synced to the cloud. Atoms marked `shared` or `private` remain strictly local on disk.

### Two-Stage Manifest Loading Architecture
To ensure sub-second first-screen loads for a 13,000+ item vault without browser memory freezing:
1. **`curation_recent.json` (Stage 1 - Instant Render)**:
   - Contains the top **72 most recent public atoms**.
   - Embeds the full raw schema envelope (`raw: clean_raw`) on these 72 items for zero-fetch, instant inspection in modal views.
2. **`curation_public.json` (Stage 2 - Full Search Index)**:
   - Contains streamlined metadata entries for all ~8,000+ public atoms.
   - Omitted `raw` and full article markdown to prevent massive single-payload bloat.
   - Loaded asynchronously in the background to power client-side search, filtering, and pagination.

### Lazy-Loaded Assets & Cloud Offloading
- **Decoupled Article Bodies (`article_url`)**:
  - Full-text markdown bodies (`article.md`) are NOT inlined into `curation_public.json` (saving over 120MB+ of payload).
  - Synced to `https://storage.googleapis.com/wideweb-assets-drew/atoms/YYYY/MM/<id>/article.md`.
  - The reader modal fetches `article_url` on-demand only when a user clicks an article card.
- **Decoupled Raw Schema Inspection (`atom_url`)**:
  - For items outside the initial 72, raw JSON is fetched on-demand from `https://storage.googleapis.com/wideweb-assets-drew/atoms/YYYY/MM/<id>/atom.json?v={timestamp}` with asset cache-busting.

### Google Cloud Storage (GCS) Pipeline
- **Bucket**: `gs://wideweb-assets-drew` (overrideable with `WIDEWEB_GCS_BUCKET`).
- **CORS Configuration (`scripts/gcs_cors.json`)**:
  - Configured with `origin: ["*"]`, methods `["GET", "HEAD", "OPTIONS"]`, and `maxAgeSeconds: 3600`.
  - Allows `drewshannon.net`, Ghost theme client scripts, and local development servers to fetch manifests and Markdown via client-side `fetch()`.
- **Gzip-Compressed Manifest Publishing**:
  - Manifests (`curation_recent.json` and `curation_public.json`) are uploaded directly via Google Cloud Storage REST API with Level-9 gzip compression (`contentEncoding: gzip`, `contentType: application/json`).
  - Cache-Control set to `public, max-age=120` (2 minutes) to ensure readers receive recent curations without serving stale indices.
  - Automatic fallback to `gcloud storage cp` CLI when API tokens are unavailable.
- **Asset Syncing (`curate.py sync` / `sync_assets_to_gcs`)**:
  - Uses `gcloud storage rsync` to mirror `cover.jpg`, `article.md`, and `atom.json` to `gs://wideweb-assets-drew/atoms/`.
  - Filter regex strictly excludes internal memos (`note.md`), verbatim quotes (`quote.md`), caption files (`transcript.txt`, `transcript.json`), system clutter (`.DS_Store`), and explicit private atoms.

---

## 6. Multi-Format Export Engine & AI Protocols

### Export Center (`curate.py export` & `/export.html`)
WideWeb features a dedicated local export engine that serializes the vault into 12 industry-standard targets:
1. **`digest`**: Unified single-file Markdown compendium for deep personal reading or offline search.
2. **`llms-txt`**: Adheres to the emerging `llms.txt` and `llms-full.txt` standard, providing LLMs with a low-token index of curated knowledge.
3. **`obsidian` / `logseq`**: Discrete Markdown notes with YAML frontmatter, tags, and inline media links.
4. **`bookmarks-html`**: Netscape Bookmark Specification HTML, importing seamlessly into desktop browsers, Safari, or Pinboard.
5. **`readwise`**: Spec-compliant CSV for Readwise highlight imports and daily active recall reviews.
6. **`arena-csv`**: Bulk CSV formatted for importing into Are.na channels.
7. **`pinterest-csv`**: Official Pinterest bulk upload format for visual board creation.
8. **`raindrop-csv`**: Custom folder and tag CSV for Raindrop.io imports.
9. **`rss`**: Spec-compliant RSS 2.0 XML feed for public syndication and personal feed readers.
10. **`bibtex`**: Academic citation blocks (`@article`, `@misc`) for Zotero and LaTeX bibliographies.
11. **`jsonl`**: Newline-delimited JSON envelopes optimized for LangChain, LlamaIndex, and vector embedding pipelines.
12. **`json`**: Complete, unpruned disaster recovery backup dump of all raw envelopes.

### Model Context Protocol (MCP) Server (`wideweb_mcp.py`)
- Provides a native Model Context Protocol server exposing tools (`list_atoms`, `get_atom`, `search_atoms`, `read_article`) to AI clients (Claude Desktop, Gemini CLI, Antigravity).

---

## 7. Canonical 7 Kinds of Atoms

| Kind | Role | Primary Content Slots | Expected Sidecars | Live Vault Count (Nov 2026) |
| :--- | :--- | :--- | :--- | :---: |
| **`article`** | Longform essay, newsletter, post | `cover_image`, `article` | `cover.jpg`, `article.md` | ~8,055 |
| **`bookmark`** | Lightweight web pointer (tool, repo, site) | `cover_image` (OG card) | `cover.jpg` | ~2,477 |
| **`video`** | YouTube, Vimeo, or video stream | `cover_image`, `video` | `cover.jpg`, `transcript.txt` | ~1,638 |
| **`image`** | Photo, artwork, diagram, scan | `cover_image` | `cover.jpg` | ~931 |
| **`quote`** | Attributed verbatim excerpt | `text` (or `cover_image`) | `quote.md` | ~689 |
| **`note`** | Personal thought, memo, reflection | `text` | `note.md` | ~10 |
| **`file`** | Document, PDF, binary attachment | `cover_image`, `file` | `document.pdf`, `cover.png` | 0 |

---

## 8. Key Workstream Assets & External References

- **Canonical JSON Schema**: `schema/atom.schema.json`
- **Interactive Google Sheet Data Dictionary**: [WideWeb - Schema Dictionary & Architecture](https://docs.google.com/spreadsheets/d/1V7nKitvW7cumwtzG4PFLMOFTApJWTuow4J32ks5vMm0/edit)
  - Tab 1: `Schema Dictionary` (53 fields & subfields)
  - Tab 2: `Kind Matrix` (7 kinds, slots, sidecars, vault counts)
  - Tab 3: `Proposed Changes` (Decision log and proposal scratchpad)
- **Primary CLI**: `curate.py` (`bookmark`, `article`, `link`, `quote`, `note`, `image`, `video`, `reindex`, `sync`, `enrich`)
- **Local Masonry Viewer**: `viewer.py` (served at `http://127.0.0.1:8080`)
- **AI Vision Pipeline**: `ai_enrich.py` (Gemini Flash multimodal alt text + Are.na upstream sync)
- **Local MCP Server**: `wideweb_mcp.py`
