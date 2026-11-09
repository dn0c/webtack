# The WideWeb Specification (v3)

**Status:** Living Standard  
**Version:** 3.0.0  
**Authors:** Drew Shannon & WideWeb Contributors  
**License:** [Creative Commons Zero v1.0 Universal (CC0 1.0)](LICENSE)  
**Formal Schema:** [`schema/atom.schema.json`](schema/atom.schema.json)

---

## 1. Abstract & Philosophy

WideWeb is an open, local-first data specification and framework for durable digital curation and personal knowledge management. It establishes a formal bridge between ephemeral browser bookmarks (which rot and lack offline content) and unstructured text notes.

WideWeb is built on three core architectural principles:

1. **The Content Sidecar Pattern**: Every captured unit of knowledge—called an **Atom**—is an isolated, self-contained directory on disk holding a structured metadata envelope (`atom.json`) alongside its offline media and text sidecars (`cover.jpg`, `article.md`, `transcript.txt`, `quote.md`, `note.md`).
2. **Filesystem as Canonical Truth**: The directory tree on disk is the permanent source of truth. Databases (SQLite catalogs, vector stores, full-text indexes) are disposable, ephemeral artifacts that can be deleted and reconstructed in seconds from sidecars.
3. **The 30-Year Horizon**: Software dies, platforms pivot, and APIs change. WideWeb atoms rely exclusively on open, human-readable, and machine-inspectable standards (JSON, Markdown, JPEG, UTF-8 plain text) that can be read on any operating system decades from today without proprietary software.

---

## 2. Directory Layout & Storage Contract

A WideWeb vault conforms to the following directory hierarchy:

```text
<vault_root>/
├── vault.db                  # Disposable SQLite search catalog (auto-generated)
├── index.html                # Zero-dependency local visual gallery (auto-generated)
├── export/                   # Generated syndication manifests & platform exports
└── atoms/
    └── YYYY/
        └── MM/
            └── atm_YYYYMMDDHHMMSS_xxxxxx/
                ├── atom.json          # Canonical 4-layer metadata envelope (required)
                ├── cover.jpg          # Visual anchor / preview card (recommended)
                ├── article.md         # Full offline article text (for kind=article)
                ├── transcript.txt     # Dialogue transcript (for kind=video)
                ├── transcript.json    # Machine-readable timestamped offsets (optional)
                ├── quote.md           # Formatted quotation (for kind=quote)
                ├── note.md            # Markdown memo (for kind=note)
                └── document.pdf       # Original attachment (for kind=file)
```

### Path Resolution Rules
* **Relative Sidecars**: All file paths referenced in `atom.json` (such as `content.cover_image.relative_path` or `content.article.relative_path`) **MUST** be relative to the directory containing the `atom.json` file.
* **Identifier Format**: Atom IDs **MUST** start with the `atm_` prefix followed by a timestamp and entropy string (e.g. `atm_YYYYMMDDHHMMSS_xxxxxx`).

---

## 3. The 7 Canonical Kinds of Atoms

Every atom is classified into an explicit semantic `kind` that determines its primary role and expected sidecars:

| Kind | Semantic Role | Primary Slots | Expected Sidecars |
| :--- | :--- | :--- | :--- |
| **`article`** | Longform essay, newsletter, or blog post | `cover_image`, `article` | `cover.jpg`, `article.md` |
| **`bookmark`** | Lightweight web pointer (tool, repo, portal) | `cover_image` | `cover.jpg` (OG preview card) |
| **`video`** | Video stream (YouTube, Vimeo, recording) | `cover_image`, `video` | `cover.jpg`, `transcript.txt` |
| **`quote`** | Attributed verbatim quotation / excerpt | `text` (or `cover_image`) | `quote.md` |
| **`note`** | Personal thought, memo, or reflection | `text` | `note.md` (no external URL required) |
| **`image`** | Photograph, artwork, diagram, or scan | `cover_image` | `cover.jpg` |
| **`file`** | Document, PDF, or binary attachment | `cover_image`, `file` | `document.pdf`, `cover.png` |

---

## 4. The 4-Layer Metadata Envelope

Every `atom.json` sidecar conforms to a 4-layer architecture:

```text
┌────────────────────────────────────────────────────────┐
│  System Envelope (Document Header)                     │
│  (id, kind, version, created_at, updated_at, $schema)  │
├────────────────────────────────────────────────────────┤
│  Tier 1: Curation Layer                                │
│  (atom_title, description, tags, collections, vis)     │
├────────────────────────────────────────────────────────┤
│  Tier 2: Source Layer                                  │
│  (source_url, source_title, site_name, author, capture)│
├────────────────────────────────────────────────────────┤
│  Tier 3: Content Layer                                 │
│  (cover_image, article, text, video, file attachments) │
└────────────────────────────────────────────────────────┘
```

### 4.1 System Envelope
* **`$schema`** *(string)*: URI pointing to the canonical schema definition.
* **`id`** *(string, required)*: Unique identifier string (`atm_...`).
* **`kind`** *(string, required)*: One of `article`, `bookmark`, `video`, `quote`, `note`, `image`, `file`.
* **`version`** *(integer, required)*: Schema specification version (`3`).
* **`created_at`** *(string, required)*: ISO 8601 UTC timestamp of creation.
* **`updated_at`** *(string, required)*: ISO 8601 UTC timestamp of last update.

### 4.2 Tier 1: Curation Layer (`curation`)
Contains all subjective, user-authored editorial intent:
* **`atom_title`** *(string, required)*: The curated headline or name.
* **`description`** *(string | null)*: Editorial commentary, summary, or personal reading notes. *(Legacy fallback: `notes`)*.
* **`tags`** *(array of strings)*: Universal lowercase tags (hyphen-separated, pattern `^[a-z0-9.\\-]+$`).
* **`collections`** *(array of strings)*: High-level thematic folders or project groupings.
* **`visibility`** *(string)*: Egress classification (`public`, `shared`, `private`). Default: `public`.
* **`favorite`** *(boolean)*: Starred / pinned status flag. Default: `false`.

### 4.3 Tier 2: Source Layer (`source`)
Contains objective external provenance and capture tracking:
* **`source_url`** *(string | null)*: The canonical web URL where the content originated.
* **`source_title`** *(string | null)*: Original title published by the source site.
* **`site_name`** *(string | null)*: Name of the publishing site or service (e.g. "The Atlantic", "GitHub").
* **`author`** *(string | null)*: Author, channel name, or creator.
* **`published_at`** *(string | null)*: ISO 8601 publication date.
* **`favicon`** *(string | null)*: URL to the publisher's favicon.
* **`capture_method`** *(string | null)*: Ingestion conduit (`cli`, `bookmarklet`, `api`, `mcp`, `arena`, `instapaper`).
* **`capture_id`** *(string | null)*: Upstream platform identifier (e.g. Are.na block ID or Instapaper bookmark ID).
* **`capture_url`** *(string | null)*: Direct link to the captured item on the upstream platform.

### 4.4 Tier 3: Content Layer (`content`)
Holds metadata descriptors for offline sidecar assets:
* **`cover_image`**: Visual preview anchor. Contains `relative_path`, `mime_type`, `dimensions`, `aspect_ratio`, `blurhash`, `color_palette`, and `alt_text`.
* **`article`**: Longform text descriptor. Contains `relative_path` (pointing to `article.md`), `word_count`, and `byline`.
* **`video`**: Stream descriptor. Contains `provider`, `embed_url`, `duration_seconds`, `has_transcript`, and `transcript_file`.
* **`text`**: Text / excerpt descriptor for quotes and notes. Contains `relative_path`, `excerpt`, and `word_count`.
* **`file`**: Binary attachment descriptor. Contains `filename`, `relative_path`, `file_size_bytes`, `file_extension`, and `page_count`.

---

## 5. Extensions & Proprietary Metadata (`metadata_json`)

To enable third-party plugins (Obsidian, Anki, browser extensions, AI agents) to store custom metadata without colliding or requiring schema modifications, the top-level **`metadata_json`** object serves as the open extension bag.

### Extension Namespacing Rule
Third-party integrations **MUST** store custom fields under a reverse-domain or plugin-namespaced key inside `metadata_json`:

```json
{
  "metadata_json": {
    "com.obsidian.spaced_repetition": {
      "interval_days": 7,
      "ease_factor": 2.5,
      "due_date": "2026-11-15"
    },
    "org.wideweb.ai_vision": {
      "model": "gemini-3.8-flash",
      "labels": ["infographic", "system-architecture"],
      "confidence": 0.96
    }
  }
}
```

Standard WideWeb parsers **MUST** preserve unknown keys inside `metadata_json` during updates and reindexing.

---

## 6. Visibility & Egress Semantics

Every atom carries an explicit `visibility` tier in its curation layer:

| Tier | Distribution Scope | Cloud Sync & Syndication Rules |
| :--- | :--- | :--- |
| **`public`** | Open Web & Digital Garden | Synced to public cloud storage, included in public feeds, published to personal website galleries. |
| **`shared`** | Trusted Circle | Excluded from public sync; selectively exported for colleagues, collaborators, or family. |
| **`private`** | Strictly Local Machine | **Hard-blocked** from public cloud synchronization; never leaves the user's local hardware without explicit private backup. |

---

## 7. Validation & Conformance

A valid WideWeb vault complies with the following tests:

1. **Schema Conformance**: Every `atom.json` validates without error against `schema/atom.schema.json`.
2. **Sidecar Integrity**: Every relative path specified in `content` resolves to an existing file on disk.
3. **Disaster Recovery**: Deleting `vault.db` and running `curate.py reindex` reconstructs 100% of the catalog without data loss.
4. **Validation Tool**: Compliance can be verified at any time using:
   ```bash
   python3 curate.py validate --vault <path_to_vault>
   ```
